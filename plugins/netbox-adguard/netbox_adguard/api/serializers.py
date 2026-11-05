from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import DNSRewrite


class DNSRewriteSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_adguard-api:dnsrewrite-detail")

    class Meta:
        model = DNSRewrite
        fields = (
            "id",
            "url",
            "display",
            "instance",
            "domain",
            "answer",
            "answer_type",
            "enabled",
            "ip_address",
            "virtual_machine",
            "device",
            "dns_record_id",
            "resolution",
            "tags",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "domain", "answer")
