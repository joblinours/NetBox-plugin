from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from .health import build_health
from .models import SourceStatus
from .syncs import enqueue_all


class SourceStatusListView(PermissionRequiredMixin, TemplateView):
    permission_required = "netbox_cmdb.view_sourcestatus"
    template_name = "netbox_cmdb/sourcestatus_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["health"] = build_health()
        ctx["ids"] = dict(SourceStatus.objects.values_list("name", "pk"))
        return ctx


class RunSyncsView(PermissionRequiredMixin, View):
    """Queue an immediate run of the Proxmox, Cloudflare and AdGuard syncs."""

    permission_required = "netbox_cmdb.change_sourcestatus"

    def post(self, request):
        queued = enqueue_all(user=request.user)
        if queued:
            messages.success(request, f"Queued: {', '.join(queued)}. Refresh this page in a minute.")
        else:
            messages.info(request, "Nothing queued: no sync configured, or a run is already waiting.")
        return redirect("plugins:netbox_cmdb:sourcestatus_list")


class ForgetSourceView(PermissionRequiredMixin, View):
    """Delete the status of a source that no longer exists (e.g. a renamed Docker host)."""

    permission_required = "netbox_cmdb.delete_sourcestatus"

    def post(self, request, pk):
        status = get_object_or_404(SourceStatus, pk=pk)
        name = status.name
        status.delete()
        messages.success(request, f"Source {name} forgotten. It reappears if it reports again.")
        return redirect("plugins:netbox_cmdb:sourcestatus_list")
