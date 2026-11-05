"""Minimal, read-only Cloudflare API client (Cloudflare Tunnel endpoints only)."""

import requests


class CloudflareError(Exception):
    pass


class CloudflareClient:
    def __init__(
        self, api_token, account_id, base_url="https://api.cloudflare.com/client/v4", timeout=30, session=None
    ):
        if not api_token or not account_id:
            raise CloudflareError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set")
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_token}", "Accept": "application/json"})

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise CloudflareError(f"GET {path}: {exc}") from exc
        try:
            payload = resp.json()
        except ValueError:
            raise CloudflareError(f"GET {path}: HTTP {resp.status_code}, non-JSON response")
        if resp.status_code >= 400 or not payload.get("success", False):
            errors = "; ".join(e.get("message", str(e)) for e in payload.get("errors", [])) or resp.reason
            raise CloudflareError(f"GET {path}: HTTP {resp.status_code}: {errors}")
        return payload

    def list_tunnels(self):
        """All non-deleted cloudflared tunnels of the account (handles pagination)."""
        tunnels, page = [], 1
        while True:
            payload = self._get(
                f"/accounts/{self.account_id}/cfd_tunnel",
                params={"is_deleted": "false", "per_page": 100, "page": page},
            )
            tunnels.extend(payload.get("result") or [])
            info = payload.get("result_info") or {}
            total_pages = info.get("total_pages") or 1
            if page >= total_pages or not payload.get("result"):
                return tunnels
            page += 1

    def get_tunnel_configuration(self, tunnel_id):
        """Remote (dashboard-managed) configuration of a tunnel: {'ingress': [...], ...}."""
        payload = self._get(f"/accounts/{self.account_id}/cfd_tunnel/{tunnel_id}/configurations")
        result = payload.get("result") or {}
        return result.get("config") or {}
