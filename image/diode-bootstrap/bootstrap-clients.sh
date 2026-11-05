#!/bin/sh
# Creates (or updates) Diode's OAuth2 clients in Hydra from the stack variables.
# Runs at every start: an existing client gets its secret and scope re-applied,
# so rotating a secret only needs the variable changed and the stack redeployed.
set -eu

HYDRA_ADMIN_URL="${HYDRA_ADMIN_URL:-http://hydra:4445}"

echo "Waiting for Hydra admin API at ${HYDRA_ADMIN_URL}..."
i=0
until wget -qO- "${HYDRA_ADMIN_URL}/health/ready" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then echo "ERROR: Hydra not ready after 120s" >&2; exit 1; fi
  sleep 2
done

ensure_client() {
  client_id="$1"; secret="$2"; scope="$3"
  if [ -z "$secret" ]; then
    echo "WARN: no secret for ${client_id}, client skipped"
    return 0
  fi
  if hydra get oauth2-client "$client_id" --endpoint "$HYDRA_ADMIN_URL" >/dev/null 2>&1; then
    hydra update oauth2-client "$client_id" --endpoint "$HYDRA_ADMIN_URL" \
      --name "$client_id" \
      --secret "$secret" \
      --grant-type client_credentials \
      --response-type token \
      --scope "$scope" \
      --token-endpoint-auth-method client_secret_post \
      --format json >/dev/null
    echo "INFO: client ${client_id} updated"
  else
    hydra create oauth2-client --endpoint "$HYDRA_ADMIN_URL" \
      --id "$client_id" \
      --name "$client_id" \
      --secret "$secret" \
      --grant-type client_credentials \
      --response-type token \
      --scope "$scope" \
      --token-endpoint-auth-method client_secret_post \
      --format json >/dev/null
    echo "INFO: client ${client_id} created"
  fi
}

# Internal clients (fixed ids, required by Diode and the NetBox plugin)
ensure_client "diode-to-netbox" "${DIODE_CLIENT_SECRET_DIODE_TO_NETBOX:-}" "netbox:read netbox:write"
ensure_client "netbox-to-diode" "${DIODE_CLIENT_SECRET_NETBOX_TO_DIODE:-}" "diode:read diode:write"
# One dedicated ingestion client per source
ensure_client "${DIODE_CLIENT_ID_ORB_AGENT:-orb-agent}" "${DIODE_CLIENT_SECRET_ORB_AGENT:-}" "diode:ingest"
ensure_client "${DIODE_CLIENT_ID_NGINX_AGENT:-nginx-agent}" "${DIODE_CLIENT_SECRET_NGINX_AGENT:-}" "diode:ingest"

echo "Diode OAuth2 clients ready."
