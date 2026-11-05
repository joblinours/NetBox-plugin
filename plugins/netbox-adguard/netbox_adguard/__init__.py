"""AdGuard Home DNS rewrites -> NetBox."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class AdGuardConfig(PluginConfig):
    name = "netbox_adguard"
    verbose_name = "AdGuard Home"
    description = "Import AdGuard Home DNS rewrites (local domain names)"
    version = __version__
    author = "Lucas Joblin"
    base_url = "adguard"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        # AdGuard Home base URLs, e.g. ["http://192.168.1.2:3000"]. Same credentials for all.
        "instances": [],
        "username": "",
        "password": "",
        "verify_ssl": True,
        "timeout": 20,
        "sync_interval": 1440,
        # Mirror the rewrites into netbox-plugin-dns (A / AAAA / CNAME records).
        "sync_netbox_dns": True,
        # Create a zone (parent domain of the rewrite) when no existing zone matches.
        "auto_create_zones": True,
        # Name server used as SOA MNAME of the zones created by the plugin.
        "nameserver": "adguard.home.arpa",
        "record_tag": "adguard",
    }

    def ready(self):
        super().ready()
        from . import jobs  # noqa: F401


config = AdGuardConfig
