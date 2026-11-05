"""Renderers: Markdown, PDF (fpdf2), Mermaid, Graphviz DOT -> PNG / SVG."""

import os
import re
import shutil
import subprocess

from netbox.plugins import get_plugin_config

PLUGIN = "netbox_cmdb_export"


# --------------------------------------------------------------------------- Markdown


def _cell(value):
    if value is None or value == "" or value == []:
        return "—"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


def _targets(u):
    """Human-readable destination(s) of a public URL, one per Nginx path."""
    if u.get("routes"):
        return "; ".join(f"{r['path']} -> {r['service']} on {r['host']}" for r in u["routes"])
    if u.get("service"):
        return f"{u['service']} on {u['host']}" if u.get("host") else u["service"]
    return u.get("upstream") or u.get("origin")


def to_markdown(data):
    md = [f"# {data['title']}", "", f"Generated {data['generated']} from NetBox.", ""]
    counts = data["overview"]["counts"]
    md += ["## Overview", ""]
    md += _table(["Item", "Count"], [[k.replace("_", " "), v] for k, v in counts.items()])
    md += ["", "Sources: " + ", ".join(f"{k} = {v}" for k, v in data["overview"]["sources"].items()), ""]

    if data["clusters"]:
        md += ["## Clusters", ""]
        for c in data["clusters"]:
            md += [f"### {c['name']} ({c['type']})", "", f"Nodes: {', '.join(c['nodes']) or '—'}", ""]
            md += _table(["VM / LXC", "Node"], [[v["name"], v["node"]] for v in c["vms"]]) + [""]

    md += ["## Hosts", ""]
    md += _table(
        ["Host", "Type", "Status", "Cluster", "Primary IP", "Ports in use"],
        [
            [
                h["name"],
                h["type"],
                h["status"],
                h["cluster"],
                h["primary_ip"],
                ", ".join(f"{p['port']}/{p['protocol']}" for p in h["ports_in_use"]),
            ]
            for h in data["hosts"]
        ],
    )
    md.append("")
    for h in data["hosts"]:
        md += [f"### {h['name']}", ""]
        meta = [f"- Type: {h['type']}, status: {h['status']}"]
        if h.get("cluster"):
            meta.append(f"- Cluster: {h['cluster']}" + (f", node {h['node']}" if h.get("node") else ""))
        for k, v in (h.get("custom_fields") or {}).items():
            meta.append(f"- {k.replace('_', ' ')}: {_cell(v)}")
        md += meta + [""]
        if h["ip_addresses"]:
            md += _table(
                ["IP", "DNS name", "Local domains"],
                [[i["address"], i["dns_name"], i["local_domains"]] for i in h["ip_addresses"]],
            ) + [""]
        if h["ports_in_use"]:
            md += _table(
                ["Port", "Used by"],
                [
                    [f"{p['port']}/{p['protocol']}", "; ".join(f"{u['source']}: {u['detail']}" for u in p["used_by"])]
                    for p in h["ports_in_use"]
                ],
            ) + [""]
        if h.get("containers"):
            md += _table(
                ["Container", "Stack", "Image", "State", "Published", "Networks"],
                [
                    [
                        c["name"],
                        c["stack"],
                        c["image"],
                        c["state"],
                        c["published_ports"],
                        [f"{n['network']} {n['ip'] or ''}".strip() for n in c["networks"]],
                    ]
                    for c in h["containers"]
                ],
            ) + [""]

    if data["public_urls"]:
        md += ["## Public URLs", ""]
        md += _table(
            ["URL", "Exposure", "Nginx", "Target (path -> service on host)"],
            [[u["url"], u["exposure_path"], u.get("nginx_host"), _targets(u)] for u in data["public_urls"]],
        ) + [""]
    if data["dns_names"]:
        md += ["## DNS names", ""]
        md += _table(
            ["Name", "Type", "Answer", "Host"],
            [[d["name"], d["type"], d["answer"], d["host"]] for d in data["dns_names"]],
        ) + [""]
    if data["docker_hosts"]:
        md += ["## Docker", ""]
        for d in data["docker_hosts"]:
            md += [
                f"### {d['name']}" + (f" (on {d['netbox_host']})" if d["netbox_host"] else ""),
                "",
                f"Docker {d['engine_version'] or '?'}, last seen {d['last_seen'] or 'never'}.",
                "",
            ]
            md += _table(
                ["Network", "Driver", "Internal", "Subnets", "Stack", "Containers"],
                [
                    [
                        n["name"],
                        n["driver"],
                        "yes" if n["internal"] else "no",
                        n["subnets"],
                        n["stack"],
                        n["containers"],
                    ]
                    for n in d["networks"]
                ],
            ) + [""]
    return "\n".join(md).rstrip() + "\n"


