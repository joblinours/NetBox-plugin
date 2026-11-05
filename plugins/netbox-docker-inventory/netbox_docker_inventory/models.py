from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class DockerHost(NetBoxModel):
    name = models.CharField(max_length=255, unique=True, help_text="Name reported by the agent (NetBox VM/device name)")
    virtual_machine = models.ForeignKey(
        "virtualization.VirtualMachine", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    device = models.ForeignKey("dcim.Device", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    hostname = models.CharField(max_length=255, blank=True, help_text="Docker engine hostname")
    engine_version = models.CharField(max_length=64, blank=True)
    operating_system = models.CharField(max_length=255, blank=True)
    agent_version = models.CharField(max_length=32, blank=True)
    addresses = ArrayField(models.CharField(max_length=64), blank=True, default=list)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_docker_inventory:dockerhost", args=[self.pk])

    @property
    def parent(self):
        return self.virtual_machine or self.device


class DockerNetwork(NetBoxModel):
    host = models.ForeignKey(DockerHost, on_delete=models.CASCADE, related_name="networks")
    network_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    driver = models.CharField(max_length=64, blank=True)
    scope = models.CharField(max_length=32, blank=True)
    internal = models.BooleanField(default=False)
    subnets = ArrayField(models.CharField(max_length=64), blank=True, default=list)
    gateways = ArrayField(models.CharField(max_length=64), blank=True, default=list)
    stack = models.CharField(max_length=255, blank=True, help_text="Compose project owning the network")

    class Meta:
        ordering = ("host", "name")
        constraints = [models.UniqueConstraint(fields=("host", "name"), name="ndi_unique_network")]

    def __str__(self):
        return f"{self.name} ({self.host})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_docker_inventory:dockernetwork", args=[self.pk])


class DockerContainer(NetBoxModel):
    host = models.ForeignKey(DockerHost, on_delete=models.CASCADE, related_name="containers")
    container_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    image = models.CharField(max_length=512, blank=True)
    state = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=255, blank=True)
    health = models.CharField(max_length=32, blank=True)
    stack = models.CharField(max_length=255, blank=True, help_text="Compose project / Portainer stack")
    compose_service = models.CharField(max_length=255, blank=True)
    restart_policy = models.CharField(max_length=32, blank=True)
    network_mode = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    # [{"private_port": 80, "public_port": 8080, "ip": "0.0.0.0", "type": "tcp"}]
    ports = models.JSONField(blank=True, default=list)
    # [{"network": "web", "ip": "172.18.0.2", "aliases": ["app"]}]
    network_attachments = models.JSONField(blank=True, default=list)
    # [{"type": "volume", "source": "data", "destination": "/data", "rw": true}]
    mounts = models.JSONField(blank=True, default=list)
    labels = models.JSONField(blank=True, default=dict)
    networks = models.ManyToManyField(DockerNetwork, blank=True, related_name="containers")
    service = models.ForeignKey(
        "ipam.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="NetBox service created for the published ports",
    )

    class Meta:
        ordering = ("host", "stack", "name")
        constraints = [models.UniqueConstraint(fields=("host", "name"), name="ndi_unique_container")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_docker_inventory:dockercontainer", args=[self.pk])

    def get_state_color(self):
        return {"running": "green", "exited": "red", "restarting": "orange", "paused": "gray"}.get(self.state, "gray")

    @property
    def published_ports(self):
        return [p for p in self.ports or [] if p.get("public_port")]

    @property
    def ports_display(self):
        parts = []
        for p in self.ports or []:
            if p.get("public_port"):
                parts.append(f"{p['public_port']}->{p.get('private_port')}/{p.get('type', 'tcp')}")
            else:
                parts.append(f"{p.get('private_port')}/{p.get('type', 'tcp')}")
        return ", ".join(sorted(set(parts)))

    def summary(self):
        return {
            "name": self.name,
            "host": self.host.name,
            "stack": self.stack or None,
            "image": self.image,
            "state": self.state,
            "health": self.health or None,
            "published_ports": [
                f"{p.get('ip') or '0.0.0.0'}:{p['public_port']}->{p.get('private_port')}/{p.get('type', 'tcp')}"
                for p in self.published_ports
            ],
            "networks": [
                {"network": n.get("network"), "ip": n.get("ip") or None} for n in self.network_attachments or []
            ],
            "network_mode": self.network_mode or None,
            "volumes": [f"{m.get('source')}:{m.get('destination')}" for m in self.mounts or []],
        }
