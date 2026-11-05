"""cmdb-nginx-agent: push the reverse proxy's virtual hosts to NetBox (via Diode)."""

import argparse
import sys

from . import __version__
from .agent import Settings, report, run


def load_env_file(path):
    import os

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cmdb-nginx-agent", description=__doc__)
    parser.add_argument("--env-file", help="read settings from this KEY=VALUE file (systemd uses EnvironmentFile)")
    parser.add_argument("--dry-run", action="store_true", help="parse and print, send nothing")
    parser.add_argument("--config-dump", help="read a saved `nginx -T` output instead of running nginx")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    if args.env_file:
        load_env_file(args.env_file)
    settings = Settings.from_env()
    if args.config_dump:
        settings.config_dump = args.config_dump

    try:
        vhosts = run(settings, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - every failure must reach Zabbix
        print(f"ERROR: {exc}", file=sys.stderr)
        if not args.dry_run:
            try:
                report(settings, False, str(exc))
            except Exception as rep_exc:  # noqa: BLE001
                print(f"WARN: could not report failure to NetBox: {rep_exc}", file=sys.stderr)
        return 1
    if not args.dry_run:
        try:
            report(settings, True, f"{len(vhosts)} virtual hosts", {"vhosts": len(vhosts)})
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not report success to NetBox: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
