from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views import View
from django.views.generic import TemplateView

from . import render
from .collect import collect
from .exporter import FORMATS, http_response


class ExportHomeView(LoginRequiredMixin, TemplateView):
    template_name = "netbox_cmdb_export/export.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        graph = render.build_graph(collect(self.request.user), containers=self.request.GET.get("containers") == "1")
        ctx["mermaid"] = render.to_mermaid(graph)
        ctx["containers"] = self.request.GET.get("containers") == "1"
        return ctx


class ExportFileView(LoginRequiredMixin, View):
    def get(self, request, fmt):
        if fmt not in FORMATS:
            raise Http404
        return http_response(
            request.user, fmt, request.GET.get("containers") == "1", inline=request.GET.get("inline") == "1"
        )
