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
            site=get("NGINX_AGENT_SITE"),
            tag=get("NGINX_AGENT_TAG", "nginx-agent"),
            nginx_bin=get("NGINX_BIN", "nginx"),
            config_dump=get("NGINX_CONFIG_DUMP"),
            netbox_url=get("NETBOX_URL").rstrip("/"),
            netbox_token=get("NETBOX_TOKEN"),
            source_name=get("CMDB_SOURCE_NAME", "nginx"),
        )


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
            vm_kwargs["cluster"] = Cluster(name=settings.cluster)
        parent = {"parent_object_virtual_machine": VirtualMachine(**vm_kwargs)}

    entities = []
    for vh in vhosts:
        if not vh.ports:
            continue
        extra = [f"{path} -> {target}" for path, target in sorted(vh.locations.items()) if path != "/"]
        description = f"Nginx vhost -> {vh.upstream}" if vh.upstream else "Nginx vhost (no proxy_pass)"
        custom_fields = {"upstream_target": CustomFieldValue(text=vh.upstream)} if vh.upstream else None
        service = Service(
            name=vh.name[:100],
            port_mappings=[f"tcp/{p}" for p in sorted(vh.ports)],
            description=description[:200],
            comments="\n".join(extra) if extra else None,
            tags=[settings.tag],
            custom_fields=custom_fields,
            **parent,
        )
        entities.append(Entity(service=service))
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
