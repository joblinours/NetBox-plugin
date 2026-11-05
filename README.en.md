# NetBox-plugin — homelab CMDB (NetBox + Diode)

🇫🇷 [Version française](README.md)

Everything needed to run the homelab CMDB: NetBox as the source of truth, filled automatically by Diode and by plugins. One Portainer stack, no file to copy to the host.

| Folder | Content |
| --- | --- |
| `plugins/netbox-cloudflare-tunnel/` | Home-made plugin: syncs Cloudflare Tunnel public hostnames and records, for each, the exposure path (cloudflared direct or via Nginx) and the target service |
| `plugins/netbox-cmdb/` | Home-made plugin: base data model (custom fields), service accounts and tokens, scheduled Proxmox sync, source health for Zabbix |
| `plugins/netbox-cmdb-mcp/` | Home-made plugin: read-only MCP server for Claude Code (hosts, used/free IPs and ports, URLs, DNS, containers) |
| `plugins/netbox-cmdb-export/` | Home-made plugin: CMDB export as Markdown, PDF, JSON, and topology graph (Mermaid / PNG / SVG) |
| `plugins/netbox-adguard/` | Home-made plugin: AdGuard Home DNS rewrites → local names in NetBox and netbox-plugin-dns |
| `plugins/netbox-docker-inventory/` | Home-made plugin: Docker hosts, stacks, containers (even silent ones), internal networks, ports, volumes |
| `agents/docker-agent/` | Docker agent (in the stack for the LXC; `deploy/docker-agent.compose.yml` for every other Docker host) |
| `agents/nginx-agent/` | Discovery agent installed on `revers-proxy`: reads `nginx -T` and pushes virtual hosts to NetBox through Diode |
| `image/netbox/` | NetBox image recipe (official image + third-party plugins + home-made plugins) |
| `image/diode-gateway/`, `image/diode-bootstrap/`, `image/orb-agent/` | Small images carrying the Diode and orb-agent configuration (so nothing lives on the host) |
| `deploy/` | Stack file (`docker-compose.yml`) and variables example (`stack.env.example`) |
| `tools/generate-env.py` | Generates every stack variable with random secrets |
| `monitoring/zabbix/` | Zabbix 7.0 template (NetBox/API/Diode availability and failure of each source) |
| `.github/workflows/build.yml` | Lint, tests on a NetBox 4.7 instance, secret scan, build and push to GHCR |

## Architecture

Two blocks in one stack: **NetBox** (netbox, netbox-worker, postgres, valkey) stores and serves the inventory; **Diode** (diode-gateway, diode-ingester, diode-reconciler, diode-auth, hydra, diode-postgres, diode-redis) receives and reconciles data before writing it to NetBox through the Diode plugin API. orb-agent runs in the same stack with host networking so nmap sees the LAN.

Only two ports are published: the NetBox UI/API (`NETBOX_PORT`, 10000) and the Diode gRPC entry point (`DIODE_GRPC_PORT`, 10001); 8000 is taken by Portainer.

### Automatic sources

| Source | How | Frequency | Reported to Zabbix as |
| --- | --- | --- | --- |
| Proxmox | `proxmox2netbox` plugin; its endpoint is created at start-up from the variables; system job `CMDB - Proxmox sync` in the worker. The whole cluster is read through the API, so a new node appears with no change | `PROXMOX_SYNC_INTERVAL` (1440 min) | `proxmox` |
| Network scan | orb-agent (nmap) → Diode. One scan at start-up, then nightly (`SCAN_SCHEDULE`). Live IPs + open ports (in the IP comments) | daily | `network-scan` |
| Cloudflare | `netbox-cloudflare-tunnel` plugin: reads the ingress of dashboard-managed tunnels (read-only token), finds or creates the target service and sets `URL publique` / `Chemin d'exposition` | `CLOUDFLARE_SYNC_INTERVAL` (1440 min) | `cloudflare` |
| Nginx | `cmdb-nginx-agent` on revers-proxy (systemd timer) → Diode. One service per `server_name`, with ports and upstream (`proxy_pass`) | daily | `nginx` |

| AdGuard Home | `netbox-adguard`: DNS rewrites → IP/host (`local_domains` custom field) and A/CNAME records in netbox-plugin-dns | `ADGUARD_SYNC_INTERVAL` (1440 min) | `adguard` |
| Docker | `cmdb-docker-agent` on each Docker host → `netbox-docker-inventory` (containers, stacks, internal networks; published ports become NetBox services with the Portainer stack) | hourly | `docker-<host>` |

**Claude Code (MCP)**: `claude mcp add --transport http --scope user cmdb http://192.168.1.13:10000/api/plugins/mcp/ --header "Authorization: Bearer <CMDB_TOKEN_MCP>"`. **Export**: *Plugins > Export CMDB* or `GET /api/plugins/export/<md|pdf|json|mmd|png|svg>/`.

