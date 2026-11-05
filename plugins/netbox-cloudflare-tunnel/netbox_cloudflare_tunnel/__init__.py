"""Cloudflare Tunnel -> NetBox plugin."""

from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class CloudflareTunnelConfig(PluginConfig):
    name = "netbox_cloudflare_tunnel"
    verbose_name = "Cloudflare Tunnel"
    description = "Sync Cloudflare Tunnel public hostnames and map them to NetBox services"
    version = __version__
    author = "Lucas Joblin"
    base_url = "cloudflare-tunnel"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        # Cloudflare API token, read-only: Account > Cloudflare Tunnel > Read
        "api_token": "",
        "account_id": "",
        # Optional list of tunnel UUIDs to sync. Empty = every tunnel of the account.
        "tunnel_ids": [],
        # IPs / hostnames of the Nginx reverse proxy. An ingress pointing at one of them
        # is classified "via Nginx", anything else "cloudflared direct".
        "nginx_hosts": [],
        # Create an ipam.Service on the origin VM/device when none matches the port.
        "create_services": True,
        # Interval (minutes) of the scheduled sync. 0 disables scheduling.
        "sync_interval": 1440,
        "api_base_url": "https://api.cloudflare.com/client/v4",
        "timeout": 30,
    }

    def ready(self):
        super().ready()
        from . import jobs  # noqa: F401  (registers the system job)


config = CloudflareTunnelConfig
