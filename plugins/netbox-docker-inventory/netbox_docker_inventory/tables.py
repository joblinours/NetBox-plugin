import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .models import DockerContainer, DockerHost, DockerNetwork


class DockerHostTable(NetBoxTable):
    actions = columns.ActionsColumn(actions=("delete", "changelog"))
    name = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    device = tables.Column(linkify=True)
    container_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_docker_inventory:dockercontainer_list",
        url_params={"host_id": "pk"},
        verbose_name="Containers",
    )

    class Meta(NetBoxTable.Meta):
        model = DockerHost
        fields = (
            "pk",
            "id",
            "name",
            "virtual_machine",
            "device",
            "engine_version",
            "operating_system",
            "container_count",
            "agent_version",
            "last_seen",
            "tags",
        )
        default_columns = ("name", "virtual_machine", "device", "engine_version", "container_count", "last_seen")


class DockerNetworkTable(NetBoxTable):
    actions = columns.ActionsColumn(actions=("delete", "changelog"))
    name = tables.Column(linkify=True)
    host = tables.Column(linkify=True)
    subnets = tables.TemplateColumn("{{ value|join:', ' }}")
    container_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_docker_inventory:dockercontainer_list",
        url_params={"network_id": "pk"},
        verbose_name="Containers",
    )

    class Meta(NetBoxTable.Meta):
        model = DockerNetwork
        fields = (
            "pk",
            "id",
            "name",
            "host",
            "stack",
            "driver",
            "scope",
            "internal",
            "subnets",
            "container_count",
            "tags",
        )
        default_columns = ("name", "host", "stack", "driver", "internal", "subnets", "container_count")


class DockerContainerTable(NetBoxTable):
    actions = columns.ActionsColumn(actions=("delete", "changelog"))
    name = tables.Column(linkify=True)
    host = tables.Column(linkify=True)
    state = tables.TemplateColumn(
        '<span class="badge text-bg-{% if value == "running" %}success{% elif value == "exited" %}danger'
        '{% else %}secondary{% endif %}">{{ value }}</span>'
    )
    ports_display = tables.Column(verbose_name="Ports", orderable=False)
    service = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = DockerContainer
        fields = (
            "pk",
            "id",
            "name",
            "host",
            "stack",
            "compose_service",
            "image",
            "state",
            "health",
            "status",
            "ports_display",
            "network_mode",
            "restart_policy",
            "service",
            "tags",
        )
        default_columns = ("name", "host", "stack", "image", "state", "ports_display", "network_mode")
