"""Review queue: which candidates can be promoted as they are, which need a human
decision, and the state of every source document.

A candidate is accepted without review only when nothing about it needs checking
(see `review_reasons`). Everything else waits for a row in decisions.csv. A
candidate whose evidence is already in the seed graph counts as promoted.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from scg import paths
from scg.entities import _rows, entity_key, node_index, resolve
from scg.validate import normalise

EXTRACTABLE = {"10-K", "20-F", "annual_report", "press_release", "news", "investor_presentation"}


@dataclass
class Candidate:
    source_id: str
    line: int
    rec: dict
    supplier: str | None
    buyer: str | None
    reasons: list[str]
    state: str  # promoted | rejected | accepted | auto | needs_review | blocked | ignored

    @property
    def label(self) -> str:
        return f"{self.source_id}:{self.line}"


def review_reasons(rec: dict, supplier: str | None, buyer: str | None, input_ids: set[str]) -> list[str]:
    reasons = []
    if rec.get("confidence") != "high":
        reasons.append(f"{rec.get('confidence', 'no')} confidence")
    if rec.get("anonymised"):
        reasons.append("anonymised counterparty")
    if rec.get("input_is_new") or rec["input"] not in input_ids:
        reasons.append(f"new input {rec['input']!r}")
    if rec.get("weight"):
        reasons.append("weight to check")
    if rec.get("has_alternatives") == "no":
        reasons.append("sole-source claim")
    for side, nid in (("supplier", supplier), ("buyer", buyer)):
        if not nid:
            reasons.append(f"unmatched {side} {rec[side]['mention']!r}")
    return reasons


def candidates(
    files: list[Path],
    seed_dir: Path = paths.SEED_DIR,
    decisions: dict[tuple[str, int], dict] | None = None,
    ignored: set[str] | None = None,
) -> list[Candidate]:
    decisions = decisions or {}
    ignored = ignored or set()
    index = node_index(seed_dir)
    input_ids = {r["id"] for r in _rows(seed_dir / "inputs.csv")}
    # One excerpt can support several edges (a sentence naming three suppliers), so match on the edge too.
    promoted = {(e["edge_id"], e.get("source_id", ""), normalise(e.get("excerpt", ""))) for e in _rows(seed_dir / "evidence.csv")}
    out = []
    for path in files:
        for line, text in enumerate(path.read_text().splitlines(), start=1):
            if not text.strip():
                continue
            rec = json.loads(text)
            dec = decisions.get((rec["source_id"], line), {})
            supplier = dec.get("set_supplier") or resolve(rec["supplier"], index)
            buyer = dec.get("set_buyer") or resolve(rec["buyer"], index)
            reasons = review_reasons(rec, supplier, buyer, input_ids | {dec.get("set_input", "")} - {""})
            edge = f"{supplier}-to-{buyer}-{dec.get('set_input') or rec['input']}"
            if (edge, rec["source_id"], normalise(rec["excerpt"])) in promoted:
                state = "promoted"
            elif dec.get("decision") == "reject":
                state = "rejected"
            elif any(entity_key(rec[s]) in ignored for s in ("supplier", "buyer") if not (supplier if s == "supplier" else buyer)):
                state = "ignored"
            elif not supplier or not buyer:
                state = "blocked"  # waiting on an entity decision in entities.csv
            elif dec.get("decision") == "accept":
                state = "accepted"
            elif reasons:
                state = "needs_review"
            else:
                state = "auto"
            out.append(Candidate(rec["source_id"], line, rec, supplier, buyer, reasons, state))
    return out


@dataclass
class SourceStatus:
    source_id: str
    doc_type: str
    cached: bool
    extracted: bool
    counts: dict[str, int] = field(default_factory=dict)


def status(
    sources_dir: Path = paths.SOURCES_DIR,
    extracted_dir: Path = paths.EXTRACTED_DIR,
    cands: list[Candidate] | None = None,
) -> list[SourceStatus]:
    by_source: dict[str, dict[str, int]] = {}
    for c in cands or []:
        counts = by_source.setdefault(c.source_id, {})
        counts[c.state] = counts.get(c.state, 0) + 1
    out = []
    for s in _rows(sources_dir / "sources.csv"):
        out.append(SourceStatus(
            source_id=s["id"],
            doc_type=s["doc_type"],
            cached=(sources_dir / "cache" / f"{s['id']}.txt").exists(),
            extracted=(extracted_dir / f"{s['id']}.jsonl").exists(),
            counts=by_source.get(s["id"], {}),
        ))
    return out


def to_extract(statuses: list[SourceStatus], seed_dir: Path = paths.SEED_DIR) -> list[str]:
    """Cached documents of an extractable type that have not been extracted and aren't
    already used only as production-location sources."""
    used_for_production = {r.get("source_id") for r in _rows(seed_dir / "production.csv")}
    return [
        s.source_id for s in statuses
        if s.cached and not s.extracted and s.doc_type in EXTRACTABLE and s.source_id not in used_for_production
    ]


def review_markdown(cands: list[Candidate], names: dict[str, str]) -> str:
    """data/extracted/review.md: every candidate waiting on a decision, ready to copy into decisions.csv."""
    todo = [c for c in cands if c.state in ("needs_review", "blocked")]
    lines = [
        "# Review queue",
        "",
        f"{len(todo)} candidates need a decision. Accept or reject each in `decisions.csv`",
        "(`source_id,line,decision,set_supplier,set_buyer,set_input,set_has_alternatives,reason`).",
        "Blocked candidates name a company with no node: decide it in `entities.csv` first.",
        "",
    ]
    for source in sorted({c.source_id for c in todo}):
        lines += [f"## {source}", ""]
        for c in (c for c in todo if c.source_id == source):
            r = c.rec
            sup = names.get(c.supplier or "", r["supplier"].get("proposed_name") or r["supplier"]["mention"])
            buy = names.get(c.buyer or "", r["buyer"].get("proposed_name") or r["buyer"]["mention"])
            weight = r.get("weight") or {}
            lines += [
                f"### line {c.line}: {sup} → {buy} ({r['input']}){'  — BLOCKED' if c.state == 'blocked' else ''}",
                "",
                f"> {r['excerpt']}",
                "",
                f"- Locator: {r['locator']} · strength: {r['strength']} · alternatives: {r['has_alternatives']}"
                + (f" · weight: {weight.get('value')} {weight.get('metric')} ({weight.get('basis')})" if weight else ""),
                f"- Needs review: {', '.join(c.reasons)}",
            ]
            if r.get("notes"):
                lines.append(f"- Extractor notes: {r['notes']}")
            lines += ["", f"`{c.source_id},{c.line},accept,,,,,`", ""]
    return "\n".join(lines) + "\n"
