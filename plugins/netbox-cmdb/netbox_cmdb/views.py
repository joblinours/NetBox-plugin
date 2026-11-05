from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import TemplateView

from .health import build_health


class SourceStatusListView(PermissionRequiredMixin, TemplateView):
    permission_required = "netbox_cmdb.view_sourcestatus"
    template_name = "netbox_cmdb/sourcestatus_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["health"] = build_health()
        return ctx
