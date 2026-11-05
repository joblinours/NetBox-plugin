"""Scheduled jobs registered by the CMDB plugin.

NetBox system jobs are (re)scheduled automatically by the RQ worker at start-up,
so the daily Proxmox sync needs no manual action and survives restarts.
"""

import logging

from netbox.jobs import JobFailed, JobRunner, system_job
from netbox.plugins import get_plugin_config

from .models import SourceStatus

logger = logging.getLogger("netbox.plugins.netbox_cmdb")

PROXMOX_INTERVAL = int(get_plugin_config("netbox_cmdb", "proxmox_sync_interval") or 0)


def run_proxmox_sync():
    """Run proxmox2netbox's full sync and record the outcome as the 'proxmox' source."""
    try:
        from proxmox2netbox.models import ProxmoxEndpoint
        from proxmox2netbox.services.proxmox_sync import sync_full_update
    except ImportError as exc:  # pragma: no cover - plugin missing from the image
        SourceStatus.report("proxmox", False, f"proxmox2netbox not installed: {exc}")
        raise JobFailed("proxmox2netbox is not installed")

    if not ProxmoxEndpoint.objects.filter(sync_enabled=True).exists():
        msg = "No enabled Proxmox endpoint (set PROXMOX_HOST / PROXMOX_TOKEN_* in the stack)"
        SourceStatus.report("proxmox", False, msg)
        raise JobFailed(msg)

    try:
        result = sync_full_update() or {}
    except Exception as exc:
        SourceStatus.report("proxmox", False, repr(exc))
        raise

    errors = result.get("errors") or []
    summary = {k: v for k, v in result.items() if k != "errors" and isinstance(v, (int, str, bool, float))}
    if errors:
        SourceStatus.report("proxmox", False, "; ".join(map(str, errors)), summary)
        raise JobFailed("; ".join(map(str, errors)))
    SourceStatus.report("proxmox", True, "Sync complete", summary)
    return result


class ProxmoxDailySyncJob(JobRunner):
    class Meta:
        name = "CMDB - Proxmox sync"

    def run(self, *args, **kwargs):
        result = run_proxmox_sync()
        self.logger.info("Proxmox sync complete: %s", {k: v for k, v in (result or {}).items() if k != "errors"})


if PROXMOX_INTERVAL > 0:
    ProxmoxDailySyncJob = system_job(interval=PROXMOX_INTERVAL)(ProxmoxDailySyncJob)
