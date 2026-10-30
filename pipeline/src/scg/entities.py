"""Entity resolution across extraction files.

Names are matched on a canonical key: case, punctuation and legal suffixes are
ignored ("Taiwan Semiconductor Manufacturing Co., Ltd." = "Taiwan Semiconductor
Manufacturing"), and a trailing parenthetical is treated as another name
("King Yuan Electronics (KYEC)" also matches "KYEC").

Mentions that match no graph node are grouped across documents into
data/extracted/entities.csv, one row per distinct company. Each row is matched
against the ETO market catalogue where possible and waits for a decision:

    create  add a node to nodes.csv (needs node_id, name, kind, stage; companies need hq_country)
    alias   the mention is another name for an existing node_id; it is added to its aliases
    ignore  candidates naming this entity are not promoted

Every decision needs a reason. `scg entities` refreshes the file and keeps the decisions.
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from scg import paths
from scg.eto import market

ENTITY_FIELDS = [
    "key", "proposed_name", "mentions", "sources", "candidates", "eto_match",
    "decision", "node_id", "name", "kind", "stage", "hq_country", "eto_provider_id", "reason",
]
NODE_FIELDS = ["id", "name", "kind", "parent", "stage", "role", "hq_country", "aliases", "ticker", "eto_provider_id", "notes"]

# How a filer refers to itself; never stored as an alias.
SELF_REFERENCES = {"we", "us", "our", "the company", "company", "the registrant"}

SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "plc", "sa", "ag",
    "nv", "bv", "gmbh", "kk", "se", "holdings", "holding", "group", "the",
}


def names_of(name: str) -> list[str]:
    """The name plus any trailing parenthetical, e.g. 'King Yuan Electronics (KYEC)' -> both parts."""
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", name)
    return [m.group(1), m.group(2)] if m else [name]


def canonical(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.casefold().replace("&", " and "))
    while words and words[-1] in SUFFIXES:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return "".join(words)


def keys_of(name: str) -> list[str]:
    return [k for n in names_of(name) if (k := canonical(n))]


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def node_index(seed_dir: Path = paths.SEED_DIR) -> dict[str, str]:
    """Canonical keys of node ids, names and aliases -> node id."""
    index: dict[str, str] = {}
    for row in _rows(seed_dir / "nodes.csv"):
        for name in [row["id"].replace("-", " "), row["name"], *row.get("aliases", "").split(";")]:
            for k in keys_of(name) if name.strip() else []:
                index.setdefault(k, row["id"])
    return index


def resolve(entity: dict, index: dict[str, str]) -> str | None:
    """The entity's node_id, or the node whose name or alias matches its mention or proposed_name."""
    if entity.get("node_id"):
        return entity["node_id"]
    for name in (entity.get("mention"), entity.get("proposed_name")):
        for k in keys_of(name or ""):
            if k in index:
                return index[k]
    return None


def entity_key(entity: dict) -> str:
    mention = "" if entity["mention"].strip().casefold() in SELF_REFERENCES else entity["mention"]
    keys = keys_of(entity.get("proposed_name") or "") or keys_of(mention)
    return keys[0] if keys else ""


def unresolved(files: list[Path], seed_dir: Path = paths.SEED_DIR, skip: set[tuple[str, int]] = frozenset()) -> dict[str, dict]:
    """Unmatched entities across files, grouped by canonical key. `skip` holds rejected (source_id, line)s."""
    index = node_index(seed_dir)
    groups: dict[str, dict] = defaultdict(lambda: {"mentions": set(), "sources": set(), "names": [], "candidates": 0})
    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            rec = json.loads(line)
            if (rec["source_id"], lineno) in skip:
                continue
            for side in ("supplier", "buyer"):
                ent = rec[side]
                if resolve(ent, index):
                    continue
                key = entity_key(ent)
                if not key:
                    continue
                g = groups[key]
                if ent["mention"].strip().casefold() not in SELF_REFERENCES:
                    g["mentions"].add(ent["mention"])
                g["sources"].add(rec["source_id"])
                g["names"].append(ent.get("proposed_name") or ent["mention"])
                g["candidates"] += 1
    return groups


def eto_index(seed_dir: Path = paths.SEED_DIR) -> dict[str, dict]:
    out = {}
    for c in market(seed_dir)["companies"]:
        for name in [c["name"], *c["aliases"]]:
            for k in keys_of(name):
                out.setdefault(k, c)
    return out


