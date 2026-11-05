"""AdGuard Home rewrites -> NetBox.

1. Every rewrite of every instance becomes a ``DNSRewrite``, linked to the NetBox
   IP address and host (VM / device) it points to (CNAME chains are followed).
2. The ``local_domains`` custom field of those IPs / hosts lists their local names.
3. Optionally, the rewrites are mirrored as A / AAAA / CNAME records in
   netbox-plugin-dns (zones found by suffix, or created).

Idempotent; rewrites deleted in AdGuard disappear from NetBox (only for instances
that answered, so an AdGuard outage never wipes data).
"""

import ipaddress
import logging
from dataclasses import asdict, dataclass, field

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import AnswerTypeChoices, DNSRewrite

logger = logging.getLogger("netbox.plugins.netbox_adguard")


@dataclass
class SyncResult:
    instances_ok: list = field(default_factory=list)
    instances_failed: list = field(default_factory=list)
    rewrites: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unresolved: list = field(default_factory=list)
    dns_records_created: int = 0
    dns_records_updated: int = 0
    dns_records_deleted: int = 0
    dns_errors: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def answer_type(answer):
    if answer.upper() in ("A", "AAAA"):  # "keep the upstream answer" special values
        return AnswerTypeChoices.OTHER
    try:
        ip = ipaddress.ip_address(answer)
        return AnswerTypeChoices.A if ip.version == 4 else AnswerTypeChoices.AAAA
    except ValueError:
        return AnswerTypeChoices.CNAME


def _parent_of_ip(ip):
    obj = ip.assigned_object if ip else None
    if obj is None:
        return None
    return getattr(obj, "device", None) or getattr(obj, "virtual_machine", None)


def resolve(answer, by_domain, depth=0):
    """Return (IPAddress or None, host or None, explanation)."""
    from dcim.models import Device
    from ipam.models import IPAddress
    from virtualization.models import VirtualMachine

    kind = answer_type(answer)
    if kind in (AnswerTypeChoices.A, AnswerTypeChoices.AAAA):
        ips = list(IPAddress.objects.filter(address__net_host=answer))
        ips.sort(key=lambda i: i.assigned_object_id is None)
        if not ips:
            return None, None, f"IP {answer} unknown in NetBox"
        return ips[0], _parent_of_ip(ips[0]), f"IP {answer}"
    if kind == AnswerTypeChoices.OTHER:
        return None, None, "upstream answer kept"
    target = answer.lower()
    if target in by_domain and depth < 5:
        ip, host, how = resolve(by_domain[target], by_domain, depth + 1)
        return ip, host, f"CNAME {target} -> {how}"
    ip = IPAddress.objects.filter(dns_name__iexact=target).first()
    if ip:
        return ip, _parent_of_ip(ip), f"DNS name {target}"
    for model in (VirtualMachine, Device):
        obj = model.objects.filter(name__iexact=target.split(".")[0]).first()
        if obj:
            return obj.primary_ip, obj, f"{model._meta.verbose_name} {obj.name}"
    return None, None, f"{target} unknown in NetBox"


def _set_local_domains(obj, domains):
    data = dict(obj.custom_field_data or {})
    wanted = ", ".join(sorted(domains)) if domains else None
    if data.get("local_domains") == wanted:
        return False
    if hasattr(obj, "snapshot"):
        obj.snapshot()
    data["local_domains"] = wanted
    obj.custom_field_data = data
    obj.save()
    return True


def update_local_domains():
    """Recompute the local_domains custom field of IPs and hosts from the stored rewrites."""
    from dcim.models import Device
    from ipam.models import IPAddress
    from virtualization.models import VirtualMachine

    wanted = {}
    for r in DNSRewrite.objects.filter(enabled=True):
        for obj in (r.ip_address, r.virtual_machine, r.device):
            if obj is not None:
                wanted.setdefault((obj._meta.label_lower, obj.pk), (obj, set()))[1].add(r.domain)
    for model in (IPAddress, VirtualMachine, Device):
        for obj in model.objects.filter(custom_field_data__local_domains__isnull=False).exclude(
            custom_field_data__local_domains=""
        ):
            if (obj._meta.label_lower, obj.pk) not in wanted:
                _set_local_domains(obj, set())
    for obj, domains in wanted.values():
        _set_local_domains(obj, domains)


# --------------------------------------------------------------------------- netbox-plugin-dns


def _dns_available():
    return apps.is_installed("netbox_dns")


def _find_or_create_zone(domain, settings, cache):
    from netbox_dns.models import NameServer, View, Zone

    labels = domain.split(".")
    for i in range(len(labels)):
        candidate = ".".join(labels[i:])
        if candidate in cache:
            return cache[candidate]
        zone = Zone.objects.filter(name=candidate).first()
        if zone:
            cache[candidate] = zone
            return zone
    if not settings.get("auto_create_zones") or len(labels) < 2:
        return None
    name = ".".join(labels[1:])
    ns, _ = NameServer.objects.get_or_create(name=settings.get("nameserver") or "adguard.home.arpa")
    zone = Zone(
        view=View.get_default_view(),
        name=name,
        soa_mname=ns,
        soa_rname=f"hostmaster.{name}",
        description="Created by the AdGuard sync",
    )
    zone.full_clean()
    zone.save()
    zone.nameservers.add(ns)
    cache[name] = zone
    return zone


