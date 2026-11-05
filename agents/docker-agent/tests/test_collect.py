from cmdb_docker_agent.collect import build_container, build_network, build_snapshot

SUMMARY = {
    "Id": "abc123",
    "Names": ["/wiki-app"],
    "Image": "wikijs:2",
    "State": "running",
    "Status": "Up 2 hours",
    "Ports": [
        {"IP": "0.0.0.0", "PrivatePort": 3000, "PublicPort": 3080, "Type": "tcp"},
        {"IP": "::", "PrivatePort": 3000, "PublicPort": 3080, "Type": "tcp"},
        {"PrivatePort": 9000, "Type": "tcp"},
    ],
    "Labels": {"com.docker.compose.project": "wiki"},
}
DETAIL = {
    "Id": "abc123",
    "Name": "/wiki-app",
    "Created": "2026-01-01T00:00:00Z",
    "Config": {
        "Image": "ghcr.io/requarks/wiki:2",
        "Labels": {"com.docker.compose.project": "wiki", "com.docker.compose.service": "app"},
    },
    "HostConfig": {"NetworkMode": "wiki_default", "RestartPolicy": {"Name": "unless-stopped"}},
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
    "NetworkSettings": {"Networks": {"wiki_default": {"IPAddress": "172.20.0.2", "Aliases": ["app", "abc123"]}}},
    "Mounts": [
        {
            "Type": "volume",
            "Name": "wiki_data",
            "Source": "/var/lib/docker/volumes/wiki_data/_data",
            "Destination": "/data",
            "RW": True,
        }
    ],
}


def test_container():
    c = build_container(SUMMARY, DETAIL)
    assert c["name"] == "wiki-app"
    assert c["stack"] == "wiki" and c["compose_service"] == "app"
    assert c["image"] == "ghcr.io/requarks/wiki:2"
    assert c["health"] == "healthy"
    assert len([p for p in c["ports"] if p["public_port"] == 3080]) == 2  # v4 + v6 bindings kept, deduped by IP
    assert {"private_port": 9000, "public_port": None, "ip": "", "type": "tcp"} in c["ports"]
    assert c["networks"] == [{"network": "wiki_default", "ip": "172.20.0.2", "aliases": ["app"]}]
    assert c["mounts"][0]["source"] == "wiki_data"


def test_host_network_container():
    detail = {
        **DETAIL,
        "HostConfig": {"NetworkMode": "host"},
        "Config": {"Image": "x", "ExposedPorts": {"8123/tcp": {}}},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    c = build_container({**SUMMARY, "Ports": []}, detail)
    assert c["network_mode"] == "host"
    assert c["ports"] == [{"private_port": 8123, "public_port": 8123, "ip": "", "type": "tcp"}]


def test_network():
    n = build_network(
        {
            "Id": "n1",
            "Name": "wiki_default",
            "Driver": "bridge",
            "Scope": "local",
            "Internal": True,
            "IPAM": {"Config": [{"Subnet": "172.20.0.0/16", "Gateway": "172.20.0.1"}]},
            "Labels": {"com.docker.compose.project": "wiki"},
        }
    )
    assert n == {
        "id": "n1",
        "name": "wiki_default",
        "driver": "bridge",
        "scope": "local",
        "internal": True,
        "subnets": ["172.20.0.0/16"],
        "gateways": ["172.20.0.1"],
        "stack": "wiki",
    }


class FakeDocker:
    def info(self):
        return {"Name": "lxc13", "OperatingSystem": "Debian GNU/Linux 12"}

    def version(self):
        return {"Version": "27.3.1"}

    def containers(self):
        return [SUMMARY]

    def inspect_container(self, cid):
        return DETAIL

    def networks(self):
        return [{"Id": "n1", "Name": "bridge", "Driver": "bridge", "IPAM": {"Config": []}}]


def test_snapshot():
    snap = build_snapshot(FakeDocker(), "cmdb-lxc", ["192.168.1.13"])
    assert snap["host"]["name"] == "cmdb-lxc"
    assert snap["host"]["engine_version"] == "27.3.1"
    assert len(snap["containers"]) == 1 and len(snap["networks"]) == 1