def refresh(
    files: list[Path],
    seed_dir: Path = paths.SEED_DIR,
    path: Path = paths.EXTRACTED_DIR / "entities.csv",
    skip: set[tuple[str, int]] = frozenset(),
) -> list[dict]:
    """Rewrite entities.csv from the current extractions, keeping existing decisions."""
    existing = {r["key"]: r for r in _rows(path)}
    eto = eto_index(seed_dir)
    rows = []
    for key, g in sorted(unresolved(files, seed_dir, skip).items()):
        row = existing.get(key, {k: "" for k in ENTITY_FIELDS})
        proposed = max(set(g["names"]), key=g["names"].count)
        match = eto.get(key) or next((eto[k] for m in g["mentions"] for k in keys_of(m) if k in eto), None)
        row.update(
            key=key,
            proposed_name=proposed,
            mentions=";".join(sorted(g["mentions"])),
            sources=";".join(sorted(g["sources"])),
            candidates=str(g["candidates"]),
            eto_match=f"{match['eto_provider_id']} {match['name']}" if match else "",
        )
        if not row["decision"] and match:
            # Prefill from ETO so a reviewer only has to confirm with a decision and reason.
            row.update(
                node_id=row["node_id"] or match["id"],
                name=row["name"] or match["name"],
                kind=row["kind"] or "company",
                stage=row["stage"] or (match["stage"] or ""),
                hq_country=row["hq_country"] or (match["hq_country"] or ""),
                eto_provider_id=row["eto_provider_id"] or match["eto_provider_id"],
            )
        rows.append(row)
    # Decided rows whose entity is now resolved stay as a record.
    seen = {r["key"] for r in rows}
    rows += [r for k, r in existing.items() if k not in seen and r.get("decision")]
    _write(path, ENTITY_FIELDS, sorted(rows, key=lambda r: r["key"]))
    return rows


def check(path: Path = paths.EXTRACTED_DIR / "entities.csv", seed_dir: Path = paths.SEED_DIR) -> list[str]:
    errors = []
    node_ids = {r["id"] for r in _rows(seed_dir / "nodes.csv")}
    for i, r in enumerate(_rows(path), start=2):
        d = r.get("decision", "")
        if not d:
            continue
        where = f"entities.csv:{i} ({r['key']})"
        if d not in ("create", "alias", "ignore"):
            errors.append(f"{where}: decision must be create, alias or ignore")
        if not r.get("reason", "").strip():
            errors.append(f"{where}: reason is required")
        if d == "alias" and r["node_id"] not in node_ids:
            errors.append(f"{where}: alias needs an existing node_id")
        if d == "create":
            missing = [f for f in ("node_id", "name", "kind", "stage") if not r.get(f)]
            if r.get("kind") == "company" and not r.get("hq_country"):
                missing.append("hq_country")
            if missing:
                errors.append(f"{where}: create needs {', '.join(missing)}")
    return errors


def apply(path: Path = paths.EXTRACTED_DIR / "entities.csv", seed_dir: Path = paths.SEED_DIR) -> tuple[list[str], set[str]]:
    """Apply create and alias decisions to nodes.csv. Returns (changes, ignored keys)."""
    errors = check(path, seed_dir)
    if errors:
        raise ValueError("; ".join(errors))
    nodes_path = seed_dir / "nodes.csv"
    nodes = _rows(nodes_path)
    fields = list(nodes[0]) if nodes else NODE_FIELDS
    by_id = {n["id"]: n for n in nodes}
    changes, ignored = [], set()
    for r in _rows(path):
        if r["decision"] == "ignore":
            ignored.add(r["key"])
        elif r["decision"] == "create" and r["node_id"] not in by_id:
            node = {k: "" for k in fields}
            mentions = [m for m in r["mentions"].split(";") if m and m != r["name"]]
            node.update(
                id=r["node_id"], name=r["name"], kind=r["kind"], stage=r["stage"], hq_country=r["hq_country"],
                eto_provider_id=r["eto_provider_id"], aliases=";".join(mentions),
                notes=f"Added from extraction ({r['sources']}): {r['reason']}",
            )
            nodes.append(node)
            by_id[node["id"]] = node
            changes.append(f"created node {node['id']}")
        elif r["decision"] == "alias":
            node = by_id[r["node_id"]]
            aliases = [a for a in node["aliases"].split(";") if a]
            new = [m for m in r["mentions"].split(";") if m and m not in aliases and m != node["name"]]
            if new:
                node["aliases"] = ";".join(aliases + new)
                changes.append(f"aliases for {node['id']}: {', '.join(new)}")
    if changes:
        _write(nodes_path, fields, nodes)
    return changes, ignored
