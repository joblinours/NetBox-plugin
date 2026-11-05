"""Apply a snapshot pushed by cmdb-docker-agent. Idempotent: a snapshot identical to
the previous one changes nothing. Containers / networks gone from the host are removed.

Snapshot format::

    {
      "host": {"name": "docker-lxc", "hostname": "...", "engine_version": "27.3.1",
               "operating_system": "Debian 12", "agent_version": "0.1.0", "addresses": ["192.168.1.13"]},
      "networks": [{"id": "...", "name": "web", "driver": "bridge", "scope": "local", "internal": false,
                    "subnets": ["172.18.0.0/16"], "gateways": ["172.18.0.1"], "stack": "web"}],
      "containers": [{"id": "...", "name": "app", "image": "nginx:1.27", "state": "running",
                      "status": "Up 2 hours", "health": "", "stack": "web", "compose_service": "app",
                      "restart_policy": "unless-stopped", "network_mode": "web", "created": "2026-01-01T00:00:00Z",
                      "ports": [{"private_port": 80, "public_port": 8080, "ip": "0.0.0.0", "type": "tcp"}],
                      "networks": [{"network": "web", "ip": "172.18.0.2", "aliases": ["app"]}],
                      "mounts": [{"type": "volume", "source": "data", "destination": "/data", "rw": true}],
                      "labels": {}}]
    }
"""

from dataclasses import asdict, dataclass

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from netbox.plugins import get_plugin_config

from .models import DockerContainer, DockerHost, DockerNetwork

PLUGIN = "netbox_docker_inventory"
LABEL_PREFIXES_KEPT = ("com.docker.compose.", "org.opencontainers.image.", "traefik.", "io.portainer.")


@dataclass
class IngestResult:
    host: str = ""
    containers: int = 0
    networks: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    services_created: int = 0
    services_updated: int = 0
    services_deleted: int = 0
    linked_to: str = ""

    def as_dict(self):
        return asdict(self)


class SnapshotError(ValueError):
    pass


def _match_parent(name, addresses):
    from dcim.models import Device
    from ipam.models import IPAddress
    from virtualization.models import VirtualMachine

    for model in (VirtualMachine, Device):
        obj = model.objects.filter(name__iexact=name).first()
        if obj:
            return obj
    for addr in addresses or []:
        ip = IPAddress.objects.filter(address__net_host=addr).exclude(assigned_object_id=None).first()
        if ip and ip.assigned_object:
            return getattr(ip.assigned_object, "virtual_machine", None) or getattr(ip.assigned_object, "device", None)
    return None


def _clean_labels(labels):
    return {k: v for k, v in (labels or {}).items() if k.startswith(LABEL_PREFIXES_KEPT)}


def _update(obj, values):
    changed = [k for k, v in values.items() if getattr(obj, k) != v]
    if not changed:
        return False
    if obj.pk and hasattr(obj, "snapshot"):
        obj.snapshot()
    for k in changed:
        setattr(obj, k, values[k])
    obj.save()
    return True


def _service_for(container, parent, result):
    """Create / update the ipam.Service describing the ports a container publishes on its host."""
    from extras.models import Tag
    from ipam.models import Service

    mappings = sorted(
        {f"{p.get('type', 'tcp')}/{int(p['public_port'])}" for p in container.published_ports},
        key=lambda m: (int(m.split("/")[1]), m),
    )
    service = container.service
    if not mappings or parent is None:
        if service is not None and service.tags.filter(slug=_tag_slug()).exists():
            service.delete()
            result.services_deleted += 1
        return None

    ct = ContentType.objects.get_for_model(parent)
    if service is None:
        service = Service.objects.filter(
            parent_object_type=ct, parent_object_id=parent.pk, name=container.name[:100]
        ).first()
    cf = dict(service.custom_field_data or {}) if service else {}
    if container.stack:
        cf["portainer_stack"] = container.stack
    values = {
        "name": container.name[:100],
        "port_mappings": mappings,
        "description": f"Docker container ({container.image})"[:200],
        "custom_field_data": cf,
    }
    if service is None:
        service = Service(parent=parent, **values)
        service.full_clean()
        service.save()
        result.services_created += 1
    else:
        if service.parent != parent:
            values["parent"] = parent
        if _update(service, values):
            result.services_updated += 1
    tag, _ = Tag.objects.get_or_create(slug=_tag_slug(), defaults={"name": _tag_name()})
    if not service.tags.filter(pk=tag.pk).exists():
        service.tags.add(tag)
    return service


def _tag_name():
    return get_plugin_config(PLUGIN, "service_tag") or "docker"


def _tag_slug():
    from django.utils.text import slugify

    return slugify(_tag_name())


