from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class ExposureChoices(models.TextChoices):
    DIRECT = "cloudflared-direct", "cloudflared direct"
    NGINX = "nginx", "via Nginx"
    OTHER = "other", "Other (non-HTTP origin)"


class Tunnel(NetBoxModel):
    tunnel_id = models.UUIDField(unique=True, verbose_name="Tunnel ID")
    name = models.CharField(max_length=255)
    account_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, blank=True)
    remote_config = models.BooleanField(default=True, help_text="Ingress managed from the Cloudflare dashboard")
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_cloudflare_tunnel:tunnel", args=[self.pk])


class PublicHostname(NetBoxModel):
    """One ingress rule of a tunnel: public hostname (+ optional path) -> origin service."""

    tunnel = models.ForeignKey(Tunnel, on_delete=models.CASCADE, related_name="hostnames")
    hostname = models.CharField(max_length=255)
    path = models.CharField(max_length=255, blank=True)
    origin = models.CharField(max_length=512, help_text="Origin service as configured in Cloudflare")
    origin_scheme = models.CharField(max_length=16, blank=True)
    origin_host = models.CharField(max_length=255, blank=True)
    origin_port = models.PositiveIntegerField(null=True, blank=True)
    exposure = models.CharField(max_length=32, choices=ExposureChoices.choices)
    # The service the public URL ends up on (backend). For "via Nginx" this is the
    # service behind the proxy when it could be resolved.
    service = models.ForeignKey("ipam.Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # For "via Nginx": the Nginx vhost service (pushed by the Nginx agent through Diode).
    proxy_service = models.ForeignKey(
        "ipam.Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    upstream = models.CharField(max_length=512, blank=True, help_text="Nginx upstream (proxy_pass)")
    resolution = models.CharField(max_length=255, blank=True, help_text="How the origin was resolved")

    class Meta:
        ordering = ("hostname", "path")
        constraints = [
            models.UniqueConstraint(fields=("tunnel", "hostname", "path"), name="ncft_unique_hostname_path"),
        ]

    def __str__(self):
        return f"{self.hostname}{self.path}" if self.path else self.hostname

    def get_absolute_url(self):
        return reverse("plugins:netbox_cloudflare_tunnel:publichostname", args=[self.pk])

    def get_exposure_color(self):
        return {"cloudflared-direct": "blue", "nginx": "green"}.get(self.exposure, "gray")
