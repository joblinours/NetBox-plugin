"""A small, dependency-free parser for Nginx configuration (``nginx -T`` output).

It only extracts what the CMDB needs: virtual hosts (server_name, listen ports)
and where they proxy to (proxy_pass, resolved through ``upstream`` blocks).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Directive:
    name: str
    args: list[str]
    block: list[Directive] | None = None

    def children(self, name):
        return [d for d in (self.block or []) if d.name == name]


@dataclass
class VirtualHost:
    name: str
    ports: set[int] = field(default_factory=set)
    tls: bool = False
    upstream: str = ""
    locations: dict[str, str] = field(default_factory=dict)
    kind: str = "http"  # http | stream


def tokenize(text):
    """Yield tokens: words, quoted strings, '{', '}', ';'. Comments are dropped."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{};":
            yield c
            i += 1
        elif c in "\"'":
            quote, j, buf = c, i + 1, []
            while j < n and text[j] != quote:
                if text[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(text[j])
                j += 1
            yield "".join(buf)
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{};":
                if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
                    j = text.find("}", j) + 1 or n
                    continue
                j += 1
            yield text[i:j]
            i = j


def parse(text):
    """Parse configuration text into a list of Directives. Unbalanced braces are tolerated."""
    tokens = list(tokenize(text))
    pos = 0

    def parse_block():
        nonlocal pos
        out, current = [], []
        while pos < len(tokens):
            tok = tokens[pos]
            pos += 1
            if tok == ";":
                if current:
                    out.append(Directive(current[0], current[1:]))
                current = []
            elif tok == "{":
                name, args = (current[0], current[1:]) if current else ("", [])
                out.append(Directive(name, args, parse_block()))
                current = []
            elif tok == "}":
                return out
            else:
                current.append(tok)
        return out

    return parse_block()


def split_files(dump):
    """Split ``nginx -T`` output into {path: content} using its '# configuration file' markers."""
    marker = re.compile(r"^# configuration file (.+?):\s*$", re.M)
    matches = list(marker.finditer(dump))
    if not matches:
        return {"<stdin>": dump}
    files = {}
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(dump)
        files[m.group(1)] = dump[m.end() : end]
    return files


def _walk(directives, context=()):
    for d in directives:
        yield d, context
        if d.block is not None:
            yield from _walk(d.block, context + (d.name,))


def _listen_port(args):
    if not args:
        return None, False
    addr = args[0]
    tls = "ssl" in args[1:] or "quic" in args[1:]
    if addr.startswith("unix:"):
        return None, tls
    m = re.search(r"(?:^|:)(\d{1,5})$", addr)
    if m:
        return int(m.group(1)), tls
    if addr.isdigit():
        return int(addr), tls
    return 80, tls  # "listen 127.0.0.1;" -> default port


def _normalize_target(target, upstreams, scheme_hint="http"):
    """Turn a proxy_pass value into ``scheme://host:port`` when possible."""
    target = target.strip()
    if not target:
        return ""
    m = re.match(r"^(?P<scheme>[a-z]+)://(?P<rest>.+)$", target)
    scheme, rest = (m.group("scheme"), m.group("rest")) if m else (scheme_hint, target)
    hostport = rest.split("/", 1)[0]
    if hostport in upstreams and upstreams[hostport]:
        hostport = upstreams[hostport][0]
    if hostport.startswith("unix:") or "$" in hostport:
        return f"{scheme}://{hostport}" if m else target
    return f"{scheme}://{hostport}"


def extract_vhosts(directives):
    """Return a list of VirtualHost, merged by server_name, from parsed directives."""
    upstreams = {}
    for d, _ in _walk(directives):
        if d.name == "upstream" and d.block is not None and d.args:
            upstreams[d.args[0]] = [
                s.args[0] for s in d.children("server") if s.args and not s.args[0].startswith("unix:")
            ]

    vhosts = {}
    for d, ctx in _walk(directives):
        if d.name != "server" or d.block is None or "upstream" in ctx:
            continue
        kind = "stream" if "stream" in ctx else "http"
        names = [a.lower() for s in d.children("server_name") for a in s.args]
        names = [n for n in names if n and n not in ("_", "localhost", '""') and not n.startswith("~")]
        ports, tls = set(), False
        for listen in d.children("listen"):
            port, is_tls = _listen_port(listen.args)
            if port:
                ports.add(port)
            tls = tls or is_tls
        if not d.children("listen") and kind == "http":
            ports.add(80)  # nginx default when no listen directive

        locations = {}
        for p in d.children("proxy_pass") + d.children("grpc_pass"):  # stream servers / server-level
            if p.args:
                locations["/"] = _normalize_target(
                    p.args[0], upstreams, "grpc" if p.name == "grpc_pass" else "tcp" if kind == "stream" else "http"
                )
        for loc, _ in _walk(d.block):
            if loc.name != "location" or loc.block is None:
                continue
            if not loc.args:
                continue
            modifier = loc.args[0] if len(loc.args) > 1 else ""
            # "= /x" and "^~ /x" are plain paths; "~ regex" / "~* regex" are kept marked as regex
            path = f"~ {loc.args[-1]}" if modifier in ("~", "~*") else loc.args[-1]
            for p in loc.children("proxy_pass") + loc.children("grpc_pass"):
                if p.args:
                    locations[path] = _normalize_target(
                        p.args[0], upstreams, "grpc" if p.name == "grpc_pass" else "http"
                    )
        if kind == "stream" and not names:
            names = [f"stream-{min(ports)}"] if ports else []

        for name in names:
            vh = vhosts.setdefault(name, VirtualHost(name=name, kind=kind))
            vh.ports |= ports
            vh.tls = vh.tls or tls
            for path, target in locations.items():
                vh.locations.setdefault(path, target)

    for vh in vhosts.values():
        if vh.locations:
            vh.upstream = vh.locations.get("/") or vh.locations[sorted(vh.locations)[0]]
    return sorted(vhosts.values(), key=lambda v: v.name)


def vhosts_from_dump(dump):
    """Parse the full ``nginx -T`` output (all files) and return virtual hosts."""
    directives = []
    for content in split_files(dump).values():
        directives.extend(parse(content))
    return extract_vhosts(directives)
