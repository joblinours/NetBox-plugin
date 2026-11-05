import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from .models import DNSRewrite


class DNSRewriteTable(NetBoxTable):
    actions = columns.ActionsColumn(actions=("delete", "changelog"))
    domain = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True, verbose_name="VM")
    device = tables.Column(linkify=True)
    enabled = tables.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = DNSRewrite
        fields = (
            "pk",
            "id",
            "domain",
            "answer",
            "answer_type",
            "enabled",
            "ip_address",
            "virtual_machine",
            "device",
            "instance",
            "resolution",
            "tags",
        )
        default_columns = (
            "domain",
            "answer",
            "answer_type",
            "enabled",
            "ip_address",
            "virtual_machine",
            "device",
            "resolution",
        )
