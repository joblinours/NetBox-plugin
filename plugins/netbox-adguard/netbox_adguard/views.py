from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import redirect
from django.views import View
from netbox.object_actions import BulkDelete, BulkExport, DeleteObject
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, tables
from .models import DNSRewrite


@register_model_view(DNSRewrite, "list", path="", detail=False)
class DNSRewriteListView(generic.ObjectListView):
    queryset = DNSRewrite.objects.select_related("ip_address", "virtual_machine", "device")
    table = tables.DNSRewriteTable
    filterset = filtersets.DNSRewriteFilterSet
    filterset_form = forms.DNSRewriteFilterForm
    actions = (BulkExport, BulkDelete)
    template_name = "netbox_adguard/dnsrewrite_list.html"


@register_model_view(DNSRewrite)
class DNSRewriteView(generic.ObjectView):
    queryset = DNSRewrite.objects.all()
    actions = (DeleteObject,)


@register_model_view(DNSRewrite, "delete")
class DNSRewriteDeleteView(generic.ObjectDeleteView):
    queryset = DNSRewrite.objects.all()


@register_model_view(DNSRewrite, "bulk_delete", path="delete", detail=False)
class DNSRewriteBulkDeleteView(generic.BulkDeleteView):
    queryset = DNSRewrite.objects.all()
    filterset = filtersets.DNSRewriteFilterSet
    table = tables.DNSRewriteTable


class SyncNowView(PermissionRequiredMixin, View):
    permission_required = "netbox_adguard.change_dnsrewrite"

    def post(self, request):
        from .jobs import AdGuardSyncJob

        job = AdGuardSyncJob.enqueue(user=request.user)
        messages.success(request, f"AdGuard sync queued (job #{job.pk}).")
        return redirect(job.get_absolute_url())
