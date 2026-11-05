from unittest import mock

from django.test import SimpleTestCase, TestCase
from ipam.models import IPAddress
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

from netbox_adguard.client import AdGuardClient, AdGuardError
from netbox_adguard.models import DNSRewrite
from netbox_adguard.sync import answer_type, sync

SETTINGS = {
    "sync_netbox_dns": True,
    "auto_create_zones": True,
    "nameserver": "adguard.home.arpa",
    "record_tag": "adguard",
}


class Fake:
    def __init__(self, url, rewrites=None, fail=False):
        self.base_url, self._rewrites, self.fail = url, rewrites or [], fail

    def rewrites(self):
        if self.fail:
            raise AdGuardError(f"{self.base_url}: down")
        return self._rewrites


REWRITES = [
    {"domain": "nas.home.lan", "answer": "192.168.1.5", "enabled": True},
    {"domain": "photos.home.lan", "answer": "nas.home.lan", "enabled": True},
    {"domain": "ghost.home.lan", "answer": "192.168.1.250", "enabled": True},
    {"domain": "old.home.lan", "answer": "192.168.1.5", "enabled": False},
]


class ClientTest(SimpleTestCase):
    def test_parse(self):
        session = mock.Mock()
        session.get.return_value = mock.Mock(
            status_code=200,
            json=mock.Mock(
                return_value=[
                    {"domain": "NAS.lan.", "answer": "192.168.1.5"},
                    {"domain": "x.lan", "answer": "y.lan", "enabled": False},
                ]
            ),
        )
        rw = AdGuardClient("http://ag:3000/", "u", "p", session=session).rewrites()
        self.assertEqual(rw[0], {"domain": "nas.lan", "answer": "192.168.1.5", "enabled": True})
        self.assertFalse(rw[1]["enabled"])
        self.assertEqual(session.auth, ("u", "p"))

    def test_auth_error(self):
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=401)
        with self.assertRaisesRegex(AdGuardError, "authentication"):
            AdGuardClient("http://ag", session=session).rewrites()

    def test_answer_type(self):
        self.assertEqual(answer_type("192.168.1.1"), "A")
        self.assertEqual(answer_type("fd00::1"), "AAAA")
        self.assertEqual(answer_type("nas.lan"), "CNAME")
        self.assertEqual(answer_type("A"), "OTHER")


class SyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from netbox_cmdb.bootstrap import ensure_custom_fields

        ensure_custom_fields()
        cluster = Cluster.objects.create(name="pve", type=ClusterType.objects.create(name="PVE", slug="pve"))
        cls.nas = VirtualMachine.objects.create(name="nas", cluster=cluster)
        iface = VMInterface.objects.create(virtual_machine=cls.nas, name="eth0")
        cls.ip = IPAddress.objects.create(address="192.168.1.5/24", assigned_object=iface)

    def test_sync_links_and_dns(self):
        from netbox_dns.models import Record, Zone

        result = sync([Fake("http://ag1", REWRITES)], SETTINGS)
        self.assertEqual((result.rewrites, result.created), (4, 4))
        photos = DNSRewrite.objects.get(domain="photos.home.lan")
        self.assertEqual(photos.virtual_machine, self.nas)  # through the CNAME
        self.assertIn("CNAME", photos.resolution)
        self.ip.refresh_from_db()
        self.nas.refresh_from_db()
        self.assertEqual(self.ip.custom_field_data["local_domains"], "nas.home.lan, photos.home.lan")
        self.assertEqual(self.nas.custom_field_data["local_domains"], "nas.home.lan, photos.home.lan")
        self.assertTrue(any("ghost" in u for u in result.unresolved))
        # netbox-plugin-dns: zone home.lan auto-created, A + CNAME records
        zone = Zone.objects.get(name="home.lan")
        self.assertEqual(Record.objects.get(zone=zone, name="nas", type="A").value, "192.168.1.5")
        self.assertEqual(Record.objects.get(zone=zone, name="photos", type="CNAME").value, "nas.home.lan.")
        self.assertFalse(Record.objects.filter(zone=zone, name="old").exists())  # disabled
        self.assertEqual(result.dns_errors, [])

    def test_idempotent_and_cleanup(self):
        from netbox_dns.models import Record

        sync([Fake("http://ag1", REWRITES)], SETTINGS)
        records = Record.objects.filter(tags__slug="adguard").count()
        again = sync([Fake("http://ag1", REWRITES)], SETTINGS)
        self.assertEqual((again.created, again.updated, again.deleted), (0, 0, 0))
        self.assertEqual((again.dns_records_created, again.dns_records_updated, again.dns_records_deleted), (0, 0, 0))
        self.assertEqual(Record.objects.filter(tags__slug="adguard").count(), records)

        removed = sync([Fake("http://ag1", REWRITES[:1] + REWRITES[2:])], SETTINGS)
        self.assertEqual(removed.deleted, 1)
        self.assertFalse(Record.objects.filter(name="photos").exists())
        self.ip.refresh_from_db()
        self.assertEqual(self.ip.custom_field_data["local_domains"], "nas.home.lan")

    def test_failed_instance_keeps_data(self):
        sync([Fake("http://ag1", REWRITES)], SETTINGS)
        result = sync([Fake("http://ag1", fail=True)], SETTINGS)
        self.assertEqual(len(result.instances_failed), 1)
        self.assertEqual(DNSRewrite.objects.count(), 4)

    def test_ui_pages(self):
        from users.models import User

        sync([Fake("http://ag1", REWRITES)], SETTINGS)
        self.client.force_login(User.objects.create_superuser("admin", "a@b.c", "pw"))
        for url in ("/plugins/adguard/rewrites/", DNSRewrite.objects.get(domain="photos.home.lan").get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_find_host_by_local_name(self):
        from netbox_cmdb import inventory

        sync([Fake("http://ag1", REWRITES)], SETTINGS)
        self.assertEqual(inventory.find_host(None, "photos.home.lan"), self.nas)
        self.assertEqual(inventory.check_ip(None, "192.168.1.250")["available"], False)  # rewrite answer
