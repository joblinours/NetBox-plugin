"""MCP "streamable HTTP" transport, stateless, JSON responses only.

POST /api/plugins/mcp/  with a JSON-RPC 2.0 message (or batch). Authentication is
the usual NetBox API token (``Authorization: Bearer nbt_...``); every tool runs with
that user's view permissions. GET / DELETE are not supported (no server-initiated
stream, no session), which the specification allows.
"""

import logging

from django.http import HttpResponse, JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .. import __version__
from ..tools import call_tool, list_tools

logger = logging.getLogger("netbox.plugins.netbox_cmdb_mcp")

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "Read-only access to the homelab CMDB (NetBox). Use it before deploying something to know which hosts exist, "
    "which IPs and ports are taken or free, which public URLs and local DNS names exist, and which Docker "
    "containers/stacks/networks run where. Start with cmdb_overview or search; use check_port / find_free_ports / "
    "check_ip / find_free_ips before choosing a port or an IP. Data is as fresh as the last sync (daily)."
)

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def handle_message(user, msg):
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications/responses."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(msg.get("id") if isinstance(msg, dict) else None, INVALID_REQUEST, "invalid JSON-RPC message")
    method = msg.get("method")
    msg_id = msg.get("id")
    if method is None:  # a response from the client: nothing to do
        return None
    is_notification = "id" not in msg
    params = msg.get("params") or {}
    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
            result = {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "netbox-cmdb", "title": "Homelab CMDB (NetBox)", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            try:
                text, is_error = call_tool(user, name, params.get("arguments") or {})
            except KeyError:
                return _error(msg_id, INVALID_PARAMS, f"unknown tool {name!r}")
            result = {"content": [{"type": "text", "text": text}], "isError": is_error}
        elif method in ("resources/list", "resources/templates/list"):
            result = {"resources": []} if method == "resources/list" else {"resourceTemplates": []}
        elif method == "prompts/list":
            result = {"prompts": []}
        elif method.startswith("notifications/"):
            return None
        else:
            return None if is_notification else _error(msg_id, METHOD_NOT_FOUND, f"method {method!r} not found")
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP %s failed", method)
        return None if is_notification else _error(msg_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
    return None if is_notification else _result(msg_id, result)


class MCPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data
        if isinstance(payload, list):
            if not payload:
                return JsonResponse(_error(None, INVALID_REQUEST, "empty batch"), status=400)
            responses = [r for r in (handle_message(request.user, m) for m in payload) if r is not None]
            return JsonResponse(responses, safe=False) if responses else HttpResponse(status=202)
        if not isinstance(payload, dict):
            return JsonResponse(_error(None, PARSE_ERROR, "body must be a JSON-RPC object"), status=400)
        response = handle_message(request.user, payload)
        if response is None:
            return HttpResponse(status=202)
        resp = JsonResponse(response)
        resp["MCP-Protocol-Version"] = request.headers.get("MCP-Protocol-Version", SUPPORTED_VERSIONS[0])
        return resp

    def get(self, request):
        resp = HttpResponse("This MCP server does not offer a server-to-client stream.", status=405)
        resp["Allow"] = "POST"
        return resp

    def delete(self, request):
        return HttpResponse(status=405)
