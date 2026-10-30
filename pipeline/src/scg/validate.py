"""Validation of extraction output (data/extracted/*.jsonl).

Beyond the JSON Schema, this checks that every excerpt appears verbatim in the
cached source text, so the extractor cannot paraphrase or invent support.
"""

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from scg import paths
from scg.schemas import validator

_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
})


def normalise(text: str) -> str:
    """Fold case, quotes, dashes, line-break hyphenation and whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT)
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def read_ids(path: Path) -> set[str] | None:
    """The id column of a CSV, or None if the file doesn't exist yet."""
    if not path.exists():
        return None
    with path.open(newline="") as f:
        return {row["id"] for row in csv.DictReader(f)}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_extraction(
    path: Path,
    seed_dir: Path = paths.SEED_DIR,
    sources_dir: Path = paths.SOURCES_DIR,
    cache_dir: Path = paths.CACHE_DIR,
) -> Report:
    report = Report()
    schema = validator("extraction")
    node_ids = read_ids(seed_dir / "nodes.csv")
    input_ids = read_ids(seed_dir / "inputs.csv")
    source_ids = read_ids(sources_dir / "sources.csv")
    texts: dict[str, str | None] = {}

    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{lineno}"
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            report.errors.append(f"{where}: invalid JSON ({e.msg})")
            continue
        report.records += 1

        schema_errors = sorted(schema.iter_errors(rec), key=lambda e: list(e.path))
        for e in schema_errors:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            report.errors.append(f"{where}: {loc}: {e.message}")
        if schema_errors:
            continue

        sid = rec["source_id"]
        if source_ids is not None and sid not in source_ids:
            report.errors.append(f"{where}: source_id {sid!r} not in sources.csv")

        for side in ("supplier", "buyer"):
            ent = rec[side]
            nid = ent["node_id"]
            if nid is None and not ent.get("proposed_name"):
                report.errors.append(f"{where}: {side} has no node_id and no proposed_name")
            if nid is not None and node_ids is not None and nid not in node_ids:
                report.errors.append(f"{where}: {side}.node_id {nid!r} not in nodes.csv")
        if rec["supplier"]["node_id"] is not None and rec["supplier"]["node_id"] == rec["buyer"]["node_id"]:
            report.errors.append(f"{where}: supplier and buyer are the same node")

        if input_ids is not None and not rec.get("input_is_new") and rec["input"] not in input_ids:
            report.errors.append(
                f"{where}: input {rec['input']!r} not in inputs.csv (set input_is_new if proposing it)"
            )

        if rec.get("anonymised") and not rec.get("notes"):
            report.errors.append(f"{where}: anonymised counterparty needs notes explaining the identification")

        if sid not in texts:
            cached = cache_dir / f"{sid}.txt"
            texts[sid] = normalise(cached.read_text()) if cached.exists() else None
        text = texts[sid]
        if text is None:
            report.warnings.append(f"{where}: no cached text for {sid!r}; excerpt not verified")
        elif normalise(rec["excerpt"]) not in text:
            report.errors.append(f"{where}: excerpt not found verbatim in {sid}.txt")

    if report.records == 0:
        report.warnings.append(f"{path.name}: no records")
    return report
