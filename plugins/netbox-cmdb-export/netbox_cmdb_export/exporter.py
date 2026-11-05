"""One entry point for every export format (used by the UI, the REST API and the MCP server)."""

import json

from django.http import HttpResponse
from django.utils import timezone

from . import render
from .collect import collect

FORMATS = {
    "md": "text/markdown; charset=utf-8",
    "pdf": "application/pdf",
    "json": "application/json",
    "mmd": "text/plain; charset=utf-8",
    "dot": "text/plain; charset=utf-8",
    "png": "image/png",
    "svg": "image/svg+xml",
}


def export(user, fmt, containers=False):
    """Return (bytes or str, content type, file name)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}")
    data = collect(user)
    stamp = timezone.now().strftime("%Y%m%d-%H%M")
    name = f"cmdb-{stamp}.{fmt}" if fmt in ("md", "pdf", "json") else f"cmdb-topology-{stamp}.{fmt}"
    if fmt == "md":
        body = render.to_markdown(data)
    elif fmt == "pdf":
        body = render.to_pdf(data)
    elif fmt == "json":
        body = json.dumps(data, indent=2, default=str)
    else:
        graph = render.build_graph(data, containers=containers)
        if fmt == "mmd":
            body = render.to_mermaid(graph)
        else:
            dot = render.to_dot(graph, f"{data['title']} — {data['generated']}")
            body = dot if fmt == "dot" else render.render_dot(dot, fmt)
    return body, FORMATS[fmt], name


def http_response(user, fmt, containers=False, inline=False):
    try:
        body, content_type, name = export(user, fmt, containers)
    except ValueError as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain")
    except render.GraphvizMissing as exc:
        return HttpResponse(str(exc), status=501, content_type="text/plain")
    resp = HttpResponse(body, content_type=content_type)
    disposition = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f'{disposition}; filename="{name}"'
    return resp
