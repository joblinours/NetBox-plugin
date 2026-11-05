import copy
import os
from unittest import mock

from django.test import TestCase
from ipam.models import IPAddress, Service
from rest_framework.test import APIClient
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

from netbox_docker_inventory.ingest import SnapshotError, apply_snapshot
from netbox_docker_inventory.models import DockerContainer, DockerHost, DockerNetwork

TOKEN = "nbt_" + "d" * 12 + "." + "e" * 40

SNAPSHOT = {
    "host": {
        "name": "docker-lxc",
        "hostname": "lxc13",
        "engine_version": "27.3.1",
        "operating_system": "Debian 12",
        "agent_version": "0.1.0",
        "addresses": ["192.168.1.13"],
    },
    "networks": [
        {
            "id": "n1",
            "name": "bridge",
            "driver": "bridge",
            "scope": "local",
            "internal": False,
            "subnets": ["172.17.0.0/16"],
            "gateways": ["172.17.0.1"],
            "stack": "",
        },
        {
            "id": "n2",
            "name": "wiki_backend",
            "driver": "bridge",
            "scope": "local",
            "internal": True,
            "subnets": ["172.20.0.0/16"],
            "gateways": [],
            "stack": "wiki",
        },
    ],
    "containers": [
        {
            "id": "c1",
            "name": "wiki-app",
            "image": "wikijs:2",
            "state": "running",
            "status": "Up 2 hours",
            "health": "healthy",
            "stack": "wiki",
            "compose_service": "app",
            "restart_policy": "unless-stopped",
            "network_mode": "wiki_backend",
            "created": "2026-01-01T00:00:00Z",
            "ports": [
                {"private_port": 3000, "public_port": 3080, "ip": "0.0.0.0", "type": "tcp"},
                {"private_port": 3000, "public_port": 3080, "ip": "::", "type": "tcp"},
            ],
            "networks": [
                {"network": "wiki_backend", "ip": "172.20.0.2", "aliases": ["app"]},
                {"network": "bridge", "ip": "172.17.0.2", "aliases": []},
            ],
            "mounts": [{"type": "volume", "source": "wiki_data", "destination": "/data", "rw": True}],
            "labels": {"com.docker.compose.project": "wiki", "secret.label": "x"},
        },
        {
            "id": "c2",
            "name": "wiki-db",
            "image": "postgres:17",
            "state": "running",
            "status": "Up 2 hours",
            "stack": "wiki",
            "network_mode": "wiki_backend",
            "ports": [{"private_port": 5432, "type": "tcp"}],
            "networks": [{"network": "wiki_backend", "ip": "172.20.0.3", "aliases": ["db"]}],
            "mounts": [],
        },
    ],
}


class IngestTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from netbox_cmdb.bootstrap import ensure_custom_fields

        ensure_custom_fields()
        cluster = Cluster.objects.create(name="pve", type=ClusterType.objects.create(name="PVE", slug="pve"))
        cls.vm = VirtualMachine.objects.create(name="cmdb-lxc", cluster=cluster)
        iface = VMInterface.objects.create(virtual_machine=cls.vm, name="eth0")
        IPAddress.objects.create(address="192.168.1.13/24", assigned_object=iface)

    def test_snapshot(self):
        result = apply_snapshot(copy.deepcopy(SNAPSHOT))
        self.assertEqual((result.containers, result.networks), (2, 2))
        self.assertEqual(result.linked_to, "cmdb-lxc")  # matched by IP
        host = DockerHost.objects.get()
        self.assertEqual(host.virtual_machine, self.vm)
        app = DockerContainer.objects.get(name="wiki-app")
        self.assertEqual(app.stack, "wiki")
        self.assertEqual(set(app.networks.values_list("name", flat=True)), {"wiki_backend", "bridge"})
        self.assertNotIn("secret.label", app.labels)
        # the database publishes nothing: no service, but it is inventoried with its internal network
        db = DockerContainer.objects.get(name="wiki-db")
        self.assertIsNone(db.service)
        self.assertTrue(DockerNetwork.objects.get(name="wiki_backend").internal)
        self.assertEqual(app.service.port_mappings, ["tcp/3080"])
        self.assertEqual(app.service.parent, self.vm)
        self.assertEqual(app.service.custom_field_data["portainer_stack"], "wiki")

    def test_idempotent(self):
        apply_snapshot(copy.deepcopy(SNAPSHOT))
        snap = copy.deepcopy(SNAPSHOT)
        snap["containers"][0]["status"] = "Up 3 hours"
        result = apply_snapshot(snap)
        self.assertEqual((result.created, result.updated, result.deleted), (0, 0, 0))
        self.assertEqual((result.services_created, result.services_updated), (0, 0))
        self.assertEqual(Service.objects.count(), 1)
        self.assertEqual(DockerContainer.objects.get(name="wiki-app").status, "Up 3 hours")

    def test_removed_container_and_service(self):
        apply_snapshot(copy.deepcopy(SNAPSHOT))
        snap = copy.deepcopy(SNAPSHOT)
        snap["containers"] = snap["containers"][1:]
        snap["networks"] = snap["networks"][1:]
        result = apply_snapshot(snap)
        self.assertEqual(result.services_deleted, 1)
        self.assertFalse(DockerContainer.objects.filter(name="wiki-app").exists())
        self.assertFalse(Service.objects.exists())
        self.assertEqual(DockerNetwork.objects.count(), 1)

    def test_invalid(self):
        with self.assertRaises(SnapshotError):
            apply_snapshot({"host": {}})

    def test_api_requires_permission_and_reports(self):
        from netbox_cmdb import bootstrap
        from netbox_cmdb.models import SourceStatus

        with mock.patch.dict(
            os.environ, {"CMDB_TOKEN_DOCKER_AGENT": TOKEN, "CMDB_TOKEN_ZABBIX": "nbt_" + "z" * 12 + "." + "y" * 40}
        ):
            bootstrap.ensure_service_accounts()
        client = APIClient()
        url = "/api/plugins/docker-inventory/snapshot/"
        client.credentials(HTTP_AUTHORIZATION="Bearer nbt_" + "z" * 12 + "." + "y" * 40)
        self.assertEqual(client.post(url, SNAPSHOT, format="json").status_code, 403)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        resp = client.post(url, SNAPSHOT, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["containers"], 2)
        self.assertEqual(SourceStatus.objects.get(name="docker-docker-lxc").status, "ok")
        self.assertEqual(client.post(url, {"host": {}}, format="json").status_code, 400)
        # the agent can only write; reading needs a user with view permissions
        from users.models import User

        reader = APIClient()
        reader.force_authenticate(User.objects.create_superuser("reader", "r@x.y", "pw"))
        resp = reader.get("/api/plugins/docker-inventory/containers/?stack=wiki")
        self.assertEqual(resp.json()["count"], 2)

    def test_ui_pages(self):
        from users.models import User

        apply_snapshot(copy.deepcopy(SNAPSHOT))
        self.client.force_login(User.objects.create_superuser("admin", "a@b.c", "pw"))
        for url in (
            "/plugins/docker-inventory/hosts/",
            "/plugins/docker-inventory/containers/",
            "/plugins/docker-inventory/networks/",
            DockerHost.objects.get().get_absolute_url(),
            DockerContainer.objects.get(name="wiki-app").get_absolute_url(),
            DockerNetwork.objects.get(name="wiki_backend").get_absolute_url(),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
