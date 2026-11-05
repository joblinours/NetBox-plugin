#!/bin/bash
# Runs after docker-entrypoint.sh (migrations + first-start admin creation),
# provisions the CMDB from the stack variables, then starts NetBox as usual.
set -e
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py cmdb_bootstrap || echo "⚠️ cmdb_bootstrap failed, NetBox starts anyway"

LAUNCH=/opt/netbox/launch-netbox.sh
# launch-netbox.sh listens on "::"; fall back to IPv4 on hosts/LXC without IPv6.
if [ ! -e /proc/net/if_inet6 ]; then
  echo "ℹ️ IPv6 not available, NetBox listens on 0.0.0.0"
  sed 's/--host "::"/--host "0.0.0.0"/' /opt/netbox/launch-netbox.sh > /tmp/launch-netbox.sh
  chmod +x /tmp/launch-netbox.sh
  LAUNCH=/tmp/launch-netbox.sh
fi
exec "$LAUNCH" "$@"
