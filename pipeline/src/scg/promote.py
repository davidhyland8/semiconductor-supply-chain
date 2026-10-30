"""Merge reviewed extraction candidates into the seed graph.

Review decisions live in data/extracted/decisions.csv, one row per candidate
(source_id + 1-based line number):

    source_id,line,decision,set_supplier,set_buyer,set_input,set_has_alternatives,reason

decision is accept or reject; set_* override the candidate's fields. Candidates
without a decision row are accepted as-is unless an entity has no node_id.
Every override or rejection needs a reason. Promotion is idempotent: evidence is
deduplicated by (edge, source, excerpt) and existing edges are never removed.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from scg import paths
from scg.seed import EDGE_FIELDS, EVIDENCE_FIELDS, _rows
from scg.validate import normalise

ALT_RANK = {"unknown": 0, "yes": 1, "no": 2}


@dataclass
class PromoteResult:
    edges_added: int = 0
    evidence_added: int = 0
    rejected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def edge_id(supplier: str, buyer: str, input_id: str) -> str:
    return f"{supplier}-to-{buyer}-{input_id}"


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def alias_index(seed_dir: Path) -> dict[str, str]:
    """Map normalised node names, ids and aliases to node ids."""
    index = {}
    for row in _rows(seed_dir / "nodes.csv"):
        for name in [row["id"], row["name"], *row.get("aliases", "").split(";")]:
            if name.strip():
                index.setdefault(_name_key(name), row["id"])
    return index


def resolve(entity: dict, index: dict[str, str]) -> str | None:
    """The entity's node_id, or a node whose name/alias matches its mention or proposed_name."""
    if entity.get("node_id"):
        return entity["node_id"]
    for name in (entity.get("mention"), entity.get("proposed_name")):
        if name and _name_key(name) in index:
            return index[_name_key(name)]
    return None


def load_decisions(path: Path) -> dict[tuple[str, int], dict]:
    decisions = {}
    for row in _rows(path):
        key = (row["source_id"], int(row["line"]))
        if row["decision"] not in ("accept", "reject"):
            raise ValueError(f"decisions.csv {key}: decision must be accept or reject")
        if (row["decision"] == "reject" or any(row.get(k) for k in row if k.startswith("set_"))) and not row.get("reason"):
            raise ValueError(f"decisions.csv {key}: rejections and overrides need a reason")
        decisions[key] = row
    return decisions


def promote(
    files: list[Path],
    seed_dir: Path = paths.SEED_DIR,
    sources_dir: Path = paths.SOURCES_DIR,
    decisions_path: Path = paths.EXTRACTED_DIR / "decisions.csv",
) -> PromoteResult:
    result = PromoteResult()
    decisions = load_decisions(decisions_path)
    aliases = alias_index(seed_dir)
    published = {r["id"]: r.get("published", "") for r in _rows(sources_dir / "sources.csv")}
    source_urls = {r["id"]: r.get("url", "") for r in _rows(sources_dir / "sources.csv")}

    edges = {r["id"]: r for r in _rows(seed_dir / "edges.csv")}
    evidence = _rows(seed_dir / "evidence.csv")
    seen_ev = {(e["edge_id"], e.get("source_id", ""), normalise(e.get("excerpt", ""))) for e in evidence}

    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["source_id"], lineno)
            label = f"{rec['source_id']}:{lineno}"
            dec = decisions.get(key, {})
            if dec.get("decision") == "reject":
                result.rejected.append(f"{label} ({dec['reason']})")
                continue

            supplier = dec.get("set_supplier") or resolve(rec["supplier"], aliases)
            buyer = dec.get("set_buyer") or resolve(rec["buyer"], aliases)
            input_id = dec.get("set_input") or rec["input"]
            alt = dec.get("set_has_alternatives") or rec["has_alternatives"]
            if not supplier or not buyer:
                missing = rec["supplier"] if not supplier else rec["buyer"]
                result.skipped.append(f"{label}: no node for {missing['mention']!r}")
                continue

            eid = edge_id(supplier, buyer, input_id)
            as_of = published.get(rec["source_id"], "")[:7]
            weight = rec.get("weight") or {}
            edge = edges.get(eid)
            if edge is None:
                edge = {k: "" for k in EDGE_FIELDS}
                edge.update(id=eid, supplier=supplier, buyer=buyer, input=input_id, has_alternatives=alt, as_of=as_of)
                edges[eid] = edge
                result.edges_added += 1
            elif ALT_RANK[alt] > ALT_RANK.get(edge["has_alternatives"], 0):
                edge["has_alternatives"] = alt
            if weight and (not edge["weight_value"] or as_of >= edge["as_of"]):
                edge.update(weight_value=str(weight["value"]), weight_metric=weight["metric"], weight_basis=weight["basis"])
            if as_of > edge["as_of"]:
                edge["as_of"] = as_of

            ev_key = (eid, rec["source_id"], normalise(rec["excerpt"]))
            if ev_key in seen_ev:
                continue
            seen_ev.add(ev_key)
            evidence.append({
                "edge_id": eid,
                "source_id": rec["source_id"],
                "url": source_urls.get(rec["source_id"], ""),
                "excerpt": rec["excerpt"],
                "locator": rec["locator"],
                "strength": rec["strength"],
                "reasoning": dec.get("reason", "") if any(dec.get(k) for k in dec if k.startswith("set_")) else "",
            })
            result.evidence_added += 1

    _write(seed_dir / "edges.csv", EDGE_FIELDS, sorted(edges.values(), key=lambda e: e["id"]))
    _write(seed_dir / "evidence.csv", EVIDENCE_FIELDS, sorted(evidence, key=lambda e: (e["edge_id"], e.get("source_id", ""))))
    return result


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
