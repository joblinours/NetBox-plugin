#!/usr/bin/env python3
"""Generate the Portainer stack variables for the CMDB, with fresh random secrets.

    python3 tools/generate-env.py > cmdb.env          # new file
    python3 tools/generate-env.py --update cmdb.env   # keep existing values, add missing ones

Secrets only use [A-Za-z0-9]: safe in a PostgreSQL DSN, a URL, a shell and YAML.
Store the result in Vaultwarden, then paste it into Portainer
(Stacks > Add stack > Environment variables > Advanced mode).
Never commit the generated file.

Génère les variables de la stack Portainer avec des secrets aléatoires
(uniquement [A-Za-z0-9]). À ranger dans Vaultwarden, jamais dans le dépôt.
"""

import argparse
import secrets
import string
import sys
from pathlib import Path

ALPHANUM = string.ascii_letters + string.digits


def rand(length=48):
    return "".join(secrets.choice(ALPHANUM) for _ in range(length))


def netbox_token():
    """NetBox v2 API token: nbt_<12-char key>.<40-char secret>."""
    return f"nbt_{rand(12)}.{rand(40)}"


# (name, value or generator, comment). Section headers are strings.
VARIABLES = [
    "Images",
    ("CMDB_IMAGE_TAG", "latest", "latest (main), dev, a version (v1.2.3) or sha-<commit>"),
    ("DIODE_VERSION", "2.4.0", "netboxlabs/diode-* images"),
    "Docker host / published ports",
    ("DOCKER_HOST_IP", "192.168.1.13", "LAN IP of the Docker host (LXC)"),
    ("BIND_ADDRESS", "0.0.0.0", "set to DOCKER_HOST_IP to listen on the LAN interface only"),
    ("NETBOX_PORT", "8000", "NetBox UI / API"),
    ("DIODE_GRPC_PORT", "8081", "Diode gRPC entry point (orb-agent, Nginx agent)"),
    ("TZ", "Europe/Paris", None),
    "NetBox",
    ("NETBOX_ADMIN_USER", "lucas", "named admin account, created on first start only"),
    ("NETBOX_ADMIN_EMAIL", "admin@example.com", None),
    ("NETBOX_ADMIN_PASSWORD", lambda: rand(24), None),
    ("NETBOX_SECRET_KEY", lambda: rand(64), None),
    ("NETBOX_API_TOKEN_PEPPER", lambda: rand(64), "changing it invalidates every API token"),
    ("NETBOX_DB_PASSWORD", lambda: rand(32), None),
    ("NETBOX_REDIS_PASSWORD", lambda: rand(32), None),
    ("NETBOX_ALLOWED_HOSTS", "*", "space separated, e.g. 'cmdb.lan 192.168.1.13'"),
    ("NETBOX_CSRF_TRUSTED_ORIGINS", "", "only needed behind an HTTPS reverse proxy"),
    "Diode",
    ("DIODE_DB_PASSWORD", lambda: rand(32), None),
    ("DIODE_POSTGRES_ADMIN_PASSWORD", lambda: rand(32), None),
    ("DIODE_REDIS_PASSWORD", lambda: rand(32), None),
    ("HYDRA_DB_PASSWORD", lambda: rand(32), None),
    ("HYDRA_SECRETS_SYSTEM", lambda: rand(48), "Hydra system secret"),
    ("DIODE_CLIENT_SECRET_DIODE_TO_NETBOX", lambda: rand(48), "OAuth2 client diode-to-netbox"),
    ("DIODE_CLIENT_SECRET_NETBOX_TO_DIODE", lambda: rand(48), "OAuth2 client netbox-to-diode"),
    ("DIODE_CLIENT_SECRET_ORB_AGENT", lambda: rand(48), "OAuth2 client orb-agent (network scan)"),
    ("DIODE_CLIENT_SECRET_NGINX_AGENT", lambda: rand(48), "OAuth2 client nginx-agent (copy into the agent's env file)"),
    "API tokens, one per consumer (NetBox v2 format)",
    ("CMDB_TOKEN_ORB_AGENT", netbox_token, "orb-agent -> scan status"),
    ("CMDB_TOKEN_NGINX_AGENT", netbox_token, "Nginx agent -> run status (copy into the agent's env file)"),
    ("CMDB_TOKEN_ZABBIX", netbox_token, "Zabbix -> {$CMDB.TOKEN} macro"),
    "Proxmox (read-only API token, role PVEAuditor)",
    ("PROXMOX_HOST", "", "IP or DNS name of any cluster node"),
    ("PROXMOX_PORT", "8006", None),
    ("PROXMOX_USER", "netbox@pve", None),
    ("PROXMOX_TOKEN_NAME", "cmdb", None),
    ("PROXMOX_TOKEN_VALUE", "", "token secret (UUID) shown once by Proxmox"),
    ("PROXMOX_VERIFY_SSL", "false", "true once Proxmox has a trusted certificate"),
    ("PROXMOX_SYNC_INTERVAL", "1440", "minutes"),
    "Cloudflare Tunnel (read-only token: Account > Cloudflare Tunnel > Read)",
    ("CLOUDFLARE_API_TOKEN", "", None),
    ("CLOUDFLARE_ACCOUNT_ID", "", None),
    ("CLOUDFLARE_TUNNEL_IDS", "", "optional, comma separated; empty = all tunnels"),
    ("CLOUDFLARE_SYNC_INTERVAL", "1440", "minutes"),
    ("NGINX_PROXY_HOSTS", "", "IP(s) of revers-proxy, comma separated: origin = this host -> 'via Nginx'"),
    "Network scan (orb-agent)",
    ("SCAN_TARGETS", "192.168.1.0/24", "comma separated"),
    ("SCAN_SCHEDULE", "0 3 * * *", "cron, daily at 03:00"),
    ("SCAN_TOP_PORTS", "1000", None),
    ("SCAN_TIMEOUT_MINUTES", "120", None),
    ("SCAN_STARTUP", "true", "also scan once when the container starts"),
    "Health",
    ("SOURCE_MAX_AGE_HOURS", "26", "a source not successful for longer is reported to Zabbix"),
]


def parse_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value
    return values


def render(existing=None, placeholders=False):
    existing = existing or {}
    out = [
        "# CMDB homelab — Portainer stack variables. KEEP SECRET: store in Vaultwarden, never commit.",
        "# Generated by tools/generate-env.py",
    ]
    for item in VARIABLES:
        if isinstance(item, str):
            out += ["", f"# --- {item}"]
            continue
        name, value, comment = item
        if name in existing:
            v = existing[name]
        elif callable(value):
            v = "<generated by tools/generate-env.py>" if placeholders else value()
        else:
            v = value
        if comment:
            out.append(f"# {comment}")
        out.append(f"{name}={v}")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", metavar="FILE", help="keep the values of FILE, only add missing variables")
    parser.add_argument("--example", action="store_true", help="write placeholders instead of secrets")
    parser.add_argument("--token", action="store_true", help="print one new NetBox API token and exit")
    parser.add_argument("--secret", action="store_true", help="print one new random secret and exit")
    args = parser.parse_args()
    if args.token or args.secret:
        print(netbox_token() if args.token else rand(48))
        return
    existing = parse_env(args.update) if args.update else None
    sys.stdout.write(render(existing, placeholders=args.example))


if __name__ == "__main__":
    main()
