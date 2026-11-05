"""Idempotent provisioning run at every NetBox start (``manage.py cmdb_bootstrap``).

Everything here is driven by environment variables of the Portainer stack, so the
CMDB needs no manual set-up and no file on the host:

* the base data model (custom fields of the specification);
* one service account + API token per consumer, with minimal permissions;
* the Proxmox endpoint used by proxmox2netbox.

Objects are created when missing and corrected when they drift from the
environment; nothing created by hand is ever deleted.
"""

import logging
import os

from django.db import transaction

logger = logging.getLogger("netbox.plugins.netbox_cmdb")

MANAGED = "Managed by netbox_cmdb (stack variables)"

EXPOSURE_CHOICE_SET = "CMDB - exposure path"
EXPOSURE_CHOICES = [
    ["cloudflared-direct", "cloudflared direct"],
    ["nginx", "via Nginx"],
]

# name, label, type, object types, extra options
CUSTOM_FIELDS = [
    ("public_url", "URL publique", "text", ["ipam.service"], {"description": "Public hostname, e.g. mail.example.com"}),
    (
        "exposure_path",
        "Chemin d'exposition",
        "select",
        ["ipam.service"],
        {"choice_set": EXPOSURE_CHOICE_SET, "description": "How the public URL reaches the service"},
    ),
    (
        "upstream_target",
        "Cible amont",
        "text",
        ["ipam.service"],
        {"description": "Reverse-proxy upstream (proxy_pass)"},
    ),
    (
        "portainer_stack",
        "Stack Portainer",
        "text",
        ["virtualization.virtualmachine", "ipam.service"],
        {"description": "Portainer stack name"},
    ),
    (
        "backup_location",
        "Emplacement des sauvegardes",
        "text",
        ["virtualization.virtualmachine", "dcim.device"],
        {"description": "Where backups are stored, e.g. DAS"},
    ),
]

# username, env var holding the token, permissions as (object type, actions)
SERVICE_ACCOUNTS = [
    ("svc-orb-agent", "CMDB_TOKEN_ORB_AGENT", [("netbox_cmdb.sourcestatus", ["view", "change"])]),
    ("svc-nginx-agent", "CMDB_TOKEN_NGINX_AGENT", [("netbox_cmdb.sourcestatus", ["view", "change"])]),
    ("svc-zabbix", "CMDB_TOKEN_ZABBIX", [("netbox_cmdb.sourcestatus", ["view"])]),
]


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


def _env_bool(name, default=True):
    value = _env(name)
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def parse_v2_token(value):
    """Split ``nbt_<key>.<secret>`` into (key, secret). Raises ValueError on bad input."""
    value = (value or "").strip()
    if value.startswith("nbt_"):
        value = value[4:]
    key, sep, secret = value.partition(".")
    if not sep or len(key) != 12 or len(secret) < 40 or not key.isalnum() or not secret.isalnum():
        raise ValueError("expected nbt_<12 alphanumeric chars>.<40+ alphanumeric chars>")
    return key, secret


def ensure_custom_fields(stdout=None):
    from core.models import ObjectType
    from extras.models import CustomField, CustomFieldChoiceSet

    choice_set, created = CustomFieldChoiceSet.objects.get_or_create(
        name=EXPOSURE_CHOICE_SET,
        defaults={"extra_choices": EXPOSURE_CHOICES, "description": MANAGED},
    )
    if not created:
        existing = {c[0] for c in (choice_set.extra_choices or [])}
        missing = [c for c in EXPOSURE_CHOICES if c[0] not in existing]
        if missing:
            choice_set.extra_choices = list(choice_set.extra_choices or []) + missing
            choice_set.save()

    for name, label, cf_type, object_types, extra in CUSTOM_FIELDS:
        extra = dict(extra)
        if extra.get("choice_set"):
            extra["choice_set"] = choice_set
        cf, created = CustomField.objects.get_or_create(
            name=name, defaults={"label": label, "type": cf_type, "group_name": "CMDB", **extra}
        )
        wanted = [ObjectType.objects.get_by_natural_key(*ot.split(".")) for ot in object_types]
        current = set(cf.object_types.all())
        to_add = [ot for ot in wanted if ot not in current]
        if to_add:
            cf.object_types.add(*to_add)
        if created and stdout:
            stdout.write(f"  custom field {name} created")


