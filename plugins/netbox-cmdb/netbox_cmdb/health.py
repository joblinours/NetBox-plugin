"""Health summary consumed by Zabbix (and shown in the UI)."""

from django.db import connection
from django.utils import timezone
from netbox.plugins import get_plugin_config

from .models import SourceStatus


def _database_ok():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def build_health():
    expected = list(get_plugin_config("netbox_cmdb", "expected_sources") or [])
    max_age = get_plugin_config("netbox_cmdb", "max_age_hours")
    sources = {}
    for status in SourceStatus.objects.all():
        sources[status.name] = {
            "status": status.status,
            "healthy": status.healthy,
            "stale": status.is_stale,
            "last_run": status.last_run.isoformat() if status.last_run else None,
            "last_success": status.last_success.isoformat() if status.last_success else None,
            "age_hours": status.age_hours,
            "message": status.message,
        }
    for name in expected:
        sources.setdefault(
            name,
            {
                "status": "never",
                "healthy": False,
                "stale": True,
                "last_run": None,
                "last_success": None,
                "age_hours": None,
                "message": "Source never reported",
            },
        )
    unhealthy = sorted(name for name, s in sources.items() if not s["healthy"])
    db_ok = _database_ok()
    return {
        "time": timezone.now().isoformat(),
        "database": "ok" if db_ok else "failed",
        "max_age_hours": max_age,
        "sources": sources,
        "unhealthy_sources": unhealthy,
        "unhealthy_count": len(unhealthy),
        "status": "ok" if db_ok and not unhealthy else "degraded",
    }
