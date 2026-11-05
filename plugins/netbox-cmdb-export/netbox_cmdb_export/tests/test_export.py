import copy

from django.test import TestCase
from ipam.models import IPAddress, Service
from users.models import User
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

from netbox_cmdb_export import render
from netbox_cmdb_export.collect import collect
from netbox_cmdb_export.exporter import export


class ExportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from netbox_cmdb.bootstrap import ensure_custom_fields
        from netbox_docker_inventory.ingest import apply_snapshot
        from netbox_docker_inventory.tests.test_ingest import SNAPSHOT

        ensure_custom_fields()
        cls.user = User.objects.create_superuser("admin", "a@b.c", "pw")
        cluster = Cluster.objects.create(name="pve", type=ClusterType.objects.create(name="PVE", slug="pve"))
        for name, addr in (("cmdb-lxc", "192.168.1.13/24"), ("nextcloud", "192.168.1.21/24")):
            vm = VirtualMachine.objects.create(name=name, cluster=cluster)
            iface = VMInterface.objects.create(virtual_machine=vm, name="eth0")
            IPAddress.objects.create(address=addr, assigned_object=iface)
        Service(
            name="nextcloud",
            parent=VirtualMachine.objects.get(name="nextcloud"),
            port_mappings=["tcp/11000"],
            custom_field_data={"public_url": "cloud.example.com", "exposure_path": "cloudflared-direct"},
        ).save()
        apply_snapshot(copy.deepcopy(SNAPSHOT))

    def test_markdown(self):
        md = render.to_markdown(collect(self.user))
        self.assertIn("# CMDB homelab", md)
        self.assertIn("### nextcloud", md)
        self.assertIn("11000/tcp", md)
        self.assertIn("wiki-app", md)
        self.assertIn("wiki_backend", md)

    def test_mermaid_and_dot(self):
        graph = render.build_graph(collect(self.user))
        mmd = render.to_mermaid(graph)
        self.assertTrue(mmd.startswith("flowchart LR"))
        self.assertIn("Cluster pve", mmd)
        self.assertIn("wiki", mmd)  # stack node
        self.assertIn("digraph cmdb", render.to_dot(graph))
        graph_c = render.build_graph(collect(self.user), containers=True)
        self.assertIn("wiki-db", render.to_mermaid(graph_c))

    def test_binary_formats(self):
        pdf, ctype, name = export(self.user, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF"))
        png, ctype, _ = export(self.user, "png")
        self.assertTrue(png.startswith(b"\x89PNG"))
        svg, _, _ = export(self.user, "svg")
        self.assertIn(b"<svg", svg)

    def test_views(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/plugins/export/").status_code, 200)
        for fmt in ("md", "pdf", "json", "mmd", "png", "svg"):
            resp = self.client.get(f"/plugins/export/cmdb.{fmt}")
            self.assertEqual(resp.status_code, 200, fmt)
        self.assertEqual(self.client.get("/plugins/export/cmdb.exe").status_code, 404)

    def test_permissions_restrict_content(self):
        nobody = User.objects.create_user("nobody", password="pw")
        data = collect(nobody)
        self.assertEqual(data["hosts"], [])
