import json
import os
from unittest import mock

from django.test import TestCase
from ipam.models import IPAddress, Service
from rest_framework.test import APIClient
from virtualization.models import Cluster, ClusterType, VirtualMachine, VMInterface

TOKEN = "nbt_" + "m" * 12 + "." + "n" * 40
URL = "/api/plugins/mcp/"


class MCPTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from netbox_cmdb import bootstrap

        bootstrap.ensure_custom_fields()
        with mock.patch.dict(os.environ, {"CMDB_TOKEN_MCP": TOKEN}):
            bootstrap.ensure_service_accounts()
        cluster = Cluster.objects.create(name="pve", type=ClusterType.objects.create(name="PVE", slug="pve"))
        vm = VirtualMachine.objects.create(name="gitea", cluster=cluster)
        iface = VMInterface.objects.create(virtual_machine=vm, name="eth0")
        ip = IPAddress.objects.create(
            address="192.168.1.25/24",
            assigned_object=iface,
            comments=json.dumps(
                {
                    "ports": [
                        {"number": 22, "protocol": "tcp", "state": "open"},
                        {"number": 25, "protocol": "tcp", "state": "closed"},
                    ]
                }
            ),
        )
        vm.primary_ip4 = ip
        vm.save()
        Service(name="gitea", parent=vm, port_mappings=["tcp/3000", "tcp/8000"]).save()
        IPAddress.objects.create(address="192.168.1.2/24")

    def setUp(self):
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {TOKEN}")

    def rpc(self, method, params=None, msg_id=1):
        body = {"jsonrpc": "2.0", "method": method}
        if msg_id is not None:
            body["id"] = msg_id
        if params is not None:
            body["params"] = params
        return self.api.post(URL, body, format="json", HTTP_ACCEPT="application/json, text/event-stream")

    def call(self, name, **arguments):
        resp = self.rpc("tools/call", {"name": name, "arguments": arguments})
        self.assertEqual(resp.status_code, 200, resp.content)
        result = resp.json()["result"]
        return json.loads(result["content"][0]["text"]) if not result["isError"] else result

    def test_auth_required(self):
        resp = APIClient().post(URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, format="json")
        self.assertIn(resp.status_code, (401, 403))

    def test_handshake(self):
        resp = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "claude-code", "version": "1"},
            },
        )
        result = resp.json()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(self.rpc("notifications/initialized", msg_id=None).status_code, 202)
        tools = {t["name"] for t in self.rpc("tools/list").json()["result"]["tools"]}
        self.assertTrue({"check_port", "find_free_ips", "get_host", "list_containers", "export"} <= tools)
        self.assertEqual(self.rpc("nope").json()["error"]["code"], -32601)
        self.assertEqual(self.rpc("tools/call", {"name": "nope"}).json()["error"]["code"], -32602)
        self.assertEqual(self.api.get(URL).status_code, 405)

    def test_ports(self):
        self.assertFalse(self.call("check_port", host="gitea", port=3000)["available"])
        self.assertFalse(self.call("check_port", host="192.168.1.25", port=22)["available"])  # from the scan
        self.assertTrue(self.call("check_port", host="gitea", port=25)["available"])  # closed in scan
        free = self.call("find_free_ports", host="gitea", start=2999, end=3002, count=3)["free"]
        self.assertEqual(free, [2999, 3001, 3002])
        used = self.call("list_used_ports", host="gitea")["ports"]
        self.assertEqual([p["port"] for p in used], [22, 3000, 8000])

    def test_ips(self):
        free = self.call("find_free_ips", prefix="192.168.1.0/29", count=10)["free"]
        self.assertEqual(free, ["192.168.1.3", "192.168.1.4", "192.168.1.5", "192.168.1.6"])
        self.assertFalse(self.call("check_ip", address="192.168.1.25")["available"])
        self.assertTrue(self.call("check_ip", address="192.168.1.77")["available"])

    def test_host_search_overview_export(self):
        host = self.call("get_host", host="GITEA")
        self.assertEqual(host["primary_ip"], "192.168.1.25")
        self.assertEqual(host["services"][0]["ports"], ["tcp/3000", "tcp/8000"])
        self.assertIn("hosts", self.call("search", query="git"))
        self.assertEqual(self.call("cmdb_overview")["counts"]["virtual_machines"], 1)
        resp = self.rpc("tools/call", {"name": "export", "arguments": {"format": "mmd"}})
        self.assertIn("flowchart LR", resp.json()["result"]["content"][0]["text"])
        missing = self.rpc("tools/call", {"name": "get_host", "arguments": {}}).json()["result"]
        self.assertTrue(missing["isError"])

    def test_batch(self):
        resp = self.api.post(
            URL,
            [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}],
            format="json",
        )
        self.assertEqual(len(resp.json()), 1)
