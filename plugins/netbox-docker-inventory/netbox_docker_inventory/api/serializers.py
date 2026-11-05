from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import DockerContainer, DockerHost, DockerNetwork

NS = "plugins-api:netbox_docker_inventory-api"


class DockerHostSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=f"{NS}:dockerhost-detail")

    class Meta:
        model = DockerHost
        fields = (
            "id",
            "url",
            "display",
            "name",
            "virtual_machine",
            "device",
            "hostname",
            "engine_version",
            "operating_system",
            "agent_version",
            "addresses",
            "last_seen",
            "tags",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class DockerNetworkSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=f"{NS}:dockernetwork-detail")
    host = DockerHostSerializer(nested=True, read_only=True)

    class Meta:
        model = DockerNetwork
        fields = (
            "id",
            "url",
            "display",
            "host",
            "network_id",
            "name",
            "driver",
            "scope",
            "internal",
            "subnets",
            "gateways",
            "stack",
            "tags",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class DockerContainerSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name=f"{NS}:dockercontainer-detail")
    host = DockerHostSerializer(nested=True, read_only=True)
    networks = DockerNetworkSerializer(nested=True, many=True, read_only=True)

    class Meta:
        model = DockerContainer
        fields = (
            "id",
            "url",
            "display",
            "host",
            "container_id",
            "name",
            "image",
            "state",
            "status",
            "health",
            "stack",
            "compose_service",
            "restart_policy",
            "network_mode",
            "created_at",
            "ports",
            "network_attachments",
            "mounts",
            "labels",
            "networks",
            "service",
            "tags",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "state")
