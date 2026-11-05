import os
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from extras.models import CustomField
from rest_framework.test import APIClient
from users.models import Token, User

from netbox_cmdb import bootstrap
from netbox_cmdb.health import build_health
from netbox_cmdb.models import SourceStatus

ZABBIX_TOKEN = "nbt_" + "a" * 12 + "." + "b" * 40
ORB_TOKEN = "nbt_" + "c" * 12 + "." + "d" * 40


class ParseTokenTest(TestCase):
    def test_valid(self):
        self.assertEqual(bootstrap.parse_v2_token(ZABBIX_TOKEN), ("a" * 12, "b" * 40))
        self.assertEqual(bootstrap.parse_v2_token("a" * 12 + "." + "b" * 40), ("a" * 12, "b" * 40))

    def test_invalid(self):
        for bad in (
            "",
            "nbt_short.x",
            "nbt_" + "a" * 12,
            "nbt_" + "a" * 12 + "." + "b" * 10,
            "nbt_aaaaaaaaaaa$." + "b" * 40,
        ):
            with self.assertRaises(ValueError):
                bootstrap.parse_v2_token(bad)


class CustomFieldsTest(TestCase):
    def test_created_and_idempotent(self):
        bootstrap.ensure_custom_fields()
        bootstrap.ensure_custom_fields()
        names = set(CustomField.objects.values_list("name", flat=True))
        for name in ("public_url", "exposure_path", "upstream_target", "portainer_stack", "backup_location"):
            self.assertIn(name, names)
        cf = CustomField.objects.get(name="exposure_path")
        self.assertEqual(cf.choice_set.extra_choices[0][0], "cloudflared-direct")
        self.assertEqual(
            {f"{o.app_label}.{o.model}" for o in CustomField.objects.get(name="portainer_stack").object_types.all()},
            {"virtualization.virtualmachine", "ipam.service"},
        )

    def test_user_changes_preserved(self):
        bootstrap.ensure_custom_fields()
        cf = CustomField.objects.get(name="backup_location")
        cf.label = "Backups"
        cf.save()
        bootstrap.ensure_custom_fields()
        self.assertEqual(CustomField.objects.get(name="backup_location").label, "Backups")


