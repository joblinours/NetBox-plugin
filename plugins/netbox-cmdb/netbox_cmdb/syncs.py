"""Run every pull-based sync now (Proxmox, Cloudflare, AdGuard), on demand or at NetBox start.

The scheduled system jobs only run every 24 h; without this, a variable changed in
the stack would only be taken into account the next day.
"""

import logging
from importlib import import_module

from django.apps import apps
from netbox.plugins import get_plugin_config

logger = logging.getLogger("netbox.plugins.netbox_cmdb")

# (plugin app, module with the job, job class, "is it configured?" check)
SYNCS = [
    ("netbox_cmdb", "netbox_cmdb.jobs", "ProxmoxDailySyncJob", None),
    (
        "netbox_cloudflare_tunnel",
        "netbox_cloudflare_tunnel.jobs",
        "CloudflareSyncJob",
        lambda: bool(get_plugin_config("netbox_cloudflare_tunnel", "api_token")),
    ),
    (
        "netbox_adguard",
        "netbox_adguard.jobs",
        "AdGuardSyncJob",
        lambda: bool(get_plugin_config("netbox_adguard", "instances")),
    ),
]


def _proxmox_configured():
    try:
        from proxmox2netbox.models import ProxmoxEndpoint
    except ImportError:
        return False
    return ProxmoxEndpoint.objects.filter(sync_enabled=True).exists()


def enqueue_all(user=None):
    """Queue one immediate run of each configured sync (skipped if one is already waiting).

    Returns the list of queued job names.
    """
    from core.choices import JobStatusChoices
    from core.models import Job

    queued = []
    for app, module, cls_name, configured in SYNCS:
        if not apps.is_installed(app):
            continue
        check = configured or _proxmox_configured
        if not check():
            continue
        job_class = getattr(import_module(module), cls_name)
        name = job_class.name if isinstance(job_class.name, str) else job_class.Meta.name
        waiting = Job.objects.filter(
            name=name, interval__isnull=True, status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES
        ).exists()
        if waiting:
            continue
        job_class.enqueue(user=user)
        queued.append(name)
    return queued
