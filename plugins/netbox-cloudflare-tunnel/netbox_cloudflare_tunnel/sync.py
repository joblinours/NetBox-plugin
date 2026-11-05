"""Cloudflare Tunnel -> NetBox reconciliation.

For every public hostname of every (dashboard-managed) tunnel:

1. the origin (``http://192.168.1.20:8080``) is parsed and resolved to a NetBox
   IP address, VM or device;
2. the exposure path is classified: the origin is the Nginx reverse proxy
   (``nginx_hosts``) -> "via Nginx", anything else -> "cloudflared direct";
3. the service behind the URL is found (or created) and its ``public_url`` /
   ``exposure_path`` custom fields are set. For "via Nginx", the vhost pushed by
   the Nginx agent (through Diode) carries the upstream in ``upstream_target``,
   which is resolved the same way to reach the real backend service.

The run is idempotent: a second run with the same Cloudflare data changes nothing.
"""

import ipaddress
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import ExposureChoices, PublicHostname, Tunnel

logger = logging.getLogger("netbox.plugins.netbox_cloudflare_tunnel")

DEFAULT_PORTS = {"http": 80, "https": 443, "ssh": 22, "rdp": 3389, "smb": 445}
NON_NETWORK_SERVICES = ("http_status:", "hello_world", "bastion", "unix:", "unix+tls:")


@dataclass
class SyncResult:
    tunnels: int = 0
    hostnames: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    services_created: int = 0
    services_updated: int = 0
    unresolved: list = field(default_factory=list)
    skipped_tunnels: list = field(default_factory=list)

    def as_dict(self):
        return {
            "tunnels": self.tunnels,
            "hostnames": self.hostnames,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "services_created": self.services_created,
            "services_updated": self.services_updated,
            "unresolved": self.unresolved,
            "skipped_tunnels": self.skipped_tunnels,
        }


def parse_origin(service):
    """Return (scheme, host, port) of a cloudflared ingress service string."""
    service = (service or "").strip()
    if not service or service.startswith(NON_NETWORK_SERVICES):
        return ("", "", None)
    if "://" not in service:
        service = f"http://{service}"
    parts = urlsplit(service)
    scheme = (parts.scheme or "http").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is None:
        port = DEFAULT_PORTS.get(scheme)
    return (scheme, (parts.hostname or "").lower(), port)


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _parent_of_ip(ip):
    obj = ip.assigned_object
    if obj is None:
        return None
    return getattr(obj, "device", None) or getattr(obj, "virtual_machine", None)


def resolve_host(host):
    """Resolve an origin host to (parent object, IPAddress, how). Any member may be None."""
    from dcim.models import Device
    from ipam.models import IPAddress
    from virtualization.models import VirtualMachine

    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return (None, None, "loopback origin (runs on the cloudflared host)")
    if _is_ip(host):
        ips = list(IPAddress.objects.filter(address__net_host=host))
        ips.sort(key=lambda i: i.assigned_object_id is None)
        if not ips:
            return (None, None, f"IP {host} unknown in NetBox")
        ip = ips[0]
        parent = _parent_of_ip(ip)
        return (parent, ip, f"IP {host}" + ("" if parent else " (not assigned)"))

    ip = IPAddress.objects.filter(dns_name__iexact=host).first()
    if ip:
        return (_parent_of_ip(ip), ip, f"DNS name {host}")
    short = host.split(".")[0]
    for model in (VirtualMachine, Device):
        obj = model.objects.filter(name__iexact=host).first() or model.objects.filter(name__iexact=short).first()
        if obj:
            return (obj, obj.primary_ip, f"{model._meta.verbose_name} {obj.name}")
    return (None, None, f"host {host} unknown in NetBox")


def _host_matches(host, ip, nginx_hosts):
    candidates = {h.strip().lower() for h in nginx_hosts if h and h.strip()}
    if not candidates:
        return False
    if host and host.lower() in candidates:
        return True
    return bool(ip and str(ip.address.ip) in candidates)


