"""Build the versioned graph the web app loads: data/build/graph.v<N>.json.

A new version is written only when the content changes; data/build/CHANGELOG.md
records what was added or removed between versions.
"""

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import networkx as nx

from scg import eto, paths
from scg.analysis.concentration import input_concentration, stage_country_shares
from scg.analysis.graph_metrics import chokepoints, criticality
from scg.seed import _rows, load_edges, load_nodes

STRENGTH_RANK = {"inferred": 1, "reported": 2, "disclosed": 3}
SCHEMA_VERSION = 1


def build_graph(seed_dir: Path = paths.SEED_DIR, sources_dir: Path = paths.SOURCES_DIR) -> nx.DiGraph:
    g = nx.MultiDiGraph()
    for node in load_nodes(seed_dir):
        g.add_node(node["id"], **node)
    for edge in load_edges(seed_dir):
        g.add_edge(edge["supplier"], edge["buyer"], key=edge["id"], **edge)
    return g


def _evidence_with_sources(edge: dict, sources: dict[str, dict]) -> list[dict]:
    out = []
    for ev in edge["evidence"]:
        src = sources.get(ev.get("source_id", ""), {})
        out.append({**ev, "source_title": src.get("title", ""), "source_published": src.get("published", "")})
    return sorted(out, key=lambda e: -STRENGTH_RANK[e["strength"]])


def graph_document(seed_dir: Path = paths.SEED_DIR, sources_dir: Path = paths.SOURCES_DIR) -> dict:
    g = build_graph(seed_dir, sources_dir)
    sources = {r["id"]: r for r in _rows(sources_dir / "sources.csv")}
    simple = nx.DiGraph(g)
    catalogue = eto.market(seed_dir)
    positions = catalogue.pop("node_positions")

    nodes = []
    for nid, data in sorted(g.nodes(data=True)):
        nodes.append({
            **data,
            "upstream_count": len(nx.ancestors(simple, nid)),
            "downstream_count": len(nx.descendants(simple, nid)),
            **({"market_positions": positions[nid]} if nid in positions else {}),
        })

    edges = []
    for _, _, data in sorted(g.edges(data=True), key=lambda e: e[2]["id"]):
        evidence = _evidence_with_sources(data, sources)
        edges.append({**data, "evidence": evidence, "strength": evidence[0]["strength"]})

    return {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
        "inputs": _rows(seed_dir / "inputs.csv"),
        "groups": _rows(seed_dir / "groups.csv"),
        "market": catalogue,
        "analysis": {
            "chokepoints": chokepoints(edges),
            "criticality": criticality(nodes, edges),
            "input_concentration": input_concentration(),
            "stage_country_shares": stage_country_shares(),
        },
    }


def _content_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def _latest(build_dir: Path) -> tuple[int, Path | None]:
    versions = [(int(m.group(1)), p) for p in build_dir.glob("graph.v*.json") if (m := re.fullmatch(r"graph\.v(\d+)\.json", p.name))]
    return max(versions) if versions else (0, None)


def _changelog_entry(version: int, prev: dict | None, doc: dict) -> str:
    def ids(d, key):
        return {x["id"] for x in d[key]} if d else set()

    lines = [f"## v{version} ({dt.date.today().isoformat()})", ""]
    lines.append(f"{len(doc['nodes'])} nodes, {len(doc['edges'])} edges.")
    def listed(items):
        items = sorted(items)
        return ", ".join(items[:20]) + (" …" if len(items) > 20 else "")

    for key in ("nodes", "edges"):
        added, removed = ids(doc, key) - ids(prev, key), ids(prev, key) - ids(doc, key)
        before = {x["id"]: x for x in prev[key]} if prev else {}
        changed = {x["id"] for x in doc[key] if x["id"] in before and x != before[x["id"]]}
        if added:
            lines.append(f"- Added {len(added)} {key}: {listed(added)}")
        if removed:
            lines.append(f"- Removed {len(removed)} {key}: {listed(removed)}")
        if changed:
            lines.append(f"- Changed {len(changed)} {key}: {listed(changed)}")
    if prev or doc.get("market"):
        before = {c["id"] for c in (prev or {}).get("market", {}).get("companies", [])}
        after = {c["id"] for c in doc.get("market", {}).get("companies", [])}
        if after - before:
            lines.append(f"- Added {len(after - before)} ETO market companies: {listed(after - before)}")
        if before - after:
            lines.append(f"- Removed {len(before - after)} ETO market companies: {listed(before - after)}")
    if prev:
        sections = sorted(k for k in doc.get("analysis", {}) if doc["analysis"][k] != prev.get("analysis", {}).get(k))
        if sections:
            lines.append(f"- Analysis changed: {', '.join(sections)}")
    return "\n".join(lines) + "\n\n"


def write_build(build_dir: Path = paths.BUILD_DIR) -> tuple[Path, bool]:
    """Write a new graph version if content changed. Returns (path, written)."""
    build_dir.mkdir(parents=True, exist_ok=True)
    doc = graph_document()
    content_hash = _content_hash(doc)
    version, latest = _latest(build_dir)
    prev = json.loads(latest.read_text()) if latest else None
    if prev and prev.get("content_hash") == content_hash:
        return latest, False

    version += 1
    out = build_dir / f"graph.v{version}.json"
    stamped = {"version": version, "built": dt.date.today().isoformat(), "content_hash": content_hash, **doc}
    out.write_text(json.dumps(stamped, indent=1, ensure_ascii=False) + "\n")

    changelog = build_dir / "CHANGELOG.md"
    existing = changelog.read_text() if changelog.exists() else "# Graph build changelog\n\n"
    head, _, rest = existing.partition("\n\n")
    changelog.write_text(head + "\n\n" + _changelog_entry(version, prev, doc) + rest)
    return out, True