# --------------------------------------------------------------------------- PDF


def to_pdf(data):
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(orientation="landscape", format="A4")
    pdf.set_auto_page_break(True, margin=12)
    regular = get_plugin_config(PLUGIN, "pdf_font")
    bold = get_plugin_config(PLUGIN, "pdf_font_bold")
    if regular and os.path.exists(regular):
        pdf.add_font("Body", "", regular)
        pdf.add_font("Body", "B", bold if bold and os.path.exists(bold) else regular)
        font = "Body"
    else:  # core font: Latin-1 only
        font = "Helvetica"

    def text(value):
        value = _cell(value).replace("\\|", "|")
        return value if font == "Body" else value.encode("latin-1", "replace").decode("latin-1")

    def heading(value, size):
        pdf.set_font(font, "B", size)
        pdf.multi_cell(0, size * 0.55, text(value), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def table(headers, rows):
        if not rows:
            return
        pdf.set_font(font, "", 7.5)
        with pdf.table(
            headings_style=FontFace(emphasis="BOLD", fill_color=(225, 230, 240)), line_height=4, text_align="LEFT"
        ) as t:
            row = t.row()
            for h in headers:
                row.cell(text(h))
            for r in rows:
                row = t.row()
                for c in r:
                    row.cell(text(c))
        pdf.ln(3)

    pdf.add_page()
    heading(data["title"], 18)
    pdf.set_font(font, "", 9)
    pdf.cell(0, 5, text(f"Generated {data['generated']} from NetBox"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    heading("Overview", 13)
    table(["Item", "Count"], [[k.replace("_", " "), v] for k, v in data["overview"]["counts"].items()])
    heading("Hosts", 13)
    table(
        ["Host", "Type", "Status", "Cluster", "Primary IP", "Ports in use", "Local domains"],
        [
            [
                h["name"],
                h["type"],
                h["status"],
                h["cluster"],
                h["primary_ip"],
                ", ".join(f"{p['port']}/{p['protocol']}" for p in h["ports_in_use"]),
                ", ".join(filter(None, (i["local_domains"] for i in h["ip_addresses"]))),
            ]
            for h in data["hosts"]
        ],
    )
    services = [
        [s["name"], s["host"], s["ports"], s["public_url"], s["exposure_path"], s["portainer_stack"]]
        for h in data["hosts"]
        for s in h["services"]
    ]
    if services:
        heading("Services", 13)
        table(["Service", "Host", "Ports", "Public URL", "Exposure", "Stack"], services)
    if data["public_urls"]:
        heading("Public URLs", 13)
        table(
            ["URL", "Exposure", "Nginx", "Target (path -> service on host)"],
            [[u["url"], u["exposure_path"], u.get("nginx_host"), _targets(u)] for u in data["public_urls"]],
        )
    if data["dns_names"]:
        heading("DNS names", 13)
        table(
            ["Name", "Type", "Answer", "Host"],
            [[d["name"], d["type"], d["answer"], d["host"]] for d in data["dns_names"]],
        )
    for d in data["docker_hosts"]:
        heading(f"Docker: {d['name']}", 13)
        table(
            ["Container", "Stack", "Image", "State", "Published", "Networks"],
            [
                [
                    c["name"],
                    c["stack"],
                    c["image"],
                    c["state"],
                    c["published_ports"],
                    [n["network"] for n in c["networks"]],
                ]
                for c in d["containers"]
            ],
        )
        table(
            ["Network", "Driver", "Internal", "Subnets", "Containers"],
            [
                [n["name"], n["driver"], "yes" if n["internal"] else "no", n["subnets"], n["containers"]]
                for n in d["networks"]
            ],
        )
    return bytes(pdf.output())


# --------------------------------------------------------------------------- graph


def _id(*parts):
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", "_".join(str(p) for p in parts))


def build_graph(data, containers=False):
    """Returns {"groups": {group: [node ids]}, "nodes": {id: (label, kind)}, "edges": [(a, b, label)]}."""
    nodes, edges, groups = {}, [], {}

    def node(nid, label, kind, group=None):
        nodes.setdefault(nid, (label, kind))
        if group:
            groups.setdefault(group, [])
            if nid not in groups[group]:
                groups[group].append(nid)
        return nid

    host_ids = {}
    for c in data["clusters"]:
        group = f"Cluster {c['name']}"
        cid = node(_id("cluster", c["name"]), c["name"], "cluster", group)
        for n in c["nodes"]:
            nid = host_ids[n] = node(_id("host", n), n, "node", group)
            edges.append((cid, nid, ""))
        for vm in c["vms"]:
            vid = host_ids[vm["name"]] = node(_id("host", vm["name"]), vm["name"], "vm", group)
            parent = host_ids.get(vm["node"]) if vm["node"] else cid
            edges.append((parent or cid, vid, ""))
    for h in data["hosts"]:
        if h["name"] not in host_ids:
            host_ids[h["name"]] = node(_id("host", h["name"]), h["name"], "device" if h["type"] == "device" else "vm")
        label, kind = nodes[host_ids[h["name"]]]
        if h.get("primary_ip") and "\n" not in label:
            nodes[host_ids[h["name"]]] = (f"{label}\n{h['primary_ip']}", kind)

    for u in data["public_urls"]:
        uid = node(_id("url", u["url"]), u["url"].split("://", 1)[-1], "url", "Public URLs")
        proxy_host = u.get("nginx_host")
        if u["exposure_path"] == "nginx" and proxy_host in host_ids:
            edges.append((uid, host_ids[proxy_host], "via Nginx"))
            routes = u.get("routes") or (
                [{"path": "/", "host": u["host"]}] if u["host"] and u["host"] != proxy_host else []
            )
            for r in routes:
                if r["host"] in host_ids:
                    edges.append((host_ids[proxy_host], host_ids[r["host"]], r["path"]))
            continue
        if u["host"] in host_ids:
            edges.append((uid, host_ids[u["host"]], "cloudflared"))

    for d in data["docker_hosts"]:
        parent = host_ids.get(d["netbox_host"]) or node(_id("host", d["name"]), d["name"], "vm")
        stacks = {}
        for c in d["containers"]:
            stacks.setdefault(c["stack"] or "(no stack)", []).append(c)
        for stack, items in sorted(stacks.items()):
            if containers:
                for c in items:
                    cid = node(_id("ctr", d["name"], c["name"]), c["name"], "container", f"Docker {d['name']}")
                    edges.append((parent, cid, ", ".join(p.split(":")[-1] for p in c["published_ports"])))
            else:
                running = sum(1 for c in items if c["state"] == "running")
                sid = node(
                    _id("stack", d["name"], stack),
                    f"{stack}\n{running}/{len(items)} running",
                    "stack",
                    f"Docker {d['name']}",
                )
                ports = sorted({p.split(":")[-1].split("->")[0] for c in items for p in c["published_ports"]})
                edges.append((parent, sid, ", ".join(ports)))
    return {"nodes": nodes, "edges": edges, "groups": groups}


MERMAID_STYLE = {
    "cluster": "fill:#e8eefc,stroke:#3b5bdb",
    "node": "fill:#dbe4ff,stroke:#3b5bdb",
    "vm": "fill:#f1f3f5,stroke:#495057",
    "device": "fill:#fff3bf,stroke:#f08c00",
    "url": "fill:#d3f9d8,stroke:#2b8a3e",
    "stack": "fill:#e3fafc,stroke:#0c8599",
    "container": "fill:#e3fafc,stroke:#0c8599",
}


def to_mermaid(graph):
    def label(text):
        return text.replace('"', "'").replace("\n", "<br/>")

    out = ["flowchart LR"]
    grouped = {nid for ids in graph["groups"].values() for nid in ids}
    for i, (group, ids) in enumerate(sorted(graph["groups"].items())):
        out.append(f'  subgraph g{i}["{label(group)}"]')
        for nid in ids:
            text, kind = graph["nodes"][nid]
            shape = ('(["', '"])') if kind == "url" else ('["', '"]')
            out.append(f"    {nid}{shape[0]}{label(text)}{shape[1]}:::{kind}")
        out.append("  end")
    for nid, (text, kind) in graph["nodes"].items():
        if nid not in grouped:
            out.append(f'  {nid}["{label(text)}"]:::{kind}')
    for a, b, lbl in graph["edges"]:
        out.append(f'  {a} -->|"{label(lbl)}"| {b}' if lbl else f"  {a} --> {b}")
    for kind, style in MERMAID_STYLE.items():
        out.append(f"  classDef {kind} {style}")
    return "\n".join(out) + "\n"


DOT_STYLE = {
    "cluster": 'shape=folder, style=filled, fillcolor="#e8eefc", color="#3b5bdb"',
    "node": 'shape=box3d, style=filled, fillcolor="#dbe4ff", color="#3b5bdb"',
    "vm": 'shape=box, style="rounded,filled", fillcolor="#f1f3f5", color="#495057"',
    "device": 'shape=box, style=filled, fillcolor="#fff3bf", color="#f08c00"',
    "url": 'shape=oval, style=filled, fillcolor="#d3f9d8", color="#2b8a3e"',
    "stack": 'shape=component, style=filled, fillcolor="#e3fafc", color="#0c8599"',
    "container": 'shape=box, style=filled, fillcolor="#e3fafc", color="#0c8599"',
}


def to_dot(graph, title=""):
    def q(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    out = [
        "digraph cmdb {",
        "  rankdir=LR; fontname=Helvetica; fontsize=11;",
        '  node [fontname=Helvetica, fontsize=10]; edge [fontname=Helvetica, fontsize=8, color="#868e96"];',
    ]
    if title:
        out.append(f"  label={q(title)}; labelloc=t;")
    grouped = set()
    for i, (group, ids) in enumerate(sorted(graph["groups"].items())):
        out.append(f'  subgraph cluster_{i} {{ label={q(group)}; style=rounded; color="#adb5bd";')
        for nid in ids:
            text, kind = graph["nodes"][nid]
            out.append(f"    {nid} [label={q(text)}, {DOT_STYLE.get(kind, '')}];")
            grouped.add(nid)
        out.append("  }")
    for nid, (text, kind) in graph["nodes"].items():
        if nid not in grouped:
            out.append(f"  {nid} [label={q(text)}, {DOT_STYLE.get(kind, '')}];")
    for a, b, lbl in graph["edges"]:
        out.append(f"  {a} -> {b}" + (f" [label={q(lbl)}]" if lbl else "") + ";")
    out.append("}")
    return "\n".join(out) + "\n"


class GraphvizMissing(RuntimeError):
    pass


def render_dot(dot_source, fmt):
    binary = shutil.which(get_plugin_config(PLUGIN, "graphviz_dot") or "dot")
    if not binary:
        raise GraphvizMissing("Graphviz 'dot' is not installed in the NetBox image")
    proc = subprocess.run([binary, f"-T{fmt}"], input=dot_source.encode(), capture_output=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"dot failed: {proc.stderr.decode()[:300]}")
    return proc.stdout
