#!/usr/bin/env bash
# Generates /opt/orb/agent.yaml from the stack variables (no file on the host),
# starts the status reporter in the background, then hands over to orb-agent.
set -euo pipefail

: "${DIODE_TARGET:=grpc://127.0.0.1:8081/diode}"
: "${DIODE_CLIENT_ID:=orb-agent}"
: "${DIODE_CLIENT_SECRET:?DIODE_CLIENT_SECRET (orb-agent Diode client secret) is required}"
: "${ORB_AGENT_NAME:=cmdb-orb-agent}"
: "${SCAN_TARGETS:=192.168.1.0/24}"
: "${SCAN_SCHEDULE:=0 3 * * *}"
: "${SCAN_TIMEOUT_MINUTES:=120}"
: "${SCAN_TOP_PORTS:=1000}"
: "${SCAN_STARTUP:=true}"
: "${SCAN_TAG:=orb-network-scan}"
: "${ORB_DISCOVERY_PORT:=8073}"

yaml_list() {  # "a, b" -> ["a", "b"]
  local IFS=','; local out=() item
  for item in $1; do item="$(echo "$item" | xargs)"; [ -n "$item" ] && out+=("\"$item\""); done
  local joined; joined=$(IFS=,; echo "${out[*]}"); echo "[${joined}]"
}

TARGETS="$(yaml_list "$SCAN_TARGETS")"

scope_block() {
  cat <<YAML
        scope:
          targets: ${TARGETS}
          top_ports: ${SCAN_TOP_PORTS}
YAML
  if [ -n "${SCAN_EXCLUDE_PORTS:-}" ]; then echo "          exclude_ports: $(yaml_list "$SCAN_EXCLUDE_PORTS")"; fi
}

policy_config() {
  cat <<YAML
          timeout: ${SCAN_TIMEOUT_MINUTES}
          defaults:
            description: "Discovered by orb-agent network scan"
            tags: ["${SCAN_TAG}"]
YAML
}

umask 077
{
  cat <<YAML
orb:
  config_manager:
    active: local
  backends:
    network_discovery:
      host: 127.0.0.1
      port: ${ORB_DISCOVERY_PORT}
    common:
      diode:
        target: ${DIODE_TARGET}
        client_id: "${DIODE_CLIENT_ID}"
        client_secret: "${DIODE_CLIENT_SECRET}"
        agent_name: ${ORB_AGENT_NAME}
  policies:
    network_discovery:
      daily_scan:
        config:
          schedule: "${SCAN_SCHEDULE}"
YAML
  policy_config
  scope_block
  if [ "${SCAN_STARTUP}" = "true" ]; then
    cat <<YAML
      startup_scan:
        config:
YAML
    policy_config
    scope_block
  fi
} > /opt/orb/agent.yaml

echo "orb-agent config generated: targets=${TARGETS} schedule='${SCAN_SCHEDULE}' startup=${SCAN_STARTUP}"

if [ -n "${NETBOX_URL:-}" ] && [ -n "${NETBOX_TOKEN:-}" ]; then
  python3 /usr/local/bin/cmdb-reporter.py &
else
  echo "NETBOX_URL / NETBOX_TOKEN not set: scan status is not reported to NetBox (Zabbix)"
fi

exec /usr/local/bin/orb-agent-entry.sh run -c /opt/orb/agent.yaml
