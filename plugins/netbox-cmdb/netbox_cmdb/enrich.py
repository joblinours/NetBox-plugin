"""Fill gaps the sources leave in NetBox.

* proxmox2netbox never sets a VM's node (``VirtualMachine.device``) nor the
  management IP of the nodes: ``link_proxmox`` adds both from the Proxmox API.
* VMs without a QEMU guest agent have no IP in NetBox: ``assign_ip`` is used by
  the AdGuard sync to give such a host the IP of a DNS rewrite named after it.

Nothing set by hand is overwritten: a host that already has a primary IPv4
keeps it, an IP assigned to another object is never moved.
"""

import ipaddress
import logging

from django.db import transaction

logger = logging.getLogger("netbox.plugins.netbox_cmdb")


def _prefix_length(address):
    """Mask of the NetBox IP whose network contains ``address`` (e.g. a VM in /23), else /32."""
    import netaddr
    from ipam.models import IPAddress

    target = ipaddress.ip_address(address)
    needle = netaddr.IPAddress(str(target))
    best = None
    for ip in IPAddress.objects.filter(address__family=target.version).exclude(assigned_object_id=None)[:2000]:
        net = ip.address.cidr
        if needle in net and net.prefixlen < target.max_prefixlen and (best is None or net.prefixlen > best):
            best = net.prefixlen
    return best or target.max_prefixlen


def _interface_for(host, interface_name=None):
    from dcim.models import Device, Interface
    from virtualization.models import VMInterface

    if isinstance(host, Device):
        qs = Interface.objects.filter(device=host)
        iface = (qs.filter(name=interface_name).first() if interface_name else None) or qs.order_by("pk").first()
        if iface is None:
            iface = Interface(device=host, name=interface_name or "mgmt", type="virtual")
            iface.full_clean()
            iface.save()
        return iface
    iface = VMInterface.objects.filter(virtual_machine=host).order_by("pk").first()
    if iface is None:
        iface = VMInterface(virtual_machine=host, name=interface_name or "eth0")
        iface.full_clean()
        iface.save()
    return iface


def _owner(ip):
    obj = ip.assigned_object
    if obj is None:
        return None
    return getattr(obj, "device", None) or getattr(obj, "virtual_machine", None)


def assign_ip(host, address, source, interface_name=None):
    """Give ``host`` (VM or device) ``address`` as primary IPv4 when it has none.

    Returns a short message when something changed, else None.
    """
    from ipam.models import IPAddress

    try:
        target = ipaddress.ip_address(address)
    except ValueError:
        return None
    if target.version != 4 or host.primary_ip4_id:
        return None

    with transaction.atomic():
        ips = list(IPAddress.objects.filter(address__net_host=str(target), vrf__isnull=True))
        mine = next((ip for ip in ips if _owner(ip) == host), None)
        if mine is None and any(_owner(ip) not in (None, host) for ip in ips):
            logger.info("%s: %s belongs to another host, not assigned to %s", source, address, host)
            return None
        ip = mine or next((ip for ip in ips if ip.assigned_object is None), None)
        if ip is None:
            ip = IPAddress(address=f"{target}/{_prefix_length(target)}", description=f"Assigned from {source}")
        if ip.assigned_object is None:
            if ip.pk:
                ip.snapshot()
            ip.assigned_object = _interface_for(host, interface_name)
            if not ip.description:
                ip.description = f"Assigned from {source}"
            ip.full_clean()
            ip.save()
        host.snapshot()
        host.primary_ip4 = ip
        host.save()
    return f"{host.name}: primary IP {ip.address} ({source})"


def link_proxmox(endpoint):
    """Set each VM's node and each node's management IP from the Proxmox API.

    Returns {"vms_linked": n, "node_ips": n, "messages": [...]}.
    """
    from dcim.models import Device
    from proxmox2netbox.services.proxmox_sync import connect_endpoint
    from virtualization.models import VirtualMachine

    client = connect_endpoint(endpoint).client
    status_rows = client.cluster.status.get() or []
    resources = client.cluster.resources.get(type="vm") or []
    result = {"vms_linked": 0, "node_ips": 0, "messages": []}

    nodes = {}
    for row in status_rows:
        if row.get("type") != "node" or not row.get("name"):
            continue
        device = Device.objects.filter(name__iexact=row["name"]).order_by("pk").first()
        if device is None:
            continue
        nodes[row["name"]] = device
        if row.get("ip"):
            msg = assign_ip(device, row["ip"], "Proxmox cluster status", interface_name="vmbr0")
            if msg:
                result["node_ips"] += 1
                result["messages"].append(msg)

    for res in resources:
        device = nodes.get(res.get("node"))
        if device is None or not res.get("name"):
            continue
        qs = VirtualMachine.objects.filter(name=res["name"])
        if device.cluster_id:
            qs = qs.filter(cluster_id=device.cluster_id)
        vm = qs.order_by("pk").first()
        if vm is None or vm.device_id == device.pk:
            continue
        vm.snapshot()
        vm.device = device
        vm.save()
        result["vms_linked"] += 1
    return result
