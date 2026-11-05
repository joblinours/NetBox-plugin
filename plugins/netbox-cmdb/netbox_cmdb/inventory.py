"""Read-only inventory helpers shared by the MCP and export plugins.

Every function takes the requesting ``user`` and only returns objects that user
may view (NetBox object permissions, ``.restrict(user, "view")``).

A "host" is a NetBox virtual machine (VM or LXC) or device.
"""

import ipaddress
import json
import re

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q


def _restrict(qs, user):
    return qs.restrict(user, "view") if user is not None else qs


def _models():
    from dcim.models import Device
    from ipam.models import IPAddress, Service
    from virtualization.models import VirtualMachine

    return Device, VirtualMachine, IPAddress, Service


def docker_installed():
    return apps.is_installed("netbox_docker_inventory")


def adguard_installed():
    return apps.is_installed("netbox_adguard")


def cloudflare_installed():
    return apps.is_installed("netbox_cloudflare_tunnel")


# --------------------------------------------------------------------------- hosts


def host_kind(obj):
    from virtualization.models import VirtualMachine

    if isinstance(obj, VirtualMachine):
        return "lxc" if "lxc" in (obj.description or "").lower() or _is_lxc(obj) else "vm"
    return "device"


def _is_lxc(vm):
    tags = {t.lower() for t in vm.tags.names()} if hasattr(vm, "tags") else set()
    return "lxc" in tags or (vm.platform and "lxc" in vm.platform.name.lower())


def find_host(user, name_or_ip):
    """Find a VM or device by name (case-insensitive, short name accepted) or by one of its IPs."""
    Device, VirtualMachine, IPAddress, _ = _models()
    value = (name_or_ip or "").strip()
    if not value:
        return None
    try:
        ipaddress.ip_address(value)
        ip = _restrict(IPAddress.objects.filter(address__net_host=value), user).first()
        return parent_of_ip(ip) if ip else None
    except ValueError:
        pass
    for model in (VirtualMachine, Device):
        qs = _restrict(model.objects.all(), user)
        obj = qs.filter(name__iexact=value).first() or qs.filter(name__iexact=value.split(".")[0]).first()
        if obj:
            return obj
    ip = _restrict(IPAddress.objects.filter(dns_name__iexact=value), user).first()
    if ip and parent_of_ip(ip):
        return parent_of_ip(ip)
    if adguard_installed():  # local DNS name (AdGuard rewrite)
        from netbox_adguard.models import DNSRewrite

        rewrite = _restrict(DNSRewrite.objects.filter(domain__iexact=value), user).first()
        if rewrite and rewrite.host:
            return rewrite.host
    if cloudflare_installed():  # public hostname
        from netbox_cloudflare_tunnel.models import PublicHostname

        public = _restrict(PublicHostname.objects.filter(hostname__iexact=value), user).first()
        if public and public.service and public.service.parent:
            return public.service.parent
    return None


def parent_of_ip(ip):
    obj = ip.assigned_object if ip else None
    if obj is None:
        return None
    return getattr(obj, "device", None) or getattr(obj, "virtual_machine", None)


def host_ips(host, user=None):
    _, VirtualMachine, IPAddress, _ = _models()
    if isinstance(host, VirtualMachine):
        qs = IPAddress.objects.filter(vminterface__virtual_machine=host)
    else:
        qs = IPAddress.objects.filter(interface__device=host)
    return list(_restrict(qs, user).distinct())


def host_services(host, user=None):
    _, _, _, Service = _models()
    ct = ContentType.objects.get_for_model(host)
    return list(_restrict(Service.objects.filter(parent_object_type=ct, parent_object_id=host.pk), user))


def list_hosts(user, cluster=None, status=None, search=None):
    Device, VirtualMachine, _, _ = _models()
    out = []
    vms = _restrict(VirtualMachine.objects.select_related("cluster", "primary_ip4"), user)
    devices = _restrict(Device.objects.select_related("site", "primary_ip4", "role"), user)
    if cluster:
        vms = vms.filter(cluster__name__iexact=cluster)
        devices = devices.filter(cluster__name__iexact=cluster)
    if status:
        vms = vms.filter(status=status)
        devices = devices.filter(status=status)
    if search:
        vms = vms.filter(name__icontains=search)
        devices = devices.filter(name__icontains=search)
    for vm in vms:
        out.append(host_summary(vm))
    for dev in devices:
        out.append(host_summary(dev))
    return sorted(out, key=lambda h: h["name"].lower())


