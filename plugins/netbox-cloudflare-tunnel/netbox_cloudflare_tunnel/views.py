from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count
from django.shortcuts import redirect
from django.views import View
from netbox.object_actions import BulkDelete, BulkExport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, tables
from .models import PublicHostname, Tunnel


@register_model_view(Tunnel, "list", path="", detail=False)
class TunnelListView(generic.ObjectListView):
    queryset = Tunnel.objects.annotate(hostname_count=Count("hostnames"))
    table = tables.TunnelTable
    filterset = filtersets.TunnelFilterSet
    filterset_form = forms.TunnelFilterForm
    actions = (BulkExport, BulkDelete)
    template_name = "netbox_cloudflare_tunnel/tunnel_list.html"


@register_model_view(Tunnel)
class TunnelView(generic.ObjectView):
    queryset = Tunnel.objects.all()
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        table = tables.PublicHostnameTable(instance.hostnames.all())
        table.configure(request)
        return {"hostnames_table": table}


@register_model_view(Tunnel, "delete")
class TunnelDeleteView(generic.ObjectDeleteView):
    queryset = Tunnel.objects.all()


@register_model_view(Tunnel, "bulk_delete", path="delete", detail=False)
class TunnelBulkDeleteView(generic.BulkDeleteView):
    queryset = Tunnel.objects.all()
    filterset = filtersets.TunnelFilterSet
    table = tables.TunnelTable


@register_model_view(PublicHostname, "list", path="", detail=False)
class PublicHostnameListView(generic.ObjectListView):
    queryset = PublicHostname.objects.select_related("tunnel", "service", "proxy_service")
    table = tables.PublicHostnameTable
    filterset = filtersets.PublicHostnameFilterSet
    filterset_form = forms.PublicHostnameFilterForm
    actions = (BulkExport, BulkDelete)
    template_name = "netbox_cloudflare_tunnel/tunnel_list.html"


@register_model_view(PublicHostname)
class PublicHostnameView(generic.ObjectView):
    queryset = PublicHostname.objects.all()
    actions = (DeleteObject,)


@register_model_view(PublicHostname, "delete")
class PublicHostnameDeleteView(generic.ObjectDeleteView):
    queryset = PublicHostname.objects.all()


@register_model_view(PublicHostname, "bulk_delete", path="delete", detail=False)
class PublicHostnameBulkDeleteView(generic.BulkDeleteView):
    queryset = PublicHostname.objects.all()
    filterset = filtersets.PublicHostnameFilterSet
    table = tables.PublicHostnameTable


class SyncNowView(PermissionRequiredMixin, View):
    """Queue an immediate Cloudflare sync (in addition to the daily schedule)."""

    permission_required = "netbox_cloudflare_tunnel.change_tunnel"

    def post(self, request):
        from .jobs import CloudflareSyncJob

        job = CloudflareSyncJob.enqueue(user=request.user)
        messages.success(request, f"Cloudflare sync queued (job #{job.pk}).")
        return redirect(job.get_absolute_url())
