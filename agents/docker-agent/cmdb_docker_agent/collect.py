"""Turns Docker Engine API answers into the snapshot expected by netbox_docker_inventory."""

from . import __version__

COMPOSE_PROJECT = "com.docker.compose.project"
COMPOSE_SERVICE = "com.docker.compose.service"
STACK_NAMESPACE = "com.docker.stack.namespace"  # swarm stacks


def _stack(labels):
    labels = labels or {}
    return labels.get(COMPOSE_PROJECT) or labels.get(STACK_NAMESPACE) or ""


def build_network(net):
    ipam = (net.get("IPAM") or {}).get("Config") or []
    return {
        "id": net.get("Id", ""),
        "name": net.get("Name", ""),
        "driver": net.get("Driver", ""),
        "scope": net.get("Scope", ""),
        "internal": bool(net.get("Internal")),
        "subnets": [c["Subnet"] for c in ipam if c.get("Subnet")],
        "gateways": [c["Gateway"] for c in ipam if c.get("Gateway")],
        "stack": _stack(net.get("Labels")),
    }


def build_container(summary, detail):
    cfg = detail.get("Config") or {}
    host_cfg = detail.get("HostConfig") or {}
    state = detail.get("State") or {}
    labels = cfg.get("Labels") or summary.get("Labels") or {}

    ports = []
    seen = set()
    for p in summary.get("Ports") or []:
        key = (p.get("PrivatePort"), p.get("PublicPort"), p.get("Type", "tcp"), p.get("IP", ""))
        if key in seen:
            continue
        seen.add(key)
        ports.append(
            {
                "private_port": p.get("PrivatePort"),
                "public_port": p.get("PublicPort"),
                "ip": p.get("IP", ""),
                "type": p.get("Type", "tcp"),
            }
        )
    # host network mode: no port mapping, the exposed ports are the host's ports
    if host_cfg.get("NetworkMode") == "host":
        for spec in cfg.get("ExposedPorts") or {}:
            port, _, proto = spec.partition("/")
            if port.isdigit():
                ports.append({"private_port": int(port), "public_port": int(port), "ip": "", "type": proto or "tcp"})

    networks = []
    for name, n in ((detail.get("NetworkSettings") or {}).get("Networks") or {}).items():
        aliases = [a for a in (n.get("Aliases") or []) if a and not detail.get("Id", "").startswith(a)]
        networks.append({"network": name, "ip": n.get("IPAddress") or "", "aliases": sorted(set(aliases))})

    mounts = [
        {
            "type": m.get("Type", ""),
            "source": m.get("Name") or m.get("Source", ""),
            "destination": m.get("Destination", ""),
            "rw": bool(m.get("RW", True)),
        }
        for m in detail.get("Mounts") or []
    ]
    return {
        "id": detail.get("Id") or summary.get("Id", ""),
        "name": (detail.get("Name") or (summary.get("Names") or ["?"])[0]).lstrip("/"),
        "image": cfg.get("Image") or summary.get("Image", ""),
        "state": state.get("Status") or summary.get("State", ""),
        "status": summary.get("Status", ""),
        "health": (state.get("Health") or {}).get("Status", ""),
        "stack": _stack(labels),
        "compose_service": labels.get(COMPOSE_SERVICE, ""),
        "restart_policy": (host_cfg.get("RestartPolicy") or {}).get("Name", ""),
        "network_mode": host_cfg.get("NetworkMode", ""),
        "created": detail.get("Created", ""),
        "ports": ports,
        "networks": networks,
        "mounts": mounts,
        "labels": labels,
    }


def build_snapshot(client, host_name, addresses=()):
    info = client.info()
    version = client.version()
    containers = []
    for summary in client.containers():
        detail = client.inspect_container(summary["Id"])
        containers.append(build_container(summary, detail))
    networks = [build_network(n) for n in client.networks()]
    return {
        "host": {
            "name": host_name or info.get("Name", ""),
            "hostname": info.get("Name", ""),
            "engine_version": version.get("Version", ""),
            "operating_system": info.get("OperatingSystem", ""),
            "agent_version": __version__,
            "addresses": list(addresses),
        },
        "networks": networks,
        "containers": containers,
    }