def mirror_to_netbox_dns(settings, result):
    from extras.models import Tag
    from netbox_dns.models import Record

    tag_name = settings.get("record_tag") or "adguard"
    tag, _ = Tag.objects.get_or_create(slug=tag_name.lower(), defaults={"name": tag_name})
    zones = {}
    kept = set()
    for rw in DNSRewrite.objects.filter(enabled=True).order_by("domain"):
        if rw.answer_type == AnswerTypeChoices.OTHER:
            continue
        try:
            with transaction.atomic():
                zone = _find_or_create_zone(rw.domain, settings, zones)
                if zone is None:
                    raise ValidationError("no zone")
                name = "@" if rw.domain == zone.name else rw.domain[: -(len(zone.name) + 1)]
                value = rw.answer if rw.answer_type != AnswerTypeChoices.CNAME else rw.answer.rstrip(".") + "."
                record = Record.objects.filter(pk=rw.dns_record_id).first() if rw.dns_record_id else None
                if record is None:
                    record = Record.objects.filter(zone=zone, name=name, type=rw.answer_type, value=value).first()
                if record is None:
                    record = Record(
                        zone=zone, name=name, type=rw.answer_type, value=value, description="AdGuard rewrite"
                    )
                    record.full_clean()
                    record.save()
                    result.dns_records_created += 1
                elif (record.zone_id, record.name, record.type, record.value) != (zone.pk, name, rw.answer_type, value):
                    record.snapshot()
                    record.zone, record.name, record.type, record.value = zone, name, rw.answer_type, value
                    record.full_clean()
                    record.save()
                    result.dns_records_updated += 1
                if not record.tags.filter(pk=tag.pk).exists():
                    record.tags.add(tag)
                if rw.dns_record_id != record.pk:
                    DNSRewrite.objects.filter(pk=rw.pk).update(dns_record_id=record.pk)
                kept.add(record.pk)
        except (ValidationError, IntegrityError) as exc:
            msg = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
            result.dns_errors.append(f"{rw.domain}: {'; '.join(msg)[:200]}")
    stale = Record.objects.filter(tags=tag).exclude(pk__in=kept)
    result.dns_records_deleted = stale.count()
    stale.delete()


# --------------------------------------------------------------------------- main


def sync(clients, settings, log=logger):
    """``clients``: list of objects with ``base_url`` and ``rewrites()`` (AdGuardClient or test double)."""
    from virtualization.models import VirtualMachine

    from .client import AdGuardError

    result = SyncResult()
    fetched = {}
    for client in clients:
        try:
            fetched[client.base_url] = client.rewrites()
            result.instances_ok.append(client.base_url)
        except AdGuardError as exc:
            result.instances_failed.append(str(exc))
            log.warning("AdGuard instance failed: %s", exc)
    if not fetched:
        return result

    by_domain = {}
    for rewrites in fetched.values():
        for r in rewrites:
            if r["enabled"]:
                by_domain.setdefault(r["domain"], r["answer"])

    with transaction.atomic():
        seen = []
        for instance, rewrites in fetched.items():
            for r in rewrites:
                ip, host, how = resolve(r["answer"], by_domain)
                values = {
                    "answer_type": answer_type(r["answer"]),
                    "enabled": r["enabled"],
                    "ip_address": ip,
                    "virtual_machine": host if isinstance(host, VirtualMachine) else None,
                    "device": host if host is not None and not isinstance(host, VirtualMachine) else None,
                    "resolution": how[:255],
                }
                obj = DNSRewrite.objects.filter(instance=instance, domain=r["domain"], answer=r["answer"]).first()
                if obj is None:
                    obj = DNSRewrite.objects.create(instance=instance, domain=r["domain"], answer=r["answer"], **values)
                    result.created += 1
                else:
                    changed = [k for k, v in values.items() if getattr(obj, k) != v]
                    if changed:
                        obj.snapshot()
                        for k in changed:
                            setattr(obj, k, values[k])
                        obj.save()
                        result.updated += 1
                seen.append(obj.pk)
                result.rewrites += 1
                if host is None and r["enabled"]:
                    result.unresolved.append(f"{r['domain']}: {how}")
        stale = DNSRewrite.objects.filter(instance__in=list(fetched)).exclude(pk__in=seen)
        result.deleted = stale.count()
        stale.delete()
        update_local_domains()

    if settings.get("sync_netbox_dns", True) and _dns_available():
        mirror_to_netbox_dns(settings, result)
    for line in result.dns_errors:
        log.warning("netbox_dns: %s", line)
    return result
