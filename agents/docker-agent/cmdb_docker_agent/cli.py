"""cmdb-docker-agent: push this Docker host's containers, stacks and networks to NetBox.

Environment:
  NETBOX_URL            http://192.168.1.13:10000
  NETBOX_TOKEN          token of svc-docker-agent (CMDB_TOKEN_DOCKER_AGENT)
  DOCKER_AGENT_HOST_NAME  name of this host in NetBox (VM / device), default: Docker engine hostname
  DOCKER_AGENT_ADDRESSES  optional, comma separated IPs of this host (helps matching the NetBox VM)
  DOCKER_HOST           default unix:///var/run/docker.sock
  DOCKER_AGENT_INTERVAL seconds between runs (default 3600); 0 = run once and exit
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from .collect import build_snapshot
from .docker_api import DockerClient


def log(msg):
    print(f"[cmdb-docker-agent] {msg}", file=sys.stderr, flush=True)


def post(url, token, path, body, timeout=60):
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run_once(args):
    client = DockerClient(args.docker_host)
    addresses = [a.strip() for a in args.addresses.split(",") if a.strip()]
    try:
        snapshot = build_snapshot(client, args.host_name, addresses)
    except Exception as exc:  # noqa: BLE001 - the failure must reach Zabbix
        log(f"cannot read Docker: {exc}")
        if not args.dry_run and args.netbox_url and args.token:
            name = (args.host_name or "unknown").lower().replace(".", "-")
            try:
                post(
                    args.netbox_url,
                    args.token,
                    "/api/plugins/cmdb/sources/",
                    {"source": f"docker-{name}", "status": "failed", "message": f"cannot read Docker: {exc}"},
                )
            except (urllib.error.URLError, OSError) as rep:
                log(f"could not report failure: {rep}")
        return 1
    if args.dry_run:
        print(json.dumps(snapshot, indent=2))
        return 0
    try:
        result = post(args.netbox_url, args.token, "/api/plugins/docker-inventory/snapshot/", snapshot)
    except urllib.error.HTTPError as exc:
        log(f"NetBox refused the snapshot: HTTP {exc.code} {exc.read()[:300]!r}")
        return 1
    except (urllib.error.URLError, OSError) as exc:
        log(f"NetBox unreachable: {exc}")
        return 1
    log(f"snapshot sent: {result}")
    return 0


def main(argv=None):
    env = os.environ
    parser = argparse.ArgumentParser(
        prog="cmdb-docker-agent", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--netbox-url", default=env.get("NETBOX_URL", ""))
    parser.add_argument("--token", default=env.get("NETBOX_TOKEN", ""))
    parser.add_argument("--host-name", default=env.get("DOCKER_AGENT_HOST_NAME", ""))
    parser.add_argument("--addresses", default=env.get("DOCKER_AGENT_ADDRESSES", ""))
    parser.add_argument("--docker-host", default=env.get("DOCKER_HOST", "unix:///var/run/docker.sock"))
    parser.add_argument("--interval", type=int, default=int(env.get("DOCKER_AGENT_INTERVAL", "3600")))
    parser.add_argument("--dry-run", action="store_true", help="print the snapshot, send nothing")
    args = parser.parse_args(argv)

    if not args.dry_run and (not args.netbox_url or not args.token):
        parser.error("NETBOX_URL and NETBOX_TOKEN are required (or use --dry-run)")
    if args.dry_run or args.interval <= 0:
        return run_once(args)
    while True:
        run_once(args)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
