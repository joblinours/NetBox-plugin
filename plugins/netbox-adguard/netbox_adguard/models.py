from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class AnswerTypeChoices(models.TextChoices):
    A = "A", "A"
    AAAA = "AAAA", "AAAA"
    CNAME = "CNAME", "CNAME"
    OTHER = "OTHER", "Other"


class DNSRewrite(NetBoxModel):
    """One AdGuard Home DNS rewrite: domain -> answer (IP or domain)."""

    instance = models.CharField(max_length=255, help_text="AdGuard Home URL the rewrite comes from")
    domain = models.CharField(max_length=255)
    answer = models.CharField(max_length=255)
    answer_type = models.CharField(max_length=8, choices=AnswerTypeChoices.choices)
    enabled = models.BooleanField(default=True)
    ip_address = models.ForeignKey("ipam.IPAddress", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    virtual_machine = models.ForeignKey(
        "virtualization.VirtualMachine", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    device = models.ForeignKey("dcim.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # netbox_dns.Record mirrored from this rewrite (plain id: netbox-plugin-dns is optional)
    dns_record_id = models.PositiveBigIntegerField(null=True, blank=True)
    resolution = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("domain", "answer")
        verbose_name = "DNS rewrite"
        constraints = [
            models.UniqueConstraint(fields=("instance", "domain", "answer"), name="nag_unique_rewrite"),
        ]

    def __str__(self):
        return f"{self.domain} -> {self.answer}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_adguard:dnsrewrite", args=[self.pk])

    @property
    def host(self):
        return self.virtual_machine or self.device

    @property
    def host_name(self):
        return self.host.name if self.host else ""

    @property
    def dns_record(self):
        if not self.dns_record_id:
            return None
        try:
            from netbox_dns.models import Record
        except ImportError:
            return None
        return Record.objects.filter(pk=self.dns_record_id).first()
