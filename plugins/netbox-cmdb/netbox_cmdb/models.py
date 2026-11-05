from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone
from netbox.plugins import get_plugin_config


class SourceStatusChoices(models.TextChoices):
    OK = "ok", "OK"
    FAILED = "failed", "Failed"


class SourceStatus(models.Model):
    """Last known outcome of one automatic data source (Proxmox, Cloudflare, scan, Nginx...)."""

    name = models.SlugField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=SourceStatusChoices.choices)
    message = models.TextField(blank=True)
    details = models.JSONField(blank=True, default=dict)
    last_run = models.DateTimeField()
    last_success = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("name",)
        verbose_name = "source status"
        verbose_name_plural = "source statuses"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_cmdb:sourcestatus_list")

    @classmethod
    def report(cls, name, ok, message="", details=None, when=None):
        """Record one run of a source. Returns the updated SourceStatus."""
        when = when or timezone.now()
        obj, _ = cls.objects.get_or_create(
            name=name,
            defaults={"status": SourceStatusChoices.OK if ok else SourceStatusChoices.FAILED, "last_run": when},
        )
        obj.status = SourceStatusChoices.OK if ok else SourceStatusChoices.FAILED
        obj.message = (message or "")[:4000]
        obj.details = details or {}
        obj.last_run = when
        obj.run_count += 1
        if ok:
            obj.last_success = when
        else:
            obj.failure_count += 1
        obj.save()
        return obj

    @property
    def age_hours(self):
        if not self.last_success:
            return None
        return round((timezone.now() - self.last_success).total_seconds() / 3600, 2)

    @property
    def is_stale(self):
        max_age = get_plugin_config("netbox_cmdb", "max_age_hours")
        return self.last_success is None or timezone.now() - self.last_success > timedelta(hours=max_age)

    @property
    def healthy(self):
        return self.status == SourceStatusChoices.OK and not self.is_stale
