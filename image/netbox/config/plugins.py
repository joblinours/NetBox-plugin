# Plugin activation and configuration, baked into the image.
# No secret here: every sensitive or site-specific value comes from the stack
# environment variables (see deploy/stack.env.example).
#
# Activation et configuration des plugins, intégrées à l'image.
# Aucun secret ici : tout vient des variables d'environnement de la stack.
from os import environ


def _env(name, default=""):
    return environ.get(name, default).strip()


def _env_list(name):
    return [v.strip() for v in environ.get(name, "").replace(";", ",").split(",") if v.strip()]


def _env_int(name, default):
    try:
        return int(environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name, default):
    value = environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


PLUGINS = [
    "netbox_diode_plugin",
    "netbox_topology_views",
    "proxmox2netbox",
    "netbox_dns",
    "netbox_lists",
    "netbox_security",
    "netbox_custom_objects",
    "netbox_routing",
    "netbox_cloudflare_tunnel",
    "netbox_cmdb",
]

PLUGINS_CONFIG = {
    "netbox_diode_plugin": {
        # Diode entry point as seen from inside the stack (gateway container).
        "diode_target_override": _env("DIODE_TARGET_INTERNAL", "grpc://diode-gateway:80/diode"),
        # Address shown in the UI (the published port on the Docker host).
        "diode_target_display": _env("DIODE_TARGET_DISPLAY") or None,
        "diode_username": _env("DIODE_NETBOX_USERNAME", "diode"),
        "netbox_to_diode_client_secret": _env("DIODE_CLIENT_SECRET_NETBOX_TO_DIODE") or None,
    },
    "netbox_topology_views": {
        "static_image_directory": "netbox_topology_views/img",
        "allow_coordinates_saving": True,
        "always_save_coordinates": True,
    },
    "netbox_dns": {},
    "netbox_lists": {},
    "netbox_security": {},
    "netbox_custom_objects": {},
    "netbox_routing": {},
    "netbox_cloudflare_tunnel": {
        "api_token": _env("CLOUDFLARE_API_TOKEN"),
        "account_id": _env("CLOUDFLARE_ACCOUNT_ID"),
        "tunnel_ids": _env_list("CLOUDFLARE_TUNNEL_IDS"),
        "nginx_hosts": _env_list("NGINX_PROXY_HOSTS"),
        "create_services": _env_bool("CLOUDFLARE_CREATE_SERVICES", True),
        "sync_interval": _env_int("CLOUDFLARE_SYNC_INTERVAL", 1440),
    },
    "netbox_cmdb": {
        "proxmox_sync_interval": _env_int("PROXMOX_SYNC_INTERVAL", 1440),
        "max_age_hours": _env_int("SOURCE_MAX_AGE_HOURS", 26),
        "expected_sources": _env_list("CMDB_EXPECTED_SOURCES") or ["proxmox", "cloudflare", "network-scan", "nginx"],
    },
}