def find_proxy_services(hostname, proxy_host=None):
    """Nginx services pushed by the Nginx agent for ``hostname``: the vhost itself
    (named ``hostname``) and one per proxied path (named ``hostname/path``).

    When the Nginx host is known, only its services are considered; otherwise only
    services carrying an ``upstream_target`` (backends created by this sync never do).
    """
    from django.db.models import Q
    from ipam.models import Service

    qs = Service.objects.filter(Q(name__iexact=hostname) | Q(name__istartswith=f"{hostname}/"))
    if proxy_host is not None:
        ct = ContentType.objects.get_for_model(proxy_host)
        qs = qs.filter(parent_object_type=ct, parent_object_id=proxy_host.pk)
    else:
        qs = qs.exclude(custom_field_data__upstream_target__isnull=True).exclude(custom_field_data__upstream_target="")
    return sorted(qs, key=lambda s: (len(s.name), s.name.lower()))


def ensure_service(parent, port, ip, name, create):
    """Find the service of ``parent`` listening on tcp/``port``; create it when allowed."""
    from ipam.models import Service

    if parent is None or not port:
        return (None, False)
    ct = ContentType.objects.get_for_model(parent)
    mapping = f"tcp/{port}"
    service = (
        Service.objects.filter(parent_object_type=ct, parent_object_id=parent.pk, port_mappings__contains=[mapping])
        .order_by("pk")
        .first()
    )
    if service or not create:
        return (service, False)
    service = Service(name=name[:100], parent=parent, port_mappings=[mapping], description="Created by Cloudflare sync")
    service.full_clean()
    service.save()
    if ip is not None and _parent_of_ip(ip) == parent:
        service.ipaddresses.add(ip)
    return (service, True)


def _set_service_fields(service, public_urls, exposure):
    data = dict(service.custom_field_data or {})
    wanted_url = ", ".join(sorted(public_urls)) if public_urls else None
    if data.get("public_url") == wanted_url and data.get("exposure_path") == exposure:
        return False
    if hasattr(service, "snapshot"):
        service.snapshot()
    data["public_url"] = wanted_url
    data["exposure_path"] = exposure
    service.custom_field_data = data
    service.save()
    return True


def reconcile_rule(tunnel, rule, settings):
    """Map one ingress rule to NetBox. Returns a dict of PublicHostname field values."""
    hostname = (rule.get("hostname") or "").strip().lower()
    origin = (rule.get("service") or "").strip()
    scheme, host, port = parse_origin(origin)
    values = {
        "origin": origin,
        "origin_scheme": scheme,
        "origin_host": host,
        "origin_port": port,
        "service": None,
        "proxy_service": None,
        "upstream": "",
    }
    if not host:
        values.update(exposure=ExposureChoices.OTHER, resolution="no network origin")
        return values

    parent, ip, how = resolve_host(host)
    create = settings.get("create_services", True)
    if _host_matches(host, ip, settings.get("nginx_hosts") or []):
        values["exposure"] = ExposureChoices.NGINX
        proxies = find_proxy_services(hostname, parent)
        if not proxies:
            values["resolution"] = f"via Nginx ({how}); vhost not reported by the Nginx agent yet"
            return values
        links, routes, created = [], [], 0
        for proxy in proxies:
            path = proxy.name[len(hostname) :] or "/"
            url = hostname if path == "/" else f"{hostname}{path}"
            links.append((proxy, url))
            upstream = (proxy.custom_field_data or {}).get("upstream_target") or ""
            if not upstream:
                continue
            _, up_host, up_port = parse_origin(upstream)
            up_parent, up_ip, up_how = resolve_host(up_host)
            backend, was_created = ensure_service(up_parent, up_port, up_ip, url, create)
            created += int(was_created)
            if backend is not None:
                links.append((backend, url))
            routes.append((path, upstream, backend, up_how))
        root = next((p for p in proxies if p.name.lower() == hostname), proxies[0])
        values["proxy_service"] = root
        resolved = [r for r in routes if r[2] is not None]
        values["service"] = next((r[2] for r in routes if r[0] == "/"), resolved[0][2] if resolved else None)
        if len(routes) == 1 and routes[0][0] == "/":
            values["upstream"] = routes[0][1]
            values["resolution"] = (
                f"via Nginx -> {routes[0][1]} ({routes[0][3]})" if resolved else f"via Nginx; upstream: {routes[0][3]}"
            )[:255]
        else:
            values["upstream"] = "; ".join(f"{p} -> {u}" for p, u, _, _ in routes)[:512]
            values["resolution"] = f"via Nginx: {len(routes)} routes, {len(resolved)} linked to a service"[:255]
        values["_created"] = created
        values["_links"] = links
        return values

    values["exposure"] = ExposureChoices.DIRECT
    backend, created = ensure_service(parent, port, ip, hostname, create)
    values["service"] = backend
    values["_created"] = created
    values["_links"] = [(backend, hostname)] if backend is not None else []
    values["resolution"] = how if backend else f"{how}; no service on port {port}"
    return values


