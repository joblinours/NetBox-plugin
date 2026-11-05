import logging

from django.apps import apps
from netbox.jobs import JobFailed, JobRunner, system_job
from netbox.plugins import get_plugin_config

from .cloudflare import CloudflareClient, CloudflareError
from .sync import sync

logger = logging.getLogger("netbox.plugins.netbox_cloudflare_tunnel")

PLUGIN = "netbox_cloudflare_tunnel"
SYNC_INTERVAL = int(get_plugin_config(PLUGIN, "sync_interval") or 0)


def plugin_settings():
    keys = ("api_token", "account_id", "tunnel_ids", "nginx_hosts", "create_services", "api_base_url", "timeout")
    return {k: get_plugin_config(PLUGIN, k) for k in keys}


def _report(ok, message, details=None):
    """Record the run in netbox_cmdb's source health when that plugin is installed."""
    if not apps.is_installed("netbox_cmdb"):
        return
    from netbox_cmdb.models import SourceStatus

    SourceStatus.report("cloudflare", ok, message, details)


def run_sync(log=logger):
    settings = plugin_settings()
    try:
        client = CloudflareClient(
            settings["api_token"], settings["account_id"], settings["api_base_url"], int(settings["timeout"] or 30)
        )
        result = sync(client, settings, log=log)
    except CloudflareError as exc:
        _report(False, str(exc))
        raise JobFailed(str(exc))
    except Exception as exc:
        _report(False, repr(exc))
        raise
    summary = result.as_dict()
    _report(
        True, f"{result.hostnames} hostnames on {result.tunnels} tunnels, {len(result.unresolved)} unresolved", summary
    )
    return summary


class CloudflareSyncJob(JobRunner):
    class Meta:
        name = "Cloudflare Tunnel sync"

    def run(self, *args, **kwargs):
        summary = run_sync(log=self.logger)
        self.logger.info("Cloudflare sync: %s", summary)


if SYNC_INTERVAL > 0:
    CloudflareSyncJob = system_job(interval=SYNC_INTERVAL)(CloudflareSyncJob)
