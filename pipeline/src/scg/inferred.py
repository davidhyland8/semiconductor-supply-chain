"""Hand-curated inferred edges, kept as code so the reasoning is reviewable.

Each rule says why a relationship is believed to exist without a source that
states it. Equipment rules rest on ETO / TechInsights 2025 market shares: when
a toolmaker holds a dominant share of a tool category, every major fab using
that process step is assumed to buy from it. `scg add-inferred` writes these to
data/seed/edges.csv and evidence.csv, skipping any (supplier, buyer, input)
that already has an edge from a stated source.
"""

import csv

from scg import paths
from scg.promote import edge_id
from scg.seed import EDGE_FIELDS, EVIDENCE_FIELDS, _rows

ETO_SOURCE = "eto-chip-explorer-2026"
ETO_SOURCE_ROW = {
    "id": ETO_SOURCE,
    "url": "https://github.com/georgetown-cset/eto-chip-explorer/tree/060ccc7503ea35abaddfae4f7746f70607fee800/data",
    "title": "ETO Advanced Semiconductor Supply Chain Dataset (provision.csv)",
    "publisher": "Emerging Technology Observatory, CSET",
    "company": "",
    "doc_type": "dataset",
    "published": "2026-10",
    "retrieved": "2026-10-30",
    "sha256": "",
}

FABS = ["tsmc", "samsung-foundry", "samsung-memory", "sk-hynix", "micron", "intel-foundry", "smic", "umc", "globalfoundries"]
EUV_FABS_UNSOURCED = ["samsung-foundry", "micron"]

# (supplier, buyers, input, has_alternatives, reasoning)
EQUIPMENT_RULES = [
    ("asml", EUV_FABS_UNSOURCED, "euv-lithography", "no",
     "ASML holds 100% of the EUV lithography tool market (ETO/TechInsights 2025), and this fab runs EUV process nodes, so its EUV scanners can only come from ASML."),
    ("asml", ["umc", "globalfoundries"], "duv-lithography", "unknown",
     "ASML holds 99.3% of ArF immersion and 94.4% of ArF dry lithography tools (ETO/TechInsights 2025); this fab's 28nm-and-below nodes need ArF immersion scanners."),
    ("tokyo-electron", FABS, "resist-processing-tools", "unknown",
     "Tokyo Electron holds 92.6% of resist processing (coater/developer) tools (ETO/TechInsights 2025); every lithography line needs a track, so this fab almost certainly uses TEL tracks."),
    ("applied-materials", FABS, "deposition-tools", "unknown",
     "Applied Materials holds 41.2% of deposition tools overall, including 82.4% of PVD and 47.0% of CVD (ETO/TechInsights 2025); a major fab is very unlikely to run without Applied deposition tools."),
    ("kla", FABS, "process-control-tools", "unknown",
     "KLA holds 56.8% of process control tools and 85.9% of defect inspection tools (ETO/TechInsights 2025); a major fab is very unlikely to run without KLA inspection."),
    ("lam-research", ["samsung-foundry", "intel-foundry", "smic", "umc", "globalfoundries"], "etch-clean-tools", "unknown",
     "Lam Research holds 41.1% of dry etch tools (ETO/TechInsights 2025); a major fab is very unlikely to run without Lam etch tools. Lam's 10-K names its largest customers but not these."),
]

JSR_SOURCE = "jsr-tsmc-taiwan-resist-2026"
RESIST_RULES = [
    ("tokyo-ohka-kogyo", "tsmc",
     "Tokyo Ohka Kogyo (TOK) and Shin-Etsu Chemical both already operate production facilities in Taiwan, where they work directly with TSMC on resist development.",
     "TOK makes photoresist in Taiwan and co-develops resists with TSMC; co-development plus local production implies TOK supplies TSMC, but the article does not state a supply contract."),
    ("shin-etsu", "tsmc",
     "Tokyo Ohka Kogyo (TOK) and Shin-Etsu Chemical both already operate production facilities in Taiwan, where they work directly with TSMC on resist development.",
     "Shin-Etsu makes photoresist in Taiwan and co-develops resists with TSMC; co-development plus local production implies Shin-Etsu supplies TSMC, but the article does not state a supply contract."),
    ("jsr", "tsmc",
     "JSR currently develops products for Taiwanese customers by shipping samples from its facilities in Japan, the U.S., and Belgium.",
     "JSR (about a fifth of the global photoresist market) is building a Taiwan plant to supply and co-develop resists with TSMC and already ships development samples to Taiwanese customers; current volume supply to TSMC is likely but not stated."),
]


def inferred_edges() -> list[tuple[dict, dict]]:
    out = []
    for supplier, buyers, input_id, alt, reasoning in EQUIPMENT_RULES:
        for buyer in buyers:
            eid = edge_id(supplier, buyer, input_id)
            out.append((
                {"id": eid, "supplier": supplier, "buyer": buyer, "input": input_id,
                 "has_alternatives": alt, "as_of": "2025"},
                {"edge_id": eid, "source_id": ETO_SOURCE, "url": ETO_SOURCE_ROW["url"],
                 "strength": "inferred", "reasoning": reasoning},
            ))
    for supplier, buyer, excerpt, reasoning in RESIST_RULES:
        eid = edge_id(supplier, buyer, "photoresists")
        out.append((
            {"id": eid, "supplier": supplier, "buyer": buyer, "input": "photoresists",
             "has_alternatives": "unknown", "as_of": "2026-05"},
            {"edge_id": eid, "source_id": JSR_SOURCE, "excerpt": excerpt,
             "url": "https://www.tomshardware.com/tech-industry/jsr-to-build-first-taiwan-photoresist-plant-to-co-develop-advanced-resists-with-tsmc",
             "locator": "Article body", "strength": "inferred", "reasoning": reasoning},
        ))
    return out


def add_inferred() -> tuple[int, int]:
    """Write inferred edges not already covered by a sourced edge. Returns (added, skipped)."""
    from scg.collect import register_sources

    register_sources([ETO_SOURCE_ROW])
    edges = {r["id"]: r for r in _rows(paths.SEED_DIR / "edges.csv")}
    evidence = _rows(paths.SEED_DIR / "evidence.csv")
    existing_evidence = {(e["edge_id"], e.get("source_id", "")) for e in evidence}
    triples = {(e["supplier"], e["buyer"], e["input"]) for e in edges.values()}
    added = skipped = 0
    for edge, ev in inferred_edges():
        key = (edge["supplier"], edge["buyer"], edge["input"])
        if key in triples and (edge["id"], ev["source_id"]) not in existing_evidence:
            skipped += 1  # a stated source already covers it
            continue
        if edge["id"] not in edges:
            edges[edge["id"]] = {**{k: "" for k in EDGE_FIELDS}, **edge}
            triples.add(key)
            added += 1
        if (edge["id"], ev["source_id"]) not in existing_evidence:
            evidence.append(ev)
            existing_evidence.add((edge["id"], ev["source_id"]))
    for path, fields, rows in (
        (paths.SEED_DIR / "edges.csv", EDGE_FIELDS, sorted(edges.values(), key=lambda e: e["id"])),
        (paths.SEED_DIR / "evidence.csv", EVIDENCE_FIELDS, sorted(evidence, key=lambda e: (e["edge_id"], e.get("source_id", "")))),
    ):
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return added, skipped
