"""Builds Diode entities from Nginx virtual hosts and reports runs to NetBox."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass

from . import __version__
from .parser import VirtualHost, vhosts_from_dump

APP_NAME = "cmdb-nginx-agent"


@dataclass
class Settings:
    diode_target: str
    client_id: str
    client_secret: str
    parent_name: str
    parent_type: str = "vm"  # vm | device
    cluster: str = ""
    cluster_type: str = ""
    cluster_site: str = ""
    site: str = ""
    tag: str = "nginx-agent"
    nginx_bin: str = "nginx"
    config_dump: str = ""  # path to a saved `nginx -T` output (tests / offline)
    netbox_url: str = ""
    netbox_token: str = ""
    source_name: str = "nginx"

    @classmethod
    def from_env(cls, env=os.environ):
        def get(name, default=""):
            return (env.get(name) or default).strip()

        return cls(
            diode_target=get("DIODE_TARGET"),
            client_id=get("DIODE_CLIENT_ID", "nginx-agent"),
            client_secret=get("DIODE_CLIENT_SECRET"),
            parent_name=get("NGINX_AGENT_HOST_NAME") or os.uname().nodename,
            parent_type=get("NGINX_AGENT_HOST_TYPE", "vm").lower(),
            cluster=get("NGINX_AGENT_CLUSTER"),
            cluster_type=get("NGINX_AGENT_CLUSTER_TYPE"),
            cluster_site=get("NGINX_AGENT_CLUSTER_SITE"),
            site=get("NGINX_AGENT_SITE"),
            tag=get("NGINX_AGENT_TAG", "nginx-agent"),
            nginx_bin=get("NGINX_BIN", "nginx"),
            config_dump=get("NGINX_CONFIG_DUMP"),
            netbox_url=get("NETBOX_URL").rstrip("/"),
            netbox_token=get("NETBOX_TOKEN"),
            source_name=get("CMDB_SOURCE_NAME", "nginx"),
        )


def _netbox_get(settings: Settings, path):
    req = urllib.request.Request(
        f"{settings.netbox_url}{path}",
        headers={"Authorization": f"Bearer {settings.netbox_token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def resolve_parent(settings: Settings, log=print):
    """Fill the cluster name / type / site of this VM from NetBox.

    Diode only recognises an existing cluster when it gets its name, its type and
    its site; with less, it creates a second cluster and a second VM. Values set
    explicitly (NGINX_AGENT_CLUSTER*) win over what NetBox says.
    """
    if settings.parent_type != "vm" or not settings.netbox_url or not settings.netbox_token:
        return settings
    from urllib.parse import quote

    try:
        vms = _netbox_get(settings, f"/api/virtualization/virtual-machines/?name={quote(settings.parent_name)}")
        results = vms.get("results") or []
        if not results:
            log(f"WARN: VM {settings.parent_name!r} not found in NetBox (check NGINX_AGENT_HOST_NAME)")
            return settings
        cluster_ref = results[0].get("cluster")
        if not cluster_ref:
            return settings
        cluster = _netbox_get(settings, f"/api/virtualization/clusters/{cluster_ref['id']}/")
    except (OSError, ValueError, KeyError) as exc:
        log(f"WARN: could not read the VM's cluster from NetBox ({exc}); using NGINX_AGENT_CLUSTER* only")
        return settings
    settings.cluster = settings.cluster or cluster.get("name", "")
    settings.cluster_type = settings.cluster_type or (cluster.get("type") or {}).get("name", "")
    scope = cluster.get("scope") or {}
    if not settings.cluster_site and cluster.get("scope_type") == "dcim.site":
        settings.cluster_site = scope.get("name", "")
    return settings


def read_nginx_config(settings: Settings) -> str:
    """Full effective configuration, as Nginx itself sees it (`nginx -T`)."""
    if settings.config_dump:
        with open(settings.config_dump, encoding="utf-8") as fh:
            return fh.read()
    proc = subprocess.run([settings.nginx_bin, "-T"], capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"`{settings.nginx_bin} -T` failed: {proc.stderr.strip()[-500:]}")
    return proc.stdout


def build_entities(vhosts: list[VirtualHost], settings: Settings):
    from netboxlabs.diode.sdk.ingester import (
        Cluster,
        ClusterType,
        CustomFieldValue,
        Device,
        Entity,
        Service,
        Site,
        VirtualMachine,
    )

    if settings.parent_type == "device":
        parent = {
            "parent_object_device": Device(
                name=settings.parent_name, site=Site(name=settings.site) if settings.site else None
            )
        }
    else:
        vm_kwargs = {"name": settings.parent_name}
        if settings.cluster:
            cluster_kwargs = {"name": settings.cluster}
            if settings.cluster_type:
                cluster_kwargs["type"] = ClusterType(name=settings.cluster_type)
            if settings.cluster_site:
                cluster_kwargs["scope_site"] = Site(name=settings.cluster_site)
            vm_kwargs["cluster"] = Cluster(**cluster_kwargs)
        parent = {"parent_object_virtual_machine": VirtualMachine(**vm_kwargs)}

    entities = []
    ports = None

    def service(name, upstream, description, comments=None):
        return Entity(
            service=Service(
                name=name[:100],
                port_mappings=[f"tcp/{p}" for p in ports],
                description=description[:200],
                comments=comments,
                tags=[settings.tag],
                # always sent, so a route that lost its proxy_pass is cleared in NetBox
                custom_fields={"upstream_target": CustomFieldValue(text=upstream or "")},
                **parent,
            )
        )

    for vh in vhosts:
        if not vh.ports:
            continue
        ports = sorted(vh.ports)
        root = vh.locations.get("/", "")
        routes = {path: target for path, target in vh.locations.items() if path != "/"}
        comments = "\n".join(f"{path} -> {target}" for path, target in sorted(routes.items())) or None
        description = f"Nginx vhost -> {root}" if root else f"Nginx vhost ({len(routes)} routes)"
        # the vhost itself (root location)
        entities.append(service(vh.name, root, description, comments))
        # one service per proxied path, e.g. "proxy.example.com/bastion" -> 192.168.1.5:8080
        for path, target in sorted(routes.items()):
            if path.startswith(("~", "@")):
                continue  # regex / named locations stay in the vhost comments
            entities.append(service(f"{vh.name}{path.rstrip('/')}", target, f"Nginx {vh.name}{path} -> {target}"))
    return entities


def push(entities, settings: Settings):
    from netboxlabs.diode.sdk import DiodeClient

    with DiodeClient(
        target=settings.diode_target,
        app_name=APP_NAME,
        app_version=__version__,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    ) as client:
        response = client.ingest(entities=entities)
        if response.errors:
            raise RuntimeError(f"Diode rejected the ingestion: {list(response.errors)}")


def report(settings: Settings, ok: bool, message: str, details: dict | None = None):
    """Record the run in NetBox (netbox_cmdb source health -> Zabbix). Best effort."""
    if not settings.netbox_url or not settings.netbox_token:
        return False
    body = json.dumps(
        {
            "source": settings.source_name,
            "status": "ok" if ok else "failed",
            "message": message[:4000],
            "details": details or {},
        }
    ).encode()
    req = urllib.request.Request(
        f"{settings.netbox_url}/api/plugins/cmdb/sources/",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.netbox_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
    return True


def run(settings: Settings, dry_run=False, log=print):
    vhosts = vhosts_from_dump(read_nginx_config(settings))
    resolve_parent(settings, log)
    if settings.parent_type == "vm":
        log(
            f"  parent VM: {settings.parent_name} (cluster {settings.cluster or '-'}, "
            f"type {settings.cluster_type or '-'}, site {settings.cluster_site or '-'})"
        )
        if settings.cluster and not settings.cluster_type:
            log("WARN: cluster type unknown: Diode may create a duplicate cluster/VM (set NGINX_AGENT_CLUSTER_TYPE)")
    for vh in vhosts:
        log(f"  {vh.name:40s} ports={sorted(vh.ports)} upstream={vh.upstream or '-'}")
    entities = build_entities(vhosts, settings)
    if dry_run:
        log(f"{len(entities)} services (dry run, nothing sent)")
        return vhosts
    if not settings.diode_target or not settings.client_secret:
        raise RuntimeError("DIODE_TARGET and DIODE_CLIENT_SECRET must be set")
    if entities:
        push(entities, settings)
    log(f"{len(entities)} services sent to Diode ({settings.diode_target})")
    return vhosts
