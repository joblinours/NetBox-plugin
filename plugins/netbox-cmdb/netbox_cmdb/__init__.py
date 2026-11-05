"""Homelab CMDB glue plugin for NetBox."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class NetBoxCMDBConfig(PluginConfig):
    name = "netbox_cmdb"
    verbose_name = "CMDB homelab"
    description = "Base data model, service accounts, scheduled Proxmox sync and source health"
    version = __version__
    author = "Lucas Joblin"
    base_url = "cmdb"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        # Interval (minutes) of the scheduled Proxmox -> NetBox sync. 0 disables it.
        "proxmox_sync_interval": 1440,
        # A source whose last success is older than this (hours) is reported as stale.
        "max_age_hours": 26,
        # Sources expected to report. Missing ones are reported as "never".
        "expected_sources": ["proxmox", "cloudflare", "network-scan", "nginx"],
    }

    def ready(self):
        super().ready()
        from . import jobs  # noqa: F401  (registers the system jobs)


config = NetBoxCMDBConfig
