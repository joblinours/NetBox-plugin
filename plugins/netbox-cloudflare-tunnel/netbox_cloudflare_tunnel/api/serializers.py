from ipam.api.serializers import ServiceSerializer
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import PublicHostname, Tunnel


class TunnelSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_cloudflare_tunnel-api:tunnel-detail")

    class Meta:
        model = Tunnel
        fields = (
            "id",
            "url",
            "display",
            "tunnel_id",
            "name",
            "account_id",
            "status",
            "remote_config",
            "last_synced",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "tunnel_id")


class PublicHostnameSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_cloudflare_tunnel-api:publichostname-detail"
    )
    tunnel = TunnelSerializer(nested=True, read_only=True)
    service = ServiceSerializer(nested=True, read_only=True, allow_null=True)
    proxy_service = ServiceSerializer(nested=True, read_only=True, allow_null=True)

    class Meta:
        model = PublicHostname
        fields = (
            "id",
            "url",
            "display",
            "tunnel",
            "hostname",
            "path",
            "origin",
            "origin_scheme",
            "origin_host",
            "origin_port",
            "exposure",
            "service",
            "proxy_service",
            "upstream",
            "resolution",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "hostname", "path", "exposure")