def host_summary(host):
    from virtualization.models import VirtualMachine

    is_vm = isinstance(host, VirtualMachine)
    ip = host.primary_ip4 or host.primary_ip
    return {
        "name": host.name,
        "type": host_kind(host) if is_vm else "device",
        "status": str(host.status),
        "cluster": host.cluster.name if getattr(host, "cluster", None) else None,
        "node": host.device.name if is_vm and host.device else None,
        "primary_ip": str(ip.address.ip) if ip else None,
        "url": host.get_absolute_url(),
    }


def host_detail(host, user=None):
    data = host_summary(host)
    data["description"] = host.description
    data["custom_fields"] = {k: v for k, v in (host.custom_field_data or {}).items() if v not in (None, "", [])}
    data["tags"] = list(host.tags.names())
    from virtualization.models import VirtualMachine

    if isinstance(host, VirtualMachine):
        data.update({"vcpus": host.vcpus and float(host.vcpus), "memory_mb": host.memory, "disk_mb": host.disk})
    data["ip_addresses"] = [ip_summary(ip) for ip in host_ips(host, user)]
    data["ports_in_use"] = used_ports(host, user)
    data["services"] = [service_summary(s) for s in host_services(host, user)]
    if docker_installed():
        data["containers"] = [c for c in containers(user, host=host.name)]
    return data


# --------------------------------------------------------------------------- IPs


def ip_summary(ip):
    parent = parent_of_ip(ip)
    return {
        "address": str(ip.address),
        "dns_name": ip.dns_name or None,
        "status": str(ip.status),
        "assigned_to": parent.name if parent else None,
        "description": ip.description or None,
        "local_domains": (ip.custom_field_data or {}).get("local_domains") or None,
        "scan_open_ports": scan_open_ports(ip),
    }


def scan_open_ports(ip):
    """Open ports recorded by the orb-agent network scan (JSON in the IP comments)."""
    text = (ip.comments or "").strip()
    if not text.startswith("{"):
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return sorted(
        {
            (p.get("protocol", "tcp"), int(p["number"]))
            for p in data.get("ports") or []
            if p.get("state") == "open" and str(p.get("number", "")).isdigit()
        }
    )


def check_ip(user, address):
    _, _, IPAddress, _ = _models()
    addr = str(ipaddress.ip_interface(address).ip) if "/" in address else str(ipaddress.ip_address(address))
    ips = list(_restrict(IPAddress.objects.filter(address__net_host=addr), user))
    result = {"address": addr, "in_netbox": bool(ips), "records": [ip_summary(ip) for ip in ips]}
    if adguard_installed():
        from netbox_adguard.models import DNSRewrite

        result["dns_rewrites"] = list(
            _restrict(DNSRewrite.objects.filter(answer=addr), user).values_list("domain", flat=True)
        )
    result["available"] = not ips and not result.get("dns_rewrites")
    return result


def find_free_ips(user, prefix, count=5, reserved=()):
    """IPs of ``prefix`` that NetBox does not know (not in IPAM, not a DNS rewrite answer)."""
    _, _, IPAddress, _ = _models()
    net = ipaddress.ip_network(prefix, strict=False)
    used = {
        str(ip.address.ip) for ip in _restrict(IPAddress.objects.filter(address__net_host_contained=str(net)), user)
    }
    if adguard_installed():
        from netbox_adguard.models import DNSRewrite

        used |= set(DNSRewrite.objects.values_list("answer", flat=True))
    reserved_ips = set()
    for item in reserved:
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start, end = (ipaddress.ip_address(x.strip()) for x in item.split("-", 1))
            reserved_ips |= {str(ipaddress.ip_address(i)) for i in range(int(start), int(end) + 1)}
        else:
            reserved_ips |= {str(h) for h in ipaddress.ip_network(item, strict=False)}
    free = []
    hosts = net.hosts()
    first = next(net.hosts(), None)
    for host in hosts:
        h = str(host)
        if h in used or h in reserved_ips or host == first:  # .1 = gateway by convention
            continue
        free.append(h)
        if len(free) >= count:
            break
    return {
        "prefix": str(net),
        "known_used": len(used),
        "free": free,
        "note": "Free = unknown to NetBox (IPAM, network scan, DNS rewrites). The first host address is "
        "treated as the gateway. Verify with a ping before use.",
    }


