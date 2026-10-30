"""Load and validate the hand-curated seed graph (data/seed/*.csv).

CSV is the editing format; rows are converted to the JSON shapes in schema/
before validation, so the same schemas cover seed and built data.
"""

import csv
from collections import Counter
from pathlib import Path

from scg import paths
from scg.schemas import validator
from scg.validate import Report, normalise, read_ids

EDGE_FIELDS = [
    "id", "supplier", "buyer", "input", "has_alternatives",
    "weight_value", "weight_metric", "weight_basis", "as_of", "notes",
]
EVIDENCE_FIELDS = ["edge_id", "source_id", "url", "excerpt", "locator", "strength", "reasoning"]


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in ("", None, [])}


def parse_production_countries(cell: str) -> list[dict]:
    """'TW*;US:0.1;JP' -> [{country: TW, primary: True}, {country: US, share: 0.1}, {country: JP}]."""
    out = []
    for part in filter(None, (p.strip() for p in cell.split(";"))):
        entry: dict = {}
        if ":" in part:
            part, share = part.split(":", 1)
            entry["share"] = float(share)
        if part.endswith("*"):
            part = part[:-1]
            entry["primary"] = True
        out.append({"country": part, **entry})
    return out


def load_nodes(seed_dir: Path = paths.SEED_DIR) -> list[dict]:
    nodes = []
    for row in _rows(seed_dir / "nodes.csv"):
        node = _clean(dict(row))
        node.pop("production_countries", None)
        if row.get("aliases"):
            node["aliases"] = [a.strip() for a in row["aliases"].split(";") if a.strip()]
        if row.get("production_countries"):
            node["production_countries"] = parse_production_countries(row["production_countries"])
        nodes.append(node)
    return nodes


def load_edges(seed_dir: Path = paths.SEED_DIR) -> list[dict]:
    evidence: dict[str, list[dict]] = {}
    for row in _rows(seed_dir / "evidence.csv"):
        ev = _clean({k: row.get(k, "") for k in EVIDENCE_FIELDS})
        evidence.setdefault(ev.pop("edge_id", ""), []).append(ev)
    edges = []
    for row in _rows(seed_dir / "edges.csv"):
        edge = _clean({k: row.get(k, "") for k in ("id", "supplier", "buyer", "input", "has_alternatives", "as_of", "notes")})
        if row.get("weight_value"):
            edge["weight"] = {
                "value": float(row["weight_value"]),
                "metric": row.get("weight_metric", ""),
                "basis": row.get("weight_basis", ""),
            }
        edge["evidence"] = evidence.pop(row["id"], [])
        edges.append(edge)
    for orphan in evidence:
        edges.append({"id": orphan, "_orphan_evidence": True})
    return edges


def validate_seed(
    seed_dir: Path = paths.SEED_DIR,
    sources_dir: Path = paths.SOURCES_DIR,
    cache_dir: Path = paths.CACHE_DIR,
) -> Report:
    report = Report()
    nodes, edges = load_nodes(seed_dir), load_edges(seed_dir)
    input_ids = read_ids(seed_dir / "inputs.csv") or set()
    group_ids = read_ids(seed_dir / "groups.csv") or set()
    source_ids = read_ids(sources_dir / "sources.csv") or set()

    def schema_errors(kind: str, record: dict, label: str) -> bool:
        errs = list(validator(kind).iter_errors(record))
        for e in errs:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            report.errors.append(f"{label}: {loc}: {e.message}")
        return bool(errs)

    for kind, items in (("node", nodes), ("edge", edges)):
        for dup, n in Counter(i.get("id") for i in items).items():
            if n > 1:
                report.errors.append(f"duplicate {kind} id {dup!r}")

    node_ids = {n["id"] for n in nodes}
    for node in nodes:
        report.records += 1
        if schema_errors("node", node, f"node {node.get('id')}"):
            continue
        if node.get("parent") and node["parent"] not in group_ids:
            report.errors.append(f"node {node['id']}: parent {node['parent']!r} not in groups.csv")

    texts: dict[str, str | None] = {}
    seen_triples: Counter = Counter()
    for edge in edges:
        report.records += 1
        label = f"edge {edge.get('id')}"
        if edge.get("_orphan_evidence"):
            report.errors.append(f"evidence rows reference unknown edge_id {edge['id']!r}")
            continue
        if schema_errors("edge", edge, label):
            continue
        for side in ("supplier", "buyer"):
            if edge[side] not in node_ids:
                report.errors.append(f"{label}: {side} {edge[side]!r} not in nodes.csv")
        if edge["supplier"] == edge["buyer"]:
            report.errors.append(f"{label}: supplier and buyer are the same node")
        if edge["input"] not in input_ids:
            report.errors.append(f"{label}: input {edge['input']!r} not in inputs.csv")
        seen_triples[(edge["supplier"], edge["buyer"], edge["input"])] += 1

        for ev in edge["evidence"]:
            sid = ev.get("source_id")
            if sid is None:
                continue
            if sid not in source_ids:
                report.errors.append(f"{label}: source_id {sid!r} not in sources.csv")
                continue
            if "excerpt" not in ev:
                continue
            if sid not in texts:
                cached = cache_dir / f"{sid}.txt"
                texts[sid] = normalise(cached.read_text()) if cached.exists() else None
            if texts[sid] is None:
                report.warnings.append(f"{label}: no cached text for {sid!r}; excerpt not verified")
            elif normalise(ev["excerpt"]) not in texts[sid]:
                report.errors.append(f"{label}: excerpt not found verbatim in {sid}.txt")

    for (s, b, i), n in seen_triples.items():
        if n > 1:
            report.errors.append(f"{n} edges for the same supplier/buyer/input: {s} -> {b} ({i})")
    return report