def sync(client, settings, log=logger):
    """Run one full sync. ``client`` is a CloudflareClient (or a test double)."""
    result = SyncResult()
    # CLOUDFLARE_TUNNEL_IDS accepts tunnel IDs or tunnel names
    wanted_ids = {str(t).strip().lower() for t in (settings.get("tunnel_ids") or []) if str(t).strip()}
    now = timezone.now()
    remote_tunnels = [
        t
        for t in client.list_tunnels()
        if not wanted_ids or {str(t.get("id")).lower(), str(t.get("name") or "").lower()} & wanted_ids
    ]

    with transaction.atomic():
        previous_services = set(
            PublicHostname.objects.exclude(service=None).values_list("service_id", flat=True)
        ) | set(PublicHostname.objects.exclude(proxy_service=None).values_list("proxy_service_id", flat=True))
        seen_tunnels, seen_hostnames = set(), set()
        service_urls = {}  # service pk -> (service, set(hostnames), exposure)

        for remote in remote_tunnels:
            tunnel, _ = Tunnel.objects.get_or_create(
                tunnel_id=remote["id"],
                defaults={"name": remote.get("name") or remote["id"], "account_id": client.account_id},
            )
            seen_tunnels.add(tunnel.pk)
            remote_config = remote.get("config_src", "cloudflare") == "cloudflare"
            fields = {
                "name": remote.get("name") or tunnel.name,
                "account_id": client.account_id,
                "status": remote.get("status") or "",
                "remote_config": remote_config,
            }
            if any(getattr(tunnel, k) != v for k, v in fields.items()):
                for k, v in fields.items():
                    setattr(tunnel, k, v)
            tunnel.last_synced = now
            tunnel.save()
            result.tunnels += 1

            if not remote_config:
                result.skipped_tunnels.append(
                    f"{tunnel.name}: locally managed (config.yml), ingress not readable via API"
                )
                # keep existing rows of this tunnel untouched
                seen_hostnames.update(tunnel.hostnames.values_list("pk", flat=True))
                continue

            config = client.get_tunnel_configuration(remote["id"])
            for rule in config.get("ingress") or []:
                if not rule.get("hostname"):
                    continue  # catch-all rule
                values = reconcile_rule(tunnel, rule, settings)
                result.services_created += int(values.pop("_created", 0))
                links = values.pop("_links", [])
                hostname = rule["hostname"].strip().lower()
                path = (rule.get("path") or "").strip()
                obj = PublicHostname.objects.filter(tunnel=tunnel, hostname=hostname, path=path).first()
                if obj is None:
                    obj = PublicHostname(tunnel=tunnel, hostname=hostname, path=path, **values)
                    obj.save()
                    result.created += 1
                else:
                    changed = [k for k, v in values.items() if getattr(obj, k) != v]
                    if changed:
                        obj.snapshot()
                        for k in changed:
                            setattr(obj, k, values[k])
                        obj.save()
                        result.updated += 1
                seen_hostnames.add(obj.pk)
                result.hostnames += 1
                if not values.get("service") and not values.get("proxy_service"):
                    result.unresolved.append(f"{hostname}: {values.get('resolution')}")
                for svc, url in links:
                    entry = service_urls.setdefault(svc.pk, [svc, set(), values["exposure"]])
                    entry[1].add(f"{url}{path}" if path else url)

        # Hostnames removed from Cloudflare, and tunnels deleted (or filtered out) disappear.
        stale = PublicHostname.objects.exclude(pk__in=seen_hostnames)
        result.deleted = stale.count()
        stale.delete()
        Tunnel.objects.exclude(pk__in=seen_tunnels).delete()

        for svc, hostnames, exposure in service_urls.values():
            if _set_service_fields(svc, hostnames, exposure):
                result.services_updated += 1
        from ipam.models import Service

        for svc in Service.objects.filter(pk__in=previous_services - set(service_urls)):
            if _set_service_fields(svc, set(), None):
                result.services_updated += 1

    for line in result.unresolved:
        log.warning("Unresolved: %s", line)
    for line in result.skipped_tunnels:
        log.warning("Skipped tunnel %s", line)
    return result
