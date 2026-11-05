#!/usr/bin/env python3
"""Relays the outcome of each orb-agent network scan to NetBox (netbox_cmdb source health).

Polls the local network-discovery backend status API and POSTs every newly
finished run to /api/plugins/cmdb/sources/ as source "network-scan", which the
Zabbix template then watches. Standard library only.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

STATUS_URL = f"http://127.0.0.1:{os.environ.get('ORB_DISCOVERY_PORT', '8073')}/api/v1/status"
NETBOX_URL = os.environ["NETBOX_URL"].rstrip("/") + "/api/plugins/cmdb/sources/"
TOKEN = os.environ["NETBOX_TOKEN"]
SOURCE = os.environ.get("CMDB_SOURCE_NAME", "network-scan")
INTERVAL = int(os.environ.get("REPORT_INTERVAL", "300"))
UNREACHABLE_AFTER = int(os.environ.get("REPORT_UNREACHABLE_AFTER", "3600"))


def log(msg):
    print(f"[cmdb-reporter] {msg}", file=sys.stderr, flush=True)


def get_status():
    with urllib.request.urlopen(STATUS_URL, timeout=10) as resp:
        return json.load(resp)


def latest_finished_run(status):
    best = None
    for policy in status.get("policies") or []:
        for run in policy.get("runs") or []:
            if run.get("status") not in ("completed", "failed"):
                continue
            if best is None or run.get("updated_at", 0) > best[1].get("updated_at", 0):
                best = (policy.get("name", "?"), run)
    return best


def to_datetime(ts):
    """orb-agent timestamps may be in s, ms, us or ns."""
    ts = float(ts)
    for divisor in (1e9, 1e6, 1e3):
        if ts > 1e11 * (divisor / 1e3):
            ts /= divisor
            break
    return datetime.fromtimestamp(ts, tz=UTC)


def report(ok, message, details, when=None):
    body = {
        "source": SOURCE,
        "status": "ok" if ok else "failed",
        "message": message,
        "details": details,
    }
    if when:
        body["time"] = when
    req = urllib.request.Request(
        NETBOX_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def main():
    last_reported = None
    unreachable_since = None
    last_unreachable_report = 0.0
    time.sleep(30)
    while True:
        now = time.time()
        try:
            status = get_status()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            unreachable_since = unreachable_since or now
            log(f"network-discovery status unavailable: {exc}")
            if now - unreachable_since > UNREACHABLE_AFTER and now - last_unreachable_report > UNREACHABLE_AFTER:
                try:
                    report(False, f"network-discovery backend unreachable: {exc}", {})
                    last_unreachable_report = now
                except (urllib.error.URLError, OSError) as exc2:
                    log(f"could not report failure to NetBox: {exc2}")
            time.sleep(INTERVAL)
            continue

        unreachable_since = None
        found = latest_finished_run(status)
        if found:
            policy, run = found
            key = (run.get("id"), run.get("status"))
            if key != last_reported:
                ok = run.get("status") == "completed"
                when = to_datetime(run.get("updated_at") or now).isoformat()
                entities = run.get("entity_count", 0)
                msg = f"{policy}: {entities} entities" if ok else f"{policy}: {run.get('reason') or 'failed'}"
                try:
                    report(ok, msg, {"policy": policy, "run_id": run.get("id"), "entities": entities}, when)
                    last_reported = key
                    log(f"reported {run.get('status')} run {run.get('id')} of {policy}")
                except (urllib.error.URLError, OSError) as exc:
                    log(f"could not report to NetBox (will retry): {exc}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:  # noqa: BLE001 - never let the reporter die silently
            log(f"unexpected error, restarting reporter: {exc!r}")
            time.sleep(60)
