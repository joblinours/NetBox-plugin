"""Read-only AdGuard Home API client."""

import requests


class AdGuardError(Exception):
    pass


class AdGuardClient:
    def __init__(self, base_url, username="", password="", verify_ssl=True, timeout=20, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify = verify_ssl
        self.session = session or requests.Session()
        if username:
            self.session.auth = (username, password)

    def rewrites(self):
        """[{'domain': 'nas.lan', 'answer': '192.168.1.5', 'enabled': True}, ...]"""
        url = f"{self.base_url}/control/rewrite/list"
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=self.verify)
        except requests.RequestException as exc:
            raise AdGuardError(f"{self.base_url}: {exc}") from exc
        if resp.status_code in (401, 403):
            raise AdGuardError(f"{self.base_url}: authentication refused (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise AdGuardError(f"{self.base_url}: HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise AdGuardError(f"{self.base_url}: non-JSON answer (wrong URL?)")
        if not isinstance(data, list):
            raise AdGuardError(f"{self.base_url}: unexpected answer {str(data)[:100]}")
        return [
            {
                "domain": str(r.get("domain", "")).strip().lower().rstrip("."),
                "answer": str(r.get("answer", "")).strip().rstrip("."),
                "enabled": bool(r.get("enabled", True)),
            }
            for r in data
            if r.get("domain") and r.get("answer")
        ]
