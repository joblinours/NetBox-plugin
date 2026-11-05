"""Tiny read-only Docker Engine API client (unix socket or tcp://), standard library only."""

import http.client
import json
import socket
from urllib.parse import quote, urlsplit


class DockerError(Exception):
    pass


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=30):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


class DockerClient:
    def __init__(self, docker_host="unix:///var/run/docker.sock", timeout=30):
        self.docker_host = docker_host
        self.timeout = timeout

    def _conn(self):
        parts = urlsplit(self.docker_host)
        if parts.scheme == "unix":
            return _UnixHTTPConnection(parts.path, self.timeout)
        if parts.scheme in ("tcp", "http"):
            return http.client.HTTPConnection(parts.hostname, parts.port or 2375, timeout=self.timeout)
        raise DockerError(f"unsupported DOCKER_HOST {self.docker_host!r}")

    def get(self, path):
        conn = self._conn()
        try:
            conn.request("GET", path, headers={"Host": "docker", "Accept": "application/json"})
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:
            raise DockerError(f"GET {path}: {exc}") from exc
        finally:
            conn.close()
        if resp.status >= 400:
            raise DockerError(f"GET {path}: HTTP {resp.status} {body[:200]!r}")
        return json.loads(body or b"null")

    def info(self):
        return self.get("/info")

    def version(self):
        return self.get("/version")

    def containers(self):
        return self.get("/containers/json?all=1")

    def inspect_container(self, cid):
        return self.get(f"/containers/{quote(cid)}/json")

    def networks(self):
        return self.get("/networks")