# --------------------------------------------------------------------------- ports


def _service_ports(service):
    out = []
    for mapping in service.port_mappings or []:
        proto, _, port = mapping.partition("/")
        if port.isdigit():
            out.append((proto or "tcp", int(port)))
    return out


def used_ports(host, user=None):
    """Every port known as used on ``host``: NetBox services, Docker published ports, scan results."""
    ports = {}

    def add(proto, port, source, detail):
        ports.setdefault((proto, port), []).append({"source": source, "detail": detail})

    for svc in host_services(host, user):
        for proto, port in _service_ports(svc):
            add(proto, port, "service", svc.name)
    for ip in host_ips(host, user):
        for proto, port in scan_open_ports(ip):
            add(proto, port, "network-scan", str(ip.address.ip))
    if docker_installed():
        from netbox_docker_inventory.models import DockerContainer
        from virtualization.models import VirtualMachine

        field = "host__virtual_machine" if isinstance(host, VirtualMachine) else "host__device"
        qs = DockerContainer.objects.filter(**{field: host})
        for c in qs:
            for p in c.ports or []:
                if p.get("public_port"):
                    add(p.get("type", "tcp"), int(p["public_port"]), "docker", f"{c.name} -> {p.get('private_port')}")
    return [
        {"protocol": proto, "port": port, "used_by": used_by}
        for (proto, port), used_by in sorted(ports.items(), key=lambda i: (i[0][1], i[0][0]))
    ]


def check_port(user, host_name, port, protocol="tcp"):
    host = find_host(user, host_name)
    if host is None:
        return {"error": f"host {host_name!r} not found in the CMDB"}
    users = [p for p in used_ports(host, user) if p["port"] == int(port) and p["protocol"] == protocol]
    return {
        "host": host.name,
        "protocol": protocol,
        "port": int(port),
        "available": not users,
        "used_by": users[0]["used_by"] if users else [],
    }


def find_free_ports(user, host_name, start=8000, end=9000, count=5, protocol="tcp"):
    host = find_host(user, host_name)
    if host is None:
        return {"error": f"host {host_name!r} not found in the CMDB"}
    used = {p["port"] for p in used_ports(host, user) if p["protocol"] == protocol}
    free = [p for p in range(int(start), int(end) + 1) if p not in used][: int(count)]
    return {"host": host.name, "protocol": protocol, "range": [int(start), int(end)], "free": free}


# --------------------------------------------------------------------------- services, URLs, DNS


def service_summary(svc):
    cf = svc.custom_field_data or {}
    return {
        "name": svc.name,
        "host": svc.parent.name if svc.parent else None,
        "ports": svc.port_mappings,
        "public_url": cf.get("public_url"),
        "exposure_path": cf.get("exposure_path"),
        "upstream_target": cf.get("upstream_target"),
        "portainer_stack": cf.get("portainer_stack"),
        "description": svc.description or None,
    }


def public_urls(user):
    if not cloudflare_installed():
        return []
    from netbox_cloudflare_tunnel.models import PublicHostname

    _, _, _, Service = _models()
    out = []
    for h in _restrict(PublicHostname.objects.select_related("tunnel", "service", "proxy_service"), user):
        proxy_host = h.proxy_service.parent if h.proxy_service else None
        routes = []
        if h.exposure == "nginx" and proxy_host is not None:
            # backends the Cloudflare sync linked to this hostname (one per Nginx path)
            for svc in _restrict(Service.objects.filter(custom_field_data__public_url__icontains=h.hostname), user):
                if svc.parent is None or svc.parent == proxy_host:
                    continue
                for label in str((svc.custom_field_data or {}).get("public_url") or "").split(", "):
                    if label == h.hostname or label.startswith(f"{h.hostname}/"):
                        routes.append(
                            {
                                "path": label[len(h.hostname) :] or "/",
                                "service": svc.name,
                                "host": svc.parent.name,
                                "ports": svc.port_mappings,
                            }
                        )
            routes.sort(key=lambda r: r["path"])
        out.append(
            {
                "url": f"https://{h.hostname}{h.path}",
                "tunnel": h.tunnel.name,
                "exposure_path": h.exposure,
                "origin": h.origin,
                "nginx_vhost": h.proxy_service.name if h.proxy_service else None,
                "nginx_host": proxy_host.name if proxy_host else None,
                "upstream": h.upstream or None,
                "routes": routes,
                "service": h.service.name if h.service else None,
                "host": h.service.parent.name if h.service and h.service.parent else None,
            }
        )
    return out


