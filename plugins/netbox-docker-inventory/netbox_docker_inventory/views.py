from django.db.models import Count
from netbox.object_actions import BulkDelete, BulkExport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, tables
from .models import DockerContainer, DockerHost, DockerNetwork


def _register(model, table, filterset, filterset_form, queryset=None, detail_context=None):
    """Read-only list / detail / delete views (data comes from the agent)."""
    qs = queryset if queryset is not None else model.objects.all()

    class ListView(generic.ObjectListView):
        queryset = qs
        actions = (BulkExport, BulkDelete)

    ListView.table = table
    ListView.filterset = filterset
    ListView.filterset_form = filterset_form

    class DetailView(generic.ObjectView):
        queryset = model.objects.all()
        actions = (DeleteObject,)

        def get_extra_context(self, request, instance):
            return detail_context(request, instance) if detail_context else {}

    class DeleteView(generic.ObjectDeleteView):
        queryset = model.objects.all()

    class BulkDeleteView(generic.BulkDeleteView):
        queryset = model.objects.all()

    BulkDeleteView.filterset = filterset
    BulkDeleteView.table = table

    register_model_view(model, "list", path="", detail=False)(ListView)
    register_model_view(model)(DetailView)
    register_model_view(model, "delete")(DeleteView)
    register_model_view(model, "bulk_delete", path="delete", detail=False)(BulkDeleteView)


def _host_context(request, instance):
    containers = tables.DockerContainerTable(instance.containers.all(), exclude=("host",))
    containers.configure(request)
    networks = tables.DockerNetworkTable(instance.networks.all(), exclude=("host",))
    networks.configure(request)
    return {"containers_table": containers, "networks_table": networks}


def _network_context(request, instance):
    containers = tables.DockerContainerTable(instance.containers.all())
    containers.configure(request)
    rows = []
    for c in instance.containers.all():
        for att in c.network_attachments or []:
            if att.get("network") == instance.name:
                rows.append((c, att.get("ip"), ", ".join(att.get("aliases") or [])))
    return {"containers_table": containers, "attachments": rows}


_register(
    DockerHost,
    tables.DockerHostTable,
    filtersets.DockerHostFilterSet,
    forms.DockerHostFilterForm,
    DockerHost.objects.annotate(container_count=Count("containers")),
    _host_context,
)
_register(
    DockerNetwork,
    tables.DockerNetworkTable,
    filtersets.DockerNetworkFilterSet,
    forms.DockerNetworkFilterForm,
    DockerNetwork.objects.select_related("host").annotate(container_count=Count("containers")),
    _network_context,
)
_register(
    DockerContainer,
    tables.DockerContainerTable,
    filtersets.DockerContainerFilterSet,
    forms.DockerContainerFilterForm,
    DockerContainer.objects.select_related("host", "service"),
)
