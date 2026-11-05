"""Collects the CMDB into one plain structure, used by every renderer.

Only objects the requesting user may view are included.
"""

from django.utils import timezone
from netbox.plugins import get_plugin_config
from netbox_cmdb import inventory


def collect(user):
    from dcim.models import Device
    from virtualization.models import Cluster, VirtualMachine

    def r(qs):
        return qs.restrict(user, "view")

    clusters = []
    for cluster in r(Cluster.objects.all()).order_by("name"):
        nodes = [d.name for d in r(Device.objects.filter(cluster=cluster)).order_by("name")]
        vms = r(VirtualMachine.objects.filter(cluster=cluster)).order_by("name")
        clusters.append(
            {
                "name": cluster.name,
                "type": str(cluster.type),
                "nodes": nodes,
                "vms": [{"name": vm.name, "node": vm.device.name if vm.device else None} for vm in vms],
            }
        )

    hosts = []
    for vm in r(VirtualMachine.objects.select_related("cluster", "device", "primary_ip4")).order_by("name"):
        hosts.append(inventory.host_detail(vm, user))
    for dev in r(Device.objects.select_related("cluster", "primary_ip4")).order_by("name"):
        hosts.append(inventory.host_detail(dev, user))

    docker = []
    if inventory.docker_installed():
        from netbox_docker_inventory.models import DockerHost

        for h in r(DockerHost.objects.all()).order_by("name"):
            docker.append(
                {
                    "name": h.name,
                    "netbox_host": h.parent.name if h.parent else None,
                    "engine_version": h.engine_version,
                    "last_seen": h.last_seen.isoformat() if h.last_seen else None,
                    "networks": [
                        {
                            "name": n.name,
                            "driver": n.driver,
                            "internal": n.internal,
                            "subnets": n.subnets,
                            "stack": n.stack or None,
                            "containers": sorted(c.name for c in n.containers.all()),
                        }
                        for n in h.networks.all()
                    ],
                    "containers": [c.summary() for c in h.containers.all()],
                }
            )

    return {
        "title": get_plugin_config("netbox_cmdb_export", "title"),
        "generated": timezone.now().isoformat(timespec="seconds"),
        "overview": inventory.overview(user),
        "clusters": clusters,
        "hosts": hosts,
        "public_urls": inventory.public_urls(user),
        "dns_names": inventory.dns_names(user),
        "docker_hosts": docker,
    }