def validate(snapshot):
    if not isinstance(snapshot, dict):
        raise SnapshotError("snapshot must be a JSON object")
    host = snapshot.get("host") or {}
    if not isinstance(host, dict) or not str(host.get("name", "")).strip():
        raise SnapshotError("host.name is required")
    for key in ("networks", "containers"):
        if not isinstance(snapshot.get(key, []), list):
            raise SnapshotError(f"{key} must be a list")
    return snapshot


def apply_snapshot(snapshot):
    validate(snapshot)
    create_services = get_plugin_config(PLUGIN, "create_services")
    h = snapshot["host"]
    result = IngestResult(host=h["name"].strip())
    now = timezone.now()

    with transaction.atomic():
        parent = _match_parent(result.host, h.get("addresses"))
        from virtualization.models import VirtualMachine

        host, created = DockerHost.objects.get_or_create(name=result.host)
        _update(
            host,
            {
                "hostname": (h.get("hostname") or "")[:255],
                "engine_version": (h.get("engine_version") or "")[:64],
                "operating_system": (h.get("operating_system") or "")[:255],
                "agent_version": (h.get("agent_version") or "")[:32],
                "addresses": [str(a)[:64] for a in h.get("addresses") or []],
                "virtual_machine": parent if isinstance(parent, VirtualMachine) else None,
                "device": parent if parent is not None and not isinstance(parent, VirtualMachine) else None,
            },
        )
        DockerHost.objects.filter(pk=host.pk).update(last_seen=now)  # heartbeat, not a change
        result.linked_to = parent.name if parent else ""

        # Networks
        seen_networks = {}
        for n in snapshot.get("networks") or []:
            name = str(n.get("name") or "").strip()
            if not name:
                continue
            values = {
                "network_id": str(n.get("id") or "")[:128],
                "driver": (n.get("driver") or "")[:64],
                "scope": (n.get("scope") or "")[:32],
                "internal": bool(n.get("internal")),
                "subnets": [str(s)[:64] for s in n.get("subnets") or []],
                "gateways": [str(s)[:64] for s in n.get("gateways") or []],
                "stack": (n.get("stack") or "")[:255],
            }
            net = DockerNetwork.objects.filter(host=host, name=name).first()
            if net is None:
                net = DockerNetwork.objects.create(host=host, name=name, **values)
                result.created += 1
            elif _update(net, values):
                result.updated += 1
            seen_networks[name] = net
            result.networks += 1
        stale = DockerNetwork.objects.filter(host=host).exclude(pk__in=[n.pk for n in seen_networks.values()])
        result.deleted += stale.count()
        stale.delete()

        # Containers
        seen = []
        for c in snapshot.get("containers") or []:
            name = str(c.get("name") or "").strip().lstrip("/")
            if not name:
                continue
            created_at = parse_datetime(c["created"]) if c.get("created") else None
            values = {
                "container_id": str(c.get("id") or "")[:128],
                "image": (c.get("image") or "")[:512],
                "state": (c.get("state") or "")[:32],
                "status": (c.get("status") or "")[:255],
                "health": (c.get("health") or "")[:32],
                "stack": (c.get("stack") or "")[:255],
                "compose_service": (c.get("compose_service") or "")[:255],
                "restart_policy": (c.get("restart_policy") or "")[:32],
                "network_mode": (c.get("network_mode") or "")[:255],
                "created_at": created_at,
                "ports": sorted(
                    c.get("ports") or [],
                    key=lambda p: (p.get("private_port") or 0, p.get("public_port") or 0, p.get("ip") or ""),
                ),
                "network_attachments": sorted(c.get("networks") or [], key=lambda n: n.get("network") or ""),
                "mounts": sorted(c.get("mounts") or [], key=lambda m: m.get("destination") or ""),
                "labels": _clean_labels(c.get("labels")),
            }
            # "status" ("Up 2 hours") changes every run: stored, but not counted as a change
            container = DockerContainer.objects.filter(host=host, name=name).first()
            if container is None:
                container = DockerContainer.objects.create(host=host, name=name, **values)
                result.created += 1
            else:
                status = values.pop("status")
                if _update(container, values):
                    result.updated += 1
                if container.status != status:
                    DockerContainer.objects.filter(pk=container.pk).update(status=status)
            wanted_nets = [
                seen_networks[n["network"]] for n in values["network_attachments"] if n.get("network") in seen_networks
            ]
            if set(container.networks.values_list("pk", flat=True)) != {n.pk for n in wanted_nets}:
                container.networks.set(wanted_nets)
            if create_services:
                service = _service_for(container, parent, result)
                if container.service_id != (service.pk if service else None):
                    DockerContainer.objects.filter(pk=container.pk).update(service=service)
            seen.append(container.pk)
            result.containers += 1

        stale = DockerContainer.objects.filter(host=host).exclude(pk__in=seen)
        for container in stale:
            if container.service and container.service.tags.filter(slug=_tag_slug()).exists():
                container.service.delete()
                result.services_deleted += 1
        result.deleted += stale.count()
        stale.delete()

    return result
