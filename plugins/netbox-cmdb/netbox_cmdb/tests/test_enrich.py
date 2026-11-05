from unittest import mock

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase
from ipam.models import IPAddress
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

from netbox_cmdb.enrich import assign_ip, link_proxmox


class EnrichTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="lab", slug="lab")
        cls.cluster = Cluster.objects.create(name="homelab", type=ClusterType.objects.create(name="PVE", slug="pve"))
        dtype = DeviceType.objects.create(
            manufacturer=Manufacturer.objects.create(name="Proxmox", slug="proxmox"), model="Node", slug="node"
        )
        role = DeviceRole.objects.create(name="Node", slug="node")
        cls.node1 = Device.objects.create(name="node1", site=site, device_type=dtype, role=role, cluster=cls.cluster)
        cls.adguard = VirtualMachine.objects.create(name="Adguard", cluster=cls.cluster)
        iface = VMInterface.objects.create(virtual_machine=cls.adguard, name="eth0")
        ip = IPAddress.objects.create(address="192.168.1.3/23", assigned_object=iface)
        cls.adguard.primary_ip4 = ip
        cls.adguard.save()
        cls.homeass = VirtualMachine.objects.create(name="HomeAss", cluster=cls.cluster)

    def test_assign_new_ip_uses_neighbour_mask(self):
        msg = assign_ip(self.homeass, "192.168.1.6", "AdGuard rewrite homeass.local")
        self.assertIn("HomeAss", msg)
        self.homeass.refresh_from_db()
        self.assertEqual(str(self.homeass.primary_ip4.address), "192.168.1.6/23")
        self.assertEqual(self.homeass.primary_ip4.assigned_object.virtual_machine, self.homeass)
        self.assertIsNone(assign_ip(self.homeass, "192.168.1.6", "again"))  # idempotent

    def test_reuses_scanned_ip_and_never_steals(self):
        scanned = IPAddress.objects.create(address="192.168.1.6/24", description="Discovered by orb-agent")
        assign_ip(self.homeass, "192.168.1.6", "AdGuard")
        scanned.refresh_from_db()
        self.assertEqual(scanned.assigned_object.virtual_machine, self.homeass)
        self.assertEqual(IPAddress.objects.filter(address__net_host="192.168.1.6").count(), 1)
        # an IP owned by another host is not moved, a host with a primary IP is not touched
        self.assertIsNone(assign_ip(self.node1, "192.168.1.3", "x"))
        self.assertIsNone(assign_ip(self.adguard, "192.168.1.50", "x"))

    def test_device_gets_interface(self):
        assign_ip(self.node1, "192.168.1.1", "Proxmox cluster status", interface_name="vmbr0")
        self.node1.refresh_from_db()
        self.assertEqual(self.node1.primary_ip4.assigned_object.name, "vmbr0")

    def test_link_proxmox(self):
        client = mock.MagicMock()
        client.cluster.status.get.return_value = [
            {"type": "cluster", "name": "homelab"},
            {"type": "node", "name": "node1", "ip": "192.168.1.1"},
        ]
        client.cluster.resources.get.return_value = [
            {"type": "lxc", "name": "Adguard", "node": "node1"},
            {"type": "qemu", "name": "HomeAss", "node": "node1"},
            {"type": "qemu", "name": "ghost", "node": "node9"},
        ]
        with mock.patch("proxmox2netbox.services.proxmox_sync.connect_endpoint", return_value=mock.Mock(client=client)):
            result = link_proxmox(endpoint=None)
            again = link_proxmox(endpoint=None)
        self.assertEqual((result["vms_linked"], result["node_ips"]), (2, 1))
        self.assertEqual((again["vms_linked"], again["node_ips"]), (0, 0))
        self.adguard.refresh_from_db()
        self.assertEqual(self.adguard.device, self.node1)
        self.node1.refresh_from_db()
        self.assertEqual(str(self.node1.primary_ip4.address.ip), "192.168.1.1")
