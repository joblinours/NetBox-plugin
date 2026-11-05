# netbox-cmdb

Glue plugin of the homelab CMDB (NetBox 4.7). / Plugin « colle » de la CMDB homelab.

## Features

- **`manage.py cmdb_bootstrap`** — run at every start of the CMDB image, idempotent, driven by environment variables:
  - custom fields of the base data model: `public_url` (URL publique), `exposure_path` (Chemin d'exposition: *cloudflared direct* / *via Nginx*), `upstream_target` (Cible amont), `portainer_stack` (Stack Portainer), `backup_location` (Emplacement des sauvegardes). Existing fields are never overwritten;
  - service accounts `svc-orb-agent`, `svc-nginx-agent`, `svc-zabbix`: no usable password, one v2 API token each taken from `CMDB_TOKEN_*` (`nbt_<key>.<secret>`), minimal object permissions. Changing the variable rotates the token;
  - the `proxmox2netbox` endpoint from `PROXMOX_HOST`, `PROXMOX_USER`, `PROXMOX_TOKEN_NAME`, `PROXMOX_TOKEN_VALUE`, `PROXMOX_VERIFY_SSL`.
- **Syncs at start-up and on demand**: every NetBox start (so every redeploy of the stack) queues one immediate run of the Proxmox, Cloudflare and AdGuard syncs (`CMDB_SYNC_ON_START=false` to disable). *CMDB > Source health* has a **Run all syncs now** button, and a button to forget a source that no longer exists (e.g. a renamed Docker host).
- **Scheduled Proxmox sync** — NetBox system job `CMDB - Proxmox sync` running `proxmox2netbox`'s full sync every `proxmox_sync_interval` minutes (default 1440).
- **Source health** — model `SourceStatus`; every source reports each run:
  - `POST /api/plugins/cmdb/sources/` `{"source": "nginx", "status": "ok|failed", "message": "...", "details": {}}` (permission `netbox_cmdb.change_sourcestatus`);
  - `GET /api/plugins/cmdb/health/` → database status and, per source, `healthy` (last run OK and last success younger than `max_age_hours`). Used by the Zabbix template;
  - UI: *CMDB > Source health*.

## Settings

```python
PLUGINS_CONFIG = {
    "netbox_cmdb": {
        "proxmox_sync_interval": 1440,
        "max_age_hours": 26,
        "expected_sources": ["proxmox", "cloudflare", "network-scan", "nginx"],
    }
}
```

## Tests

```bash
python manage.py test netbox_cmdb
```

## Licence

MIT