Exposure path: when the origin of a Cloudflare hostname is the revers-proxy IP (`NGINX_PROXY_HOSTS`) the hostname is "via Nginx"; the plugin finds the vhost pushed by the Nginx agent, reads its upstream and attaches the public URL to the final service (e.g. `cloud.example.com` → revers-proxy:443 → nextcloud:11000). Otherwise it is "cloudflared direct" and attached to the service of the origin VM. All sources are idempotent.

## First deployment

1. **Read-only credentials**
   - Proxmox: create user `netbox@pve`, an API token `cmdb` *without* privilege separation, and grant role `PVEAuditor` on `/`.
   - Cloudflare: API token with `Account > Cloudflare Tunnel > Read`; note the Account ID.
2. **Generate the variables**: `python3 tools/generate-env.py > cmdb.env`, fill in `PROXMOX_*`, `CLOUDFLARE_*`, `NGINX_PROXY_HOSTS`, `NETBOX_ADMIN_USER`. Store the file in Vaultwarden; never commit it.
3. **Portainer**: `Stacks > Add stack > Repository`, URL `https://github.com/joblinours/NetBox-plugin`, reference `refs/heads/main`, compose path `deploy/docker-compose.yml`, paste `cmdb.env` in *Environment variables > Advanced mode*, deploy. GHCR images are public.
4. **First start** (a few minutes): migrations, admin account, then `cmdb_bootstrap` creates the custom fields, the `svc-*` service accounts and tokens, and the Proxmox endpoint; `diode-bootstrap` creates the Diode OAuth2 clients.
5. **Check**: log in on `http://192.168.1.13:10000`; `Diode > Settings` shows the Diode target without error; `CMDB > Source health` shows each source.
6. **Nginx agent** on revers-proxy: see [agents/nginx-agent/README.md](agents/nginx-agent/README.md).
7. **Zabbix**: import `monitoring/zabbix/cmdb_netbox_template.yaml`, link it to the CMDB host, set `{$CMDB.TOKEN}` to `CMDB_TOKEN_ZABBIX`.

The admin account is only created when it does not exist yet; afterwards change its password in NetBox.

## Updating

- **Images**: *Pull and redeploy* the stack in Portainer. `latest` follows `main`, `dev` follows `dev`; pin with `CMDB_IMAGE_TAG=1.2.3`.
- **NetBox upgrade**: on `dev`, bump `ARG NETBOX_VERSION` in `image/netbox/Dockerfile`, check each plugin's compatibility and adjust `image/netbox/plugin_requirements.txt`. CI checks that every plugin loads, migrations are complete and tests pass; merge to `main` only when CI is green and the `dev` image ran fine.

## Adding a plugin

- **PyPI plugin**: add `package==version` to `image/netbox/plugin_requirements.txt`, its name to `PLUGINS` and its settings to `PLUGINS_CONFIG` in `image/netbox/config/plugins.py` (secrets read from the environment), bump `expected = 14` in the workflow, push.
- **Home-made plugin**: create `plugins/<name>/` (Python package with `pyproject.toml`, README, MIT licence, tests in `<module>/tests/`), add it to the `uv pip install` line of the Dockerfile, to `PLUGINS`, and to the workflow's `manage.py test` command.

## Changing a secret

| Secret | Procedure |
| --- | --- |
| `DIODE_CLIENT_SECRET_*` | Change the variable, redeploy: `diode-bootstrap` updates the client in Hydra at every start. Update `/etc/cmdb-nginx-agent.env` for `nginx-agent`. |
| `CMDB_TOKEN_*` | `python3 tools/generate-env.py --token`, change the variable, redeploy: the old token is replaced. Update Zabbix / the Nginx agent. |
| `PROXMOX_TOKEN_VALUE`, `CLOUDFLARE_API_TOKEN` | Change the variable, redeploy. |
| Database passwords | Set when the volumes are created: change the password in PostgreSQL first (`ALTER USER … PASSWORD …`), then the variable, then redeploy. |
| `NETBOX_SECRET_KEY` | Any time (logs users out). |
| `NETBOX_API_TOKEN_PEPPER` | Invalidates every API token; `svc-*` tokens are recreated at restart, others must be recreated. |

## Security

Local access only (never published through the Cloudflare tunnel; `BIND_ADDRESS` restricts listening to the LAN interface). Every Diode ingestion uses a dedicated OAuth2 client. One named admin; `svc-*` accounts have no usable password, one token each, minimal permissions. No secret in the repository or the images; CI runs gitleaks on the full Git history. No backup in v1 (deliberate decision).

## Licence

MIT — see [LICENSE](LICENSE).
