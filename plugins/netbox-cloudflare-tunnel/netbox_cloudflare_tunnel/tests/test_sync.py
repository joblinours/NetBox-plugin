from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase
from ipam.models import IPAddress, Service
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

from netbox_cloudflare_tunnel.cloudflare import CloudflareClient, CloudflareError
from netbox_cloudflare_tunnel.models import PublicHostname, Tunnel
from netbox_cloudflare_tunnel.sync import parse_origin, sync

TUNNEL_ID = "11111111-2222-3333-4444-555555555555"


class FakeClient:
    account_id = "acc123"

    def __init__(self, ingress, config_src="cloudflare"):
        self.ingress = ingress
        self.config_src = config_src

    def list_tunnels(self):
        return [{"id": TUNNEL_ID, "name": "homelab", "status": "healthy", "config_src": self.config_src}]

    def get_tunnel_configuration(self, tunnel_id):
        assert tunnel_id == TUNNEL_ID
        return {"ingress": self.ingress}


SETTINGS = {"nginx_hosts": ["192.168.1.30"], "create_services": True, "tunnel_ids": []}


class ParseOriginTest(SimpleTestCase):
    def test_parse(self):
        self.assertEqual(parse_origin("http://192.168.1.20:8080"), ("http", "192.168.1.20", 8080))
        self.assertEqual(parse_origin("https://App01.lan"), ("https", "app01.lan", 443))
        self.assertEqual(parse_origin("ssh://10.0.0.1:22"), ("ssh", "10.0.0.1", 22))
        self.assertEqual(parse_origin("localhost:3000"), ("http", "localhost", 3000))
        self.assertEqual(parse_origin("http_status:404"), ("", "", None))
        self.assertEqual(parse_origin("unix:/tmp/sock"), ("", "", None))


class ClientTest(SimpleTestCase):
    def test_requires_credentials(self):
        with self.assertRaises(CloudflareError):
            CloudflareClient("", "acc")

    def test_pagination_and_errors(self):
        session = mock.Mock()
        session.headers = {}
        pages = [
            {"success": True, "result": [{"id": "a"}], "result_info": {"total_pages": 2}},
            {"success": True, "result": [{"id": "b"}], "result_info": {"total_pages": 2}},
        ]
        session.get.side_effect = [mock.Mock(status_code=200, json=mock.Mock(return_value=p)) for p in pages]
        client = CloudflareClient("tok", "acc", session=session)
        self.assertEqual([t["id"] for t in client.list_tunnels()], ["a", "b"])
        self.assertEqual(session.headers["Authorization"], "Bearer tok")

        session.get.side_effect = [
            mock.Mock(
                status_code=403,
                reason="Forbidden",
                json=mock.Mock(return_value={"success": False, "errors": [{"message": "Authentication error"}]}),
            )
        ]
        with self.assertRaisesRegex(CloudflareError, "Authentication error"):
            client.list_tunnels()


class SyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from netbox_cmdb.bootstrap import ensure_custom_fields

        ensure_custom_fields()
        cluster = Cluster.objects.create(name="pve", type=ClusterType.objects.create(name="Proxmox", slug="proxmox"))
        cls.app = VirtualMachine.objects.create(name="app01", cluster=cluster)
        cls.proxy = VirtualMachine.objects.create(name="revers-proxy", cluster=cluster)
        cls.mail = VirtualMachine.objects.create(name="mail", cluster=cluster)
        for vm, addr in ((cls.app, "192.168.1.20/24"), (cls.proxy, "192.168.1.30/24"), (cls.mail, "192.168.1.40/24")):
            iface = VMInterface.objects.create(virtual_machine=vm, name="eth0")
            IPAddress.objects.create(address=addr, assigned_object=iface)
        # vhost reported by the Nginx agent (through Diode)
        cls.vhost = Service(
            name="cloud.example.com",
            parent=cls.proxy,
            port_mappings=["tcp/80"],
            custom_field_data={"upstream_target": "http://192.168.1.20:8080"},
        )
        cls.vhost.save()

    def _ingress(self):
        return [
            {"hostname": "mail.example.com", "service": "https://192.168.1.40:443"},
            {"hostname": "cloud.example.com", "service": "http://192.168.1.30:80"},
            {"hostname": "ghost.example.com", "service": "http://192.168.1.99:80"},
            {"service": "http_status:404"},
        ]

    def test_sync_maps_exposure_and_services(self):
        result = sync(FakeClient(self._ingress()), SETTINGS)
        self.assertEqual((result.tunnels, result.hostnames, result.created), (1, 3, 3))
        self.assertEqual(Tunnel.objects.get().name, "homelab")

        mail = PublicHostname.objects.get(hostname="mail.example.com")
        self.assertEqual(mail.exposure, "cloudflared-direct")
        self.assertEqual(mail.service.parent, self.mail)
        self.assertEqual(mail.service.port_mappings, ["tcp/443"])
        self.assertEqual(mail.service.custom_field_data["public_url"], "mail.example.com")
        self.assertEqual(mail.service.custom_field_data["exposure_path"], "cloudflared-direct")

        cloud = PublicHostname.objects.get(hostname="cloud.example.com")
        self.assertEqual(cloud.exposure, "nginx")
        self.assertEqual(cloud.proxy_service, self.vhost)
        self.assertEqual(cloud.upstream, "http://192.168.1.20:8080")
        self.assertEqual(cloud.service.parent, self.app)
        self.assertEqual(cloud.service.port_mappings, ["tcp/8080"])
        self.vhost.refresh_from_db()
        self.assertEqual(self.vhost.custom_field_data["exposure_path"], "nginx")
        self.assertEqual(cloud.service.custom_field_data["public_url"], "cloud.example.com")

        ghost = PublicHostname.objects.get(hostname="ghost.example.com")
        self.assertIsNone(ghost.service)
        self.assertTrue(any("ghost" in u for u in result.unresolved))

    def test_second_run_is_idempotent(self):
        sync(FakeClient(self._ingress()), SETTINGS)
        counts = (PublicHostname.objects.count(), Service.objects.count(), Tunnel.objects.count())
        result = sync(FakeClient(self._ingress()), SETTINGS)
        self.assertEqual((result.created, result.updated, result.deleted, result.services_created), (0, 0, 0, 0))
        self.assertEqual(result.services_updated, 0)
        self.assertEqual(counts, (PublicHostname.objects.count(), Service.objects.count(), Tunnel.objects.count()))

    def test_existing_service_is_reused(self):
        existing = Service(name="postfix", parent=self.mail, port_mappings=["tcp/25", "tcp/443"])
        existing.save()
        sync(FakeClient(self._ingress()), SETTINGS)
        self.assertEqual(PublicHostname.objects.get(hostname="mail.example.com").service, existing)
        ct = ContentType.objects.get_for_model(VirtualMachine)
        self.assertEqual(Service.objects.filter(parent_object_type=ct, parent_object_id=self.mail.pk).count(), 1)

    def test_removed_hostname_is_cleaned(self):
        sync(FakeClient(self._ingress()), SETTINGS)
        mail_service = PublicHostname.objects.get(hostname="mail.example.com").service
        result = sync(FakeClient(self._ingress()[1:]), SETTINGS)
        self.assertEqual(result.deleted, 1)
        self.assertFalse(PublicHostname.objects.filter(hostname="mail.example.com").exists())
        mail_service.refresh_from_db()
        self.assertIsNone(mail_service.custom_field_data.get("public_url"))

    def test_local_tunnel_skipped(self):
        result = sync(FakeClient(self._ingress(), config_src="local"), SETTINGS)
        self.assertEqual(result.hostnames, 0)
        self.assertEqual(len(result.skipped_tunnels), 1)
        self.assertFalse(Tunnel.objects.get().remote_config)

    def test_vhost_not_reported_yet(self):
        ingress = [{"hostname": "new.example.com", "service": "http://192.168.1.30:80"}]
        sync(FakeClient(ingress), SETTINGS)
        obj = PublicHostname.objects.get(hostname="new.example.com")
        self.assertEqual(obj.exposure, "nginx")
        self.assertIsNone(obj.proxy_service)
        self.assertIn("not reported", obj.resolution)

    def test_ui_pages(self):
        from users.models import User

        sync(FakeClient(self._ingress()), SETTINGS)
        self.client.force_login(User.objects.create_superuser("admin", "a@b.c", "pw"))
        for url in (
            "/plugins/cloudflare-tunnel/tunnels/",
            "/plugins/cloudflare-tunnel/hostnames/",
            Tunnel.objects.get().get_absolute_url(),
            PublicHostname.objects.first().get_absolute_url(),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
