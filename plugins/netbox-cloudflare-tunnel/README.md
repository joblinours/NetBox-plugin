# netbox-cloudflare-tunnel

NetBox plugin (NetBox 4.7) that syncs the **public hostnames of Cloudflare Tunnels** into NetBox and links each one to the service it ends up on.

Plugin NetBox (4.7) qui synchronise les **hostnames publics des tunnels Cloudflare** et rattache chacun au service vers lequel il pointe.

## What it does

For every dashboard-managed tunnel of the account (`GET /accounts/{id}/cfd_tunnel`, then `…/configurations`):

1. each ingress rule (hostname + optional path → origin) becomes a **Public hostname**;
2. the origin is resolved to a NetBox IP address / VM / device (IP, `dns_name`, then VM/device name);
3. **exposure path**: origin in `nginx_hosts` → *via Nginx*, otherwise *cloudflared direct*;
4. *direct*: the service of the origin VM on the origin port is found, or created;
   *via Nginx*: the Nginx vhost (an `ipam.Service` named after the hostname with an `upstream_target` custom field, pushed by `cmdb-nginx-agent` through Diode) is found, its upstream is resolved the same way and the backend service is found or created;
5. the custom fields `public_url` and `exposure_path` are set on those services (created by the `netbox-cmdb` plugin).

Runs are idempotent; hostnames removed in Cloudflare are deleted and their services' fields cleared. Tunnels managed with a local `config.yml` are listed but skipped (their ingress is not visible through the API).

Models: `Tunnel`, `PublicHostname` (UI under *Plugins > Cloudflare Tunnel*, read-only REST API under `/api/plugins/cloudflare-tunnel/`). A **Sync now** button queues an immediate run.

## Configuration

```python
PLUGINS = ["netbox_cloudflare_tunnel"]
PLUGINS_CONFIG = {
    "netbox_cloudflare_tunnel": {
        "api_token": "...",          # Account > Cloudflare Tunnel > Read
        "account_id": "...",
        "tunnel_ids": [],            # optional filter
        "nginx_hosts": ["192.168.1.30"],
        "create_services": True,
        "sync_interval": 1440,       # minutes, 0 = no schedule (system job)
    }
}
```

In the CMDB image these values come from `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_TUNNEL_IDS`, `NGINX_PROXY_HOSTS`, `CLOUDFLARE_CREATE_SERVICES`, `CLOUDFLARE_SYNC_INTERVAL`.

When `netbox_cmdb` is installed, each run is recorded as source `cloudflare` (health endpoint → Zabbix).

## Tests

```bash
python manage.py test netbox_cloudflare_tunnel
```

## Licence

MIT
