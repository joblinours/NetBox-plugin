import logging

from django.apps import apps
from netbox.jobs import JobFailed, JobRunner, system_job
from netbox.plugins import get_plugin_config

from .client import AdGuardClient
from .sync import sync

logger = logging.getLogger("netbox.plugins.netbox_adguard")
PLUGIN = "netbox_adguard"
SYNC_INTERVAL = int(get_plugin_config(PLUGIN, "sync_interval") or 0)
KEYS = (
    "instances",
    "username",
    "password",
    "verify_ssl",
    "timeout",
    "sync_netbox_dns",
    "auto_create_zones",
    "nameserver",
    "record_tag",
)


def plugin_settings():
    return {k: get_plugin_config(PLUGIN, k) for k in KEYS}


def _report(ok, message, details=None):
    if apps.is_installed("netbox_cmdb"):
        from netbox_cmdb.models import SourceStatus

        SourceStatus.report("adguard", ok, message, details)


def run_sync(log=logger):
    settings = plugin_settings()
    urls = [u for u in settings["instances"] or [] if u]
    if not urls:
        _report(False, "No AdGuard instance configured (ADGUARD_URLS)")
        raise JobFailed("No AdGuard instance configured")
    clients = [
        AdGuardClient(u, settings["username"], settings["password"], settings["verify_ssl"], settings["timeout"])
        for u in urls
    ]
    try:
        result = sync(clients, settings, log=log)
    except Exception as exc:
        _report(False, repr(exc))
        raise
    summary = result.as_dict()
    if result.instances_failed:
        msg = "; ".join(result.instances_failed)
        _report(False, msg, summary)
        raise JobFailed(msg)
    _report(
        True,
        f"{result.rewrites} rewrites, {len(result.unresolved)} unresolved, {len(result.dns_errors)} DNS errors",
        summary,
    )
    return summary


class AdGuardSyncJob(JobRunner):
    class Meta:
        name = "AdGuard rewrites sync"

    def run(self, *args, **kwargs):
        self.logger.info("AdGuard sync: %s", run_sync(log=self.logger))


if SYNC_INTERVAL > 0:
    AdGuardSyncJob = system_job(interval=SYNC_INTERVAL)(AdGuardSyncJob)