def ensure_service_accounts(stdout=None):
    from core.models import ObjectType
    from users.choices import TokenVersionChoices
    from users.models import ObjectPermission, Token, User

    for username, env_var, permissions in SERVICE_ACCOUNTS:
        raw = _env(env_var)
        if not raw:
            if stdout:
                stdout.write(f"  {env_var} not set: account {username} skipped")
            continue
        try:
            key, secret = parse_v2_token(raw)
        except ValueError as exc:
            logger.error("%s is invalid (%s); account %s skipped", env_var, exc, username)
            if stdout:
                stdout.write(f"  {env_var} invalid ({exc}): account {username} skipped")
            continue

        user, _ = User.objects.get_or_create(username=username, defaults={"is_active": True})
        if user.has_usable_password():
            user.set_unusable_password()
            user.save()

        for object_type, actions in permissions:
            perm_name = f"cmdb:{username}:{object_type}"
            perm, _ = ObjectPermission.objects.get_or_create(
                name=perm_name, defaults={"actions": actions, "description": MANAGED}
            )
            if sorted(perm.actions) != sorted(actions):
                perm.actions = actions
                perm.save()
            perm.object_types.set([ObjectType.objects.get_by_natural_key(*object_type.split("."))])
            perm.users.add(user)

        token = Token.objects.filter(user=user, key=key).first()
        if token and token.validate(secret):
            continue
        # Secret changed (or first start): replace the managed token(s) of this account.
        Token.objects.filter(user=user, description=MANAGED).delete()
        Token.objects.filter(key=key).delete()
        token = Token(user=user, version=TokenVersionChoices.V2, key=key, description=MANAGED, write_enabled=True)
        token.token = secret
        token.save()
        if stdout:
            stdout.write(f"  token for {username} (re)created")


def ensure_proxmox_endpoint(stdout=None):
    host = _env("PROXMOX_HOST")
    if not host:
        if stdout:
            stdout.write("  PROXMOX_HOST not set: Proxmox endpoint skipped")
        return
    try:
        from proxmox2netbox.models import ProxmoxEndpoint
    except ImportError:
        return

    name = _env("PROXMOX_ENDPOINT_NAME", "Proxmox (stack)")
    values = {
        "domain": host,
        "port": int(_env("PROXMOX_PORT", "8006")),
        "username": _env("PROXMOX_USER", "netbox@pve"),
        "token_name": _env("PROXMOX_TOKEN_NAME"),
        "token_value": _env("PROXMOX_TOKEN_VALUE"),
        "password": None,
        "verify_ssl": _env_bool("PROXMOX_VERIFY_SSL", False),
        "sync_enabled": True,
    }
    endpoint = ProxmoxEndpoint.objects.filter(name=name).first()
    if endpoint is None:
        # save() bypasses form validation, so an IP address is accepted as "domain".
        endpoint = ProxmoxEndpoint(name=name, **values)
        endpoint.save()
        if stdout:
            stdout.write(f"  Proxmox endpoint {name} created")
        return
    changed = False
    for field, value in values.items():
        if getattr(endpoint, field) != value:
            setattr(endpoint, field, value)
            changed = True
    if changed:
        endpoint.save()
        if stdout:
            stdout.write(f"  Proxmox endpoint {name} updated")


def run(stdout=None):
    with transaction.atomic():
        ensure_custom_fields(stdout)
    with transaction.atomic():
        ensure_service_accounts(stdout)
    with transaction.atomic():
        ensure_proxmox_endpoint(stdout)
