"""MCP tools exposed to Claude. All read-only, all limited to what the token's user may view."""

import json

from django.apps import apps
from netbox.plugins import get_plugin_config
from netbox_cmdb import inventory

PLUGIN = "netbox_cmdb_mcp"


def _str(desc, **extra):
    return {"type": "string", "description": desc, **extra}


def _int(desc, **extra):
    return {"type": "integer", "description": desc, **extra}


def _schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


def t_overview(user, **_):
    return inventory.overview(user)


def t_search(user, query, **_):
    return inventory.search(user, query) or {"result": f"nothing matches {query!r}"}


def t_list_hosts(user, cluster=None, status=None, name_contains=None, **_):
    return inventory.list_hosts(user, cluster=cluster, status=status, search=name_contains)


def t_get_host(user, host, **_):
    obj = inventory.find_host(user, host)
    if obj is None:
        return {"error": f"host {host!r} not found (try search)"}
    return inventory.host_detail(obj, user)


def t_list_used_ports(user, host, **_):
    obj = inventory.find_host(user, host)
    if obj is None:
        return {"error": f"host {host!r} not found (try search)"}
    return {"host": obj.name, "ports": inventory.used_ports(obj, user)}


def t_check_port(user, host, port, protocol="tcp", **_):
    return inventory.check_port(user, host, port, protocol)


def t_find_free_ports(user, host, start=8000, end=9000, count=5, protocol="tcp", **_):
    return inventory.find_free_ports(user, host, start, end, count, protocol)


def t_check_ip(user, address, **_):
    return inventory.check_ip(user, address)


def t_find_free_ips(user, prefix=None, count=5, **_):
    prefix = prefix or get_plugin_config(PLUGIN, "default_prefix")
    reserved = get_plugin_config(PLUGIN, "reserved_ip_ranges") or []
    result = inventory.find_free_ips(user, prefix, count, reserved)
    if reserved:
        result["reserved_ranges_excluded"] = reserved
    return result


def t_list_public_urls(user, **_):
    return inventory.public_urls(user)


def t_list_dns_names(user, contains=None, **_):
    names = inventory.dns_names(user)
    return [n for n in names if not contains or contains.lower() in n["name"].lower()]


def t_list_containers(user, host=None, stack=None, **_):
    if not inventory.docker_installed():
        return {"error": "Docker inventory plugin not installed"}
    return inventory.containers(user, host=host, stack=stack)


def t_export(user, format="md", containers=False, **_):
    if not apps.is_installed("netbox_cmdb_export"):
        return {"error": "export plugin not installed"}
    if format not in ("md", "mmd", "json"):
        return {"error": "format must be md, mmd (Mermaid) or json"}
    from netbox_cmdb_export.exporter import export

    body, _, _ = export(user, format, containers=bool(containers))
    return body


TOOLS = {
    "cmdb_overview": (
        t_overview,
        "Summary of the homelab CMDB: clusters, object counts, health of each automatic source.",
        _schema(),
    ),
    "search": (
        t_search,
        "Free-text search across hosts (VMs, LXC, devices), IP addresses, services, DNS names and containers.",
        _schema({"query": _str("Name, IP, domain or image fragment")}, ["query"]),
    ),
    "list_hosts": (
        t_list_hosts,
        "List hosts (VMs, LXC containers, physical devices) with type, status, cluster, node and primary IP.",
        _schema(
            {
                "cluster": _str("Only hosts of this cluster"),
                "status": _str("NetBox status, e.g. active, offline"),
                "name_contains": _str("Name filter"),
            }
        ),
    ),
    "get_host": (
        t_get_host,
        "Everything known about one host: IPs, local/public names, services, ports in use, containers, custom "
        "fields (Portainer stack, backups).",
        _schema({"host": _str("Host name, short name, DNS name or IP")}, ["host"]),
    ),
    "list_used_ports": (
        t_list_used_ports,
        "Ports in use on a host, with what uses them (NetBox services, Docker published ports, network scan).",
        _schema({"host": _str("Host name or IP")}, ["host"]),
    ),
    "check_port": (
        t_check_port,
        "Is a port free on a host? Returns available=true/false and what uses it.",
        _schema(
            {
                "host": _str("Host name or IP"),
                "port": _int("Port number", minimum=1, maximum=65535),
                "protocol": _str("tcp or udp", enum=["tcp", "udp"], default="tcp"),
            },
            ["host", "port"],
        ),
    ),
    "find_free_ports": (
        t_find_free_ports,
        "Propose free ports on a host within a range.",
        _schema(
            {
                "host": _str("Host name or IP"),
                "start": _int("Range start", default=8000),
                "end": _int("Range end", default=9000),
                "count": _int("How many ports", default=5, minimum=1, maximum=50),
                "protocol": _str("tcp or udp", enum=["tcp", "udp"], default="tcp"),
            },
            ["host"],
        ),
    ),
    "check_ip": (
        t_check_ip,
        "Is an IP address used? Returns the NetBox records, the host it belongs to and DNS rewrites.",
        _schema({"address": _str("IPv4/IPv6 address")}, ["address"]),
    ),
    "find_free_ips": (
        t_find_free_ips,
        "Propose IP addresses unknown to the CMDB in a prefix (excludes IPAM, scan results, DNS rewrites, reserved "
        "ranges, the gateway).",
        _schema(
            {
                "prefix": _str("CIDR, default: the LAN prefix"),
                "count": _int("How many", default=5, minimum=1, maximum=100),
            }
        ),
    ),
    "list_public_urls": (
        t_list_public_urls,
        "Public URLs (Cloudflare Tunnel) with their exposure path (cloudflared direct / via Nginx) and target service.",
        _schema(),
    ),
    "list_dns_names": (
        t_list_dns_names,
        "Local (AdGuard rewrites) and public DNS names with what they point to.",
        _schema({"contains": _str("Name filter")}),
    ),
    "list_containers": (
        t_list_containers,
        "Docker containers (including ones without network traffic) with stack, image, state, published ports, "
        "internal networks and volumes.",
        _schema({"host": _str("Docker host / VM name"), "stack": _str("Compose project / Portainer stack")}),
    ),
    "export": (
        t_export,
        "Export the whole CMDB as Markdown (md), a Mermaid topology graph (mmd) or JSON.",
        _schema(
            {
                "format": _str("md, mmd or json", enum=["md", "mmd", "json"], default="md"),
                "containers": {"type": "boolean", "description": "Graph: one node per container", "default": False},
            }
        ),
    ),
}


def list_tools():
    return [
        {"name": name, "description": desc, "inputSchema": schema, "annotations": {**READ_ONLY, "title": name}}
        for name, (_, desc, schema) in TOOLS.items()
    ]


def call_tool(user, name, arguments):
    """Returns (text, is_error)."""
    if name not in TOOLS:
        raise KeyError(name)
    func, _, schema = TOOLS[name]
    arguments = dict(arguments or {})
    missing = [r for r in schema["required"] if arguments.get(r) in (None, "")]
    if missing:
        return f"missing argument(s): {', '.join(missing)}", True
    unknown = set(arguments) - set(schema["properties"])
    for key in unknown:
        arguments.pop(key)
    try:
        result = func(user, **arguments)
    except (ValueError, TypeError) as exc:
        return f"invalid argument: {exc}", True
    if isinstance(result, str):
        return result, False
    is_error = isinstance(result, dict) and "error" in result and len(result) == 1
    return json.dumps(result, indent=1, default=str, ensure_ascii=False), is_error