def dns_names(user):
    out = []
    if adguard_installed():
        from netbox_adguard.models import DNSRewrite

        for r in _restrict(DNSRewrite.objects.select_related("ip_address"), user):
            out.append(
                {
                    "name": r.domain,
                    "type": "local (AdGuard rewrite)",
                    "answer": r.answer,
                    "host": r.host_name or None,
                    "enabled": r.enabled,
                }
            )
    for u in public_urls(user):
        out.append(
            {
                "name": u["url"].split("://", 1)[1],
                "type": "public (Cloudflare)",
                "answer": u["origin"],
                "host": u["host"],
                "enabled": True,
            }
        )
    return sorted(out, key=lambda d: d["name"])


def containers(user, host=None, stack=None):
    if not docker_installed():
        return []
    from netbox_docker_inventory.models import DockerContainer

    qs = _restrict(DockerContainer.objects.select_related("host"), user)
    if host:
        qs = qs.filter(
            Q(host__name__iexact=host)
            | Q(host__virtual_machine__name__iexact=host)
            | Q(host__device__name__iexact=host)
        )
    if stack:
        qs = qs.filter(stack__iexact=stack)
    return [c.summary() for c in qs]


def search(user, query):
    q = (query or "").strip()
    if not q:
        return {}
    Device, VirtualMachine, IPAddress, Service = _models()
    result = {
        "hosts": [host_summary(h) for h in _restrict(VirtualMachine.objects.filter(name__icontains=q), user)[:25]]
        + [host_summary(h) for h in _restrict(Device.objects.filter(name__icontains=q), user)[:25]],
        "ip_addresses": [
            ip_summary(ip)
            for ip in _restrict(
                IPAddress.objects.filter(
                    Q(address__net_host=q)
                    if _looks_like_ip(q)
                    else Q(dns_name__icontains=q) | Q(description__icontains=q)
                ),
                user,
            )[:25]
        ],
        "services": [
            service_summary(s)
            for s in _restrict(Service.objects.filter(Q(name__icontains=q) | Q(description__icontains=q)), user)[:25]
        ],
        "dns_names": [d for d in dns_names(user) if q.lower() in d["name"].lower()][:25],
        "containers": [
            c for c in containers(user) if q.lower() in c["name"].lower() or q.lower() in (c["image"] or "").lower()
        ][:25],
    }
    return {k: v for k, v in result.items() if v}


def _looks_like_ip(value):
    return bool(re.fullmatch(r"[0-9a-fA-F:.]+", value)) and any(c in value for c in ".:")


def overview(user):
    Device, VirtualMachine, IPAddress, Service = _models()
    from virtualization.models import Cluster

    from .health import build_health

    data = {
        "clusters": [
            {
                "name": c.name,
                "nodes": _restrict(Device.objects.filter(cluster=c), user).count(),
                "virtual_machines": _restrict(c.virtual_machines.all(), user).count(),
            }
            for c in _restrict(Cluster.objects.all(), user)
        ],
        "counts": {
            "virtual_machines": _restrict(VirtualMachine.objects.all(), user).count(),
            "devices": _restrict(Device.objects.all(), user).count(),
            "ip_addresses": _restrict(IPAddress.objects.all(), user).count(),
            "services": _restrict(Service.objects.all(), user).count(),
            "public_urls": len(public_urls(user)),
        },
        "sources": {k: v["status"] for k, v in build_health()["sources"].items()},
    }
    if docker_installed():
        from netbox_docker_inventory.models import DockerContainer, DockerHost

        data["counts"]["docker_hosts"] = _restrict(DockerHost.objects.all(), user).count()
        data["counts"]["containers"] = _restrict(DockerContainer.objects.all(), user).count()
    if adguard_installed():
        from netbox_adguard.models import DNSRewrite

        data["counts"]["dns_rewrites"] = _restrict(DNSRewrite.objects.all(), user).count()
    return data