@override_settings(LOGIN_REQUIRED=True)
class ServiceAccountsTest(TestCase):
    def setUp(self):
        env = {"CMDB_TOKEN_ZABBIX": ZABBIX_TOKEN, "CMDB_TOKEN_ORB_AGENT": ORB_TOKEN, "CMDB_TOKEN_NGINX_AGENT": ""}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        bootstrap.ensure_service_accounts()
        self.client = APIClient()

    def tearDown(self):
        self.env.stop()

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_accounts_created_once(self):
        bootstrap.ensure_service_accounts()
        self.assertTrue(User.objects.filter(username="svc-zabbix").exists())
        self.assertTrue(User.objects.filter(username="svc-orb-agent").exists())
        self.assertFalse(User.objects.filter(username="svc-nginx-agent").exists())
        self.assertEqual(Token.objects.filter(user__username="svc-zabbix").count(), 1)

    def test_token_rotation(self):
        new = "nbt_" + "e" * 12 + "." + "f" * 40
        with mock.patch.dict(os.environ, {"CMDB_TOKEN_ZABBIX": new}):
            bootstrap.ensure_service_accounts()
        tokens = Token.objects.filter(user__username="svc-zabbix")
        self.assertEqual(tokens.count(), 1)
        self.assertEqual(tokens.first().key, "e" * 12)

    def test_health_requires_auth(self):
        resp = self.client.get(reverse("plugins-api:netbox_cmdb-api:health"))
        self.assertIn(resp.status_code, (401, 403))

    def test_zabbix_reads_health_but_cannot_report(self):
        self._auth(ZABBIX_TOKEN)
        resp = self.client.get(reverse("plugins-api:netbox_cmdb-api:health"))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("sources", resp.json())
        resp = self.client.post(
            reverse("plugins-api:netbox_cmdb-api:sources"), {"source": "x", "status": "ok"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_agent_reports(self):
        self._auth(ORB_TOKEN)
        url = reverse("plugins-api:netbox_cmdb-api:sources")
        resp = self.client.post(url, {"source": "network-scan", "status": "ok", "message": "1 run"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        resp = self.client.post(url, {"source": "network-scan", "status": "failed", "message": "nmap"}, format="json")
        status = SourceStatus.objects.get(name="network-scan")
        self.assertEqual((status.status, status.run_count, status.failure_count), ("failed", 2, 1))
        self.assertIsNotNone(status.last_success)


class HealthTest(TestCase):
    def test_expected_sources_never(self):
        health = build_health()
        self.assertEqual(health["sources"]["proxmox"]["status"], "never")
        self.assertEqual(health["status"], "degraded")

    def test_all_ok(self):
        for name in ("proxmox", "cloudflare", "network-scan", "nginx"):
            SourceStatus.report(name, True, "ok")
        health = build_health()
        self.assertEqual(health["status"], "ok", health)
        self.assertEqual(health["unhealthy_count"], 0)

    def test_stale(self):
        SourceStatus.report("proxmox", True, "ok", when=timezone.now() - timedelta(hours=30))
        self.assertTrue(SourceStatus.objects.get(name="proxmox").is_stale)
        self.assertIn("proxmox", build_health()["unhealthy_sources"])


class ProxmoxEndpointTest(TestCase):
    def test_endpoint_from_env(self):
        from proxmox2netbox.models import ProxmoxEndpoint

        env = {
            "PROXMOX_HOST": "192.168.1.10",
            "PROXMOX_USER": "netbox@pve",
            "PROXMOX_TOKEN_NAME": "cmdb",
            "PROXMOX_TOKEN_VALUE": "secret",
        }
        with mock.patch.dict(os.environ, env):
            bootstrap.ensure_proxmox_endpoint()
            bootstrap.ensure_proxmox_endpoint()
        self.assertEqual(ProxmoxEndpoint.objects.count(), 1)
        ep = ProxmoxEndpoint.objects.get()
        self.assertEqual((ep.domain, ep.token_name, ep.verify_ssl), ("192.168.1.10", "cmdb", False))
        with mock.patch.dict(os.environ, {**env, "PROXMOX_TOKEN_VALUE": "rotated"}):
            bootstrap.ensure_proxmox_endpoint()
        self.assertEqual(ProxmoxEndpoint.objects.get().token_value, "rotated")

    def test_no_endpoint_job_reports_failure(self):
        from netbox.jobs import JobFailed

        from netbox_cmdb.jobs import run_proxmox_sync

        with self.assertRaises(JobFailed):
            run_proxmox_sync()
        self.assertEqual(SourceStatus.objects.get(name="proxmox").status, "failed")


class SyncsTest(TestCase):
    def test_enqueue_all_and_views(self):
        from core.models import Job
        from proxmox2netbox.models import ProxmoxEndpoint

        from netbox_cmdb.syncs import enqueue_all

        self.assertEqual(enqueue_all(), [])  # nothing configured
        ProxmoxEndpoint(name="pve", domain="pve.lan", token_name="t", token_value="v").save()
        with mock.patch("netbox_cmdb.syncs.get_plugin_config", return_value=""):
            self.assertEqual(enqueue_all(), ["CMDB - Proxmox sync"])
            self.assertEqual(enqueue_all(), [])  # already waiting: no duplicate
        self.assertEqual(Job.objects.filter(name="CMDB - Proxmox sync", interval__isnull=True).count(), 1)

        user = User.objects.create_superuser("admin", "a@b.c", "pw")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("plugins:netbox_cmdb:sourcestatus_list")).status_code, 200)
        self.assertEqual(self.client.post(reverse("plugins:netbox_cmdb:run_syncs")).status_code, 302)
        old = SourceStatus.report("docker-docker", True, "ok")
        resp = self.client.post(reverse("plugins:netbox_cmdb:forget_source", args=[old.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SourceStatus.objects.filter(name="docker-docker").exists())
