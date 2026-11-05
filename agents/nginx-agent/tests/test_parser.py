from pathlib import Path

from cmdb_nginx_agent.agent import Settings, build_entities
from cmdb_nginx_agent.parser import parse, split_files, tokenize, vhosts_from_dump

SAMPLE = (Path(__file__).parent / "sample_nginx_T.txt").read_text()


def test_tokenize_quotes_and_comments():
    assert list(tokenize('a "b c" d; # comment\n e {f;}')) == ["a", "b c", "d", ";", "e", "{", "f", ";", "}"]


def test_parse_unbalanced_is_tolerated():
    assert parse("server { listen 80;")[0].name == "server"


def test_split_files():
    files = split_files(SAMPLE)
    assert "/etc/nginx/sites-enabled/cloud.conf" in files
    assert "/etc/nginx/nginx.conf" in files


def test_vhosts():
    vhosts = {v.name: v for v in vhosts_from_dump(SAMPLE)}
    assert set(vhosts) == {
        "cloud.example.com",
        "git.example.com",
        "wiki.example.com",
        "local.example.com",
        "stream-2222",
        "proxy.example.com",
    }

    cloud = vhosts["cloud.example.com"]
    assert cloud.ports == {80, 443}
    assert cloud.tls
    assert cloud.upstream == "http://192.168.1.21:11000"  # first server of the upstream block
    assert cloud.locations["/push/"] == "http://192.168.1.21:7867"

    git = vhosts["git.example.com"]
    assert git.ports == {8080}
    assert git.upstream == "http://192.168.1.25:3000"
    assert vhosts["wiki.example.com"].upstream == git.upstream

    assert vhosts["local.example.com"].ports == set()
    assert vhosts["stream-2222"].kind == "stream"
    assert vhosts["stream-2222"].upstream == "tcp://192.168.1.30:22"


def test_entities():
    settings = Settings(
        diode_target="grpc://x:8081/diode",
        client_id="nginx-agent",
        client_secret="s",
        parent_name="revers-proxy",
        cluster="pve",
    )
    entities = build_entities(vhosts_from_dump(SAMPLE), settings)
    services = {e.service.name: e.service for e in entities}
    # local.example.com listens on a unix socket only: no TCP service
    assert "local.example.com" not in services
    cloud = services["cloud.example.com"]
    assert list(cloud.port_mappings) == ["tcp/80", "tcp/443"]
    assert cloud.parent_object_virtual_machine.name == "revers-proxy"
    assert cloud.parent_object_virtual_machine.cluster.name == "pve"
    assert cloud.custom_fields["upstream_target"].text == "http://192.168.1.21:11000"
    assert [t.name for t in cloud.tags] == ["nginx-agent"]
    assert "/push/ -> http://192.168.1.21:7867" in cloud.comments


def test_path_routing_vhost():
    vhosts = {v.name: v for v in vhosts_from_dump(SAMPLE)}
    proxy = vhosts["proxy.example.com"]
    assert "/" not in proxy.locations  # "location = /" only redirects
    assert proxy.locations["/bastion/"] == "http://192.168.1.5:8080"
    assert proxy.locations["/slides/"] == "http://192.168.1.13:8084"
    assert vhosts["git.example.com"].locations["~ ^/api/(.*)$"] == "https://192.168.1.25:3000"

    settings = Settings(
        diode_target="grpc://x/diode", client_id="c", client_secret="s", parent_name="revers-proxy", cluster="homelab"
    )
    services = {e.service.name: e.service for e in build_entities(vhosts_from_dump(SAMPLE), settings)}
    assert services["proxy.example.com"].custom_fields["upstream_target"].text == ""
    assert services["proxy.example.com/bastion"].custom_fields["upstream_target"].text == "http://192.168.1.5:8080"
    assert services["proxy.example.com/iptv-dev"].custom_fields["upstream_target"].text == "http://192.168.1.13:8081"
    assert list(services["proxy.example.com/slides"].port_mappings) == ["tcp/80"]
    assert services["cloud.example.com/push"].custom_fields["upstream_target"].text == "http://192.168.1.21:7867"
    # regex locations are not split into services
    assert not any(name.startswith("git.example.com/") for name in services)
