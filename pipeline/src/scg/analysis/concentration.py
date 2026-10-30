"""Market concentration from the ETO dataset: HHI per input (by company and by
country) and market-size-weighted country shares per stage.

Design, equipment and materials shares are built from ETO's per-input country
shares. Fabrication and packaging/test use ETO's stage-level shares of site
capacity by location (from SIA). Assembly and end products has no source, so it
is reported as a gap.
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

from scg import paths

ETO_DIR = paths.DATA_DIR / "raw" / "eto"

ISO3_TO_ISO2 = {
    "USA": "US", "CHN": "CN", "KOR": "KR", "JPN": "JP", "TWN": "TW", "DEU": "DE", "ITA": "IT",
    "NLD": "NL", "MYS": "MY", "SGP": "SG", "CHE": "CH", "AUT": "AT", "SWE": "SE", "GBR": "GB",
    "FRA": "FR", "ISR": "IL", "BLR": "BY", "CZE": "CZ", "CAN": "CA", "LUX": "LU", "HUN": "HU",
    "EUR": "EU",  # ETO aggregates some European providers as a region
}
def _is_other(name: str) -> bool:
    """ETO's 'Various countries' / 'Various companies' buckets (and variants)."""
    return name.strip().lower().startswith("various")

# Top-level ETO inputs per stage, chosen so no input is a sub-type of another (no double counting).
STAGE_INPUTS = {
    "design_tools_ip": ["N84", "N85"],
    "chip_design": ["N6", "N5", "N13"],
    "equipment": ["N19", "N36", "N55", "N60", "N17", "N86", "N59", "N120", "N83", "N109"],
    "materials": ["N26", "N31", "N33", "N88", "N90", "N91", "N92", "N100"],
}
# ETO stage rows giving capacity share by site location.
SITE_STAGES = {"fabrication": "S2", "packaging_test": "S3"}
NOT_COVERED = ["assembly_end_products"]


def parse_market_size(text: str) -> float | None:
    """'$13 billion (2025)' -> 13e9. None if no figure."""
    m = re.search(r"\$\s*([\d.,]+)\s*(billion|million)", text or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "")) * (1e9 if m.group(2) == "billion" else 1e6)


def hhi(shares_pct: list[float]) -> float:
    """Herfindahl-Hirschman index from percentage shares (0-10,000)."""
    return round(sum(s * s for s in shares_pct), 1)


def load_eto(eto_dir: Path = ETO_DIR) -> tuple[dict, dict, list[dict]]:
    def rows(name):
        with (eto_dir / name).open(newline="") as f:
            return list(csv.DictReader(f))

    inputs = {r["input_id"]: r for r in rows("inputs.csv")}
    providers = {r["provider_id"]: r for r in rows("providers.csv")}
    return inputs, providers, rows("provision.csv")


def input_concentration(eto_dir: Path = ETO_DIR) -> list[dict]:
    inputs, providers, provision = load_eto(eto_dir)
    companies: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    countries: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for r in provision:
        if not r["share_provided"]:
            continue
        prov = providers[r["provider_id"]]
        entry = (r["provider_name"], float(r["share_provided"]), r["year"])
        (countries if prov["provider_type"] == "country" else companies)[r["provided_id"]].append(entry)

    out = []
    for iid, inp in inputs.items():
        comp = [c for c in companies.get(iid, []) if not _is_other(c[0])]
        ctry = [c for c in countries.get(iid, []) if not _is_other(c[0])]
        if not comp and not ctry:
            continue
        top = max(comp, key=lambda c: c[1]) if comp else None
        years = sorted({c[2] for c in comp + ctry if c[2]})
        out.append({
            "eto_id": iid,
            "name": inp["input_name"],
            "market_size_usd": parse_market_size(inp["market_share_chart_global_market_size_info"]),
            "year": years[-1] if years else None,
            "company_hhi": hhi([c[1] for c in comp]) if comp else None,
            "top_company": {"name": top[0], "share": top[1] / 100} if top else None,
            "country_hhi": hhi([c[1] for c in ctry]) if ctry else None,
            "country_shares": {ISO3_TO_ISO2.get(c[0], c[0]): c[1] / 100 for c in ctry},
        })
    return sorted(out, key=lambda r: -(r["company_hhi"] or 0))


def stage_country_shares(eto_dir: Path = ETO_DIR) -> dict[str, dict]:
    """Country share of each stage, weighting each input's country shares by its market size."""
    by_input = {r["eto_id"]: r for r in input_concentration(eto_dir)}
    out: dict[str, dict] = {}
    for stage, ids in STAGE_INPUTS.items():
        used = [by_input[i] for i in ids if i in by_input and by_input[i]["country_shares"]]
        sizes = [u["market_size_usd"] for u in used]
        weights = sizes if all(sizes) else [1.0] * len(used)
        totals: dict[str, float] = defaultdict(float)
        for u, w in zip(used, weights):
            for country, share in u["country_shares"].items():
                totals[country] += share * w
        total_w = sum(weights)
        shares = {c: round(v / total_w, 4) for c, v in sorted(totals.items(), key=lambda kv: -kv[1])}
        out[stage] = {
            "shares": shares,
            "hhi": hhi([s * 100 for s in shares.values()]),
            "inputs": [u["name"] for u in used],
            "weighting": "market_size" if all(sizes) else "equal",
            "years": sorted({u["year"] for u in used if u["year"]}),
            "basis": "Each input's country shares as reported by ETO, weighted by input market size",
            "other_share": round(max(0.0, 1 - sum(shares.values())), 4),
            "source": "ETO Advanced Semiconductor Supply Chain Dataset",
        }
    for stage, sid in SITE_STAGES.items():
        out[stage] = _site_shares(eto_dir, sid)
    for stage in NOT_COVERED:
        out[stage] = {"shares": {}, "inputs": [], "note": "Not covered by ETO; needs another public source."}
    return out


def _site_shares(eto_dir: Path, stage_id: str) -> dict:
    """Share of a stage's capacity by site location, from ETO's stage-level rows."""
    path = eto_dir / "stages.csv"
    if not path.exists():
        return {"shares": {}, "inputs": [], "note": "ETO stages.csv missing."}
    with path.open(newline="") as f:
        stage = next((r for r in csv.DictReader(f) if r["stage_id"] == stage_id), None)
    _, _, provision = load_eto(eto_dir)
    rows = [r for r in provision if r["provided_id"] == stage_id and r["share_provided"]]
    named = [r for r in rows if not _is_other(r["provider_name"])]
    shares = {ISO3_TO_ISO2.get(r["provider_name"], r["provider_name"]): float(r["share_provided"]) / 100 for r in named}
    shares = dict(sorted(shares.items(), key=lambda kv: -kv[1]))
    caption = re.sub(r"^Chart shows\s+", "", (stage or {}).get("market_share_chart_caption", "")).strip()
    caption = caption[:1].upper() + caption[1:]
    cited = re.findall(r"\[([^\]]+)\]", (stage or {}).get("market_share_chart_source", ""))
    return {
        "shares": shares,
        "hhi": hhi([s * 100 for s in shares.values()]),
        "inputs": [(stage or {}).get("stage_name", stage_id)],
        "years": sorted({r["year"] for r in rows if r["year"]}),
        "basis": caption,
        "other_share": round(sum(float(r["share_provided"]) for r in rows if _is_other(r["provider_name"])) / 100, 4),
        "source": "ETO Advanced Semiconductor Supply Chain Dataset" + (f", citing {cited[0]}" if cited else ""),
    }
