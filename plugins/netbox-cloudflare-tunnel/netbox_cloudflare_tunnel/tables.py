import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .models import PublicHostname, Tunnel


class TunnelTable(NetBoxTable):
    name = tables.Column(linkify=True)
    hostname_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_cloudflare_tunnel:publichostname_list",
        url_params={"tunnel_id": "pk"},
        verbose_name="Hostnames",
    )

    class Meta(NetBoxTable.Meta):
        model = Tunnel
        fields = ("pk", "id", "name", "tunnel_id", "status", "remote_config", "hostname_count", "last_synced", "tags")
        default_columns = ("name", "tunnel_id", "status", "remote_config", "hostname_count", "last_synced")


class PublicHostnameTable(NetBoxTable):
    hostname = tables.Column(linkify=True)
    tunnel = tables.Column(linkify=True)
    exposure = columns.ChoiceFieldColumn()
    service = tables.Column(linkify=True)
    proxy_service = tables.Column(linkify=True, verbose_name="Nginx vhost")

    class Meta(NetBoxTable.Meta):
        model = PublicHostname
        fields = (
            "pk",
            "id",
            "hostname",
            "path",
            "tunnel",
            "origin",
            "exposure",
            "proxy_service",
            "upstream",
            "service",
            "resolution",
            "tags",
        )
        default_columns = ("hostname", "path", "tunnel", "origin", "exposure", "proxy_service", "service", "resolution")
