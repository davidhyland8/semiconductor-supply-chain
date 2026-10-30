"""ETO market catalogue: every ETO input and every ETO company, with market positions.

Companies already in the graph get their ETO positions attached. They are matched
by `eto_provider_id` in nodes.csv, or by a row in data/seed/eto_providers.csv,
which also skips providers that can't be attributed to one business unit and
reassigns single positions to another unit. Every mapping or skip there has a
written reason.

All other ETO companies with at least one market position go into a market
catalogue. ETO says what they sell and
their market share, not who buys from them, so they have no supply edges. They
are not graph nodes and take no part in scenarios until a sourced relationship
exists.
"""

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from scg import paths
from scg.analysis.concentration import ETO_DIR, ISO3_TO_ISO2, STAGE_INPUTS, _is_other, input_concentration, load_eto

STAGE_ORDER = ["design_tools_ip", "chip_design", "equipment", "materials", "fabrication", "packaging_test", "assembly_end_products"]
TYPE_STAGE = {"tool_resource": "equipment", "material_resource": "materials", "design_resource": "chip_design"}
ETO_STAGE = {"Design": "chip_design", "Fabrication": "fabrication", "Assembly, testing, and packaging (ATP)": "packaging_test"}
MAP_FIELDS = ["eto_provider_id", "eto_input_id", "node_id", "action", "reason"]


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def input_stages(eto_dir: Path = ETO_DIR) -> dict[str, str | None]:
    """Our stage for each ETO input: the stage of the top-level input it is a type of,
    else ETO's own stage, else a fallback by input type (tool -> equipment, ...)."""
    inputs, _, _ = load_eto(eto_dir)
    parent = {r["input_id"]: r["is_type_of_id"] for r in _rows(eto_dir / "sequence.csv") if r["is_type_of_id"]}
    top = {i: stage for stage, ids in STAGE_INPUTS.items() for i in ids}
    out = {}
    for iid, inp in inputs.items():
        node, seen = iid, set()
        while node not in top and node in parent and node not in seen:
            seen.add(node)
            node = parent[node]
        out[iid] = top.get(node) or ETO_STAGE.get(inp.get("stage_name", "")) or TYPE_STAGE.get(inp["type"])
    return out


def load_map(seed_dir: Path = paths.SEED_DIR) -> list[dict]:
    return _rows(seed_dir / "eto_providers.csv")


def provider_nodes(seed_dir: Path = paths.SEED_DIR) -> tuple[dict[str, str], set[str], dict[tuple[str, str], str]]:
    """(provider -> node, skipped providers, (provider, input) -> node overrides)."""
    to_node = {r["eto_provider_id"]: r["id"] for r in _rows(seed_dir / "nodes.csv") if r.get("eto_provider_id")}
    skipped, overrides = set(), {}
    for r in load_map(seed_dir):
        if r["action"] == "skip":
            skipped.add(r["eto_provider_id"])
        elif r["eto_input_id"]:
            overrides[(r["eto_provider_id"], r["eto_input_id"])] = r["node_id"]
        else:
            to_node[r["eto_provider_id"]] = r["node_id"]
    return to_node, skipped, overrides


def check_mapping(seed_dir: Path = paths.SEED_DIR, eto_dir: Path = ETO_DIR) -> list[str]:
    """Errors: map rows without reasons or pointing at unknown nodes, and ETO companies
    whose name matches a graph node but which are neither mapped nor skipped."""
    if not (eto_dir / "providers.csv").exists():
        return []
    errors = []
    nodes = _rows(seed_dir / "nodes.csv")
    node_ids = {n["id"] for n in nodes}
    _, providers, _ = load_eto(eto_dir)
    for i, r in enumerate(load_map(seed_dir), start=2):
        if r["action"] not in ("map", "skip"):
            errors.append(f"eto_providers.csv:{i}: action must be map or skip")
        if not r["reason"].strip():
            errors.append(f"eto_providers.csv:{i}: reason is required")
        if r["eto_provider_id"] not in providers:
            errors.append(f"eto_providers.csv:{i}: unknown ETO provider {r['eto_provider_id']!r}")
        if r["action"] == "map" and r["node_id"] not in node_ids:
            errors.append(f"eto_providers.csv:{i}: unknown node {r['node_id']!r}")

    to_node, skipped, _ = provider_nodes(seed_dir)
    names = {}
    for n in nodes:
        for alias in [n["name"], *filter(None, n.get("aliases", "").split(";"))]:
            names.setdefault(_key(alias), n["id"])
    for pid, p in providers.items():
        if p["provider_type"] == "country" or pid in to_node or pid in skipped:
            continue
        for alias in [p["provider_name"], *filter(None, p.get("alias", "").split(";"))]:
            if _key(alias) in names:
                errors.append(
                    f"ETO provider {pid} {p['provider_name']!r} matches node {names[_key(alias)]!r} by name; "
                    "set eto_provider_id in nodes.csv or add a row to eto_providers.csv"
                )
                break
    return errors


def market(seed_dir: Path = paths.SEED_DIR, eto_dir: Path = ETO_DIR) -> dict:
    """Market positions for graph nodes, plus the catalogue of ETO companies and inputs."""
    inputs, providers, provision = load_eto(eto_dir)
    stages = input_stages(eto_dir)
    to_node, skipped, overrides = provider_nodes(seed_dir)
    node_ids = {r["id"] for r in _rows(seed_dir / "nodes.csv")}
    concentration = {r["eto_id"]: r for r in input_concentration(eto_dir)}

    def owner(pid: str, iid: str) -> str | None:
        return overrides.get((pid, iid)) or to_node.get(pid)

    # Market company ids: slug of the ETO name, kept clear of graph node ids.
    company_id: dict[str, str] = {}
    taken = set(node_ids)
    for pid, p in sorted(providers.items(), key=lambda kv: int(kv[0][1:])):
        if p["provider_type"] == "country" or pid in to_node or pid in skipped or _is_other(p["provider_name"]):
            continue
        cid = slug(p["provider_name"])
        while cid in taken:
            cid += "-eto"
        taken.add(cid)
        company_id[pid] = cid

    sources: list[str] = []

    def source_index(text: str) -> int | None:
        """Positions refer to their source citation by index into `sources`."""
        if not text:
            return None
        if text not in sources:
            sources.append(text)
        return sources.index(text)

    node_positions: dict[str, list[dict]] = defaultdict(list)
    company_positions: dict[str, list[dict]] = defaultdict(list)
    suppliers: dict[str, list[dict]] = defaultdict(list)
    for r in provision:
        pid, iid = r["provider_id"], r["provided_id"]
        p = providers[pid]
        if p["provider_type"] == "country" or iid not in inputs or _is_other(p["provider_name"]):
            continue  # "various companies" is ETO's unattributed remainder, not a supplier
        share = round(float(r["share_provided"]) / 100, 4) if r["share_provided"] else None
        position = {"input": iid, "share": share, "year": r["year"] or None, "source": source_index(r.get("source", ""))}
        target = owner(pid, iid)
        ref = {"name": p["provider_name"], "share": share}
        if target:
            node_positions[target].append(position)
            ref["node"] = target
        elif pid in company_id:
            company_positions[company_id[pid]].append(position)
            ref["company"] = company_id[pid]
        suppliers[iid].append(ref)

    companies = []
    for pid, cid in company_id.items():
        p = providers[pid]
        positions = company_positions.get(cid, [])
        if not positions:
            continue  # listed by ETO but with no market positions: nothing to show
        votes = Counter(stages.get(pos["input"]) for pos in positions if stages.get(pos["input"]))
        stage = min(votes, key=lambda s: (-votes[s], STAGE_ORDER.index(s))) if votes else None
        companies.append({
            "id": cid,
            "name": p["provider_name"],
            "eto_provider_id": pid,
            "hq_country": ISO3_TO_ISO2.get(p["country"]),
            "aliases": [a for a in p.get("alias", "").split(";") if a],
            "stage": stage,
            "positions": sorted(positions, key=lambda x: -(x["share"] or 0)),
        })

    children: dict[str, list[str]] = defaultdict(list)
    seq = _rows(eto_dir / "sequence.csv")
    parent = {r["input_id"]: r["is_type_of_id"] for r in seq if r["is_type_of_id"]}
    for c, par in parent.items():
        children[par].append(c)
    goes_into = defaultdict(set)
    for r in seq:
        if r["goes_into_id"]:
            goes_into[r["input_id"]].add(r["goes_into_id"])
    curated = defaultdict(list)
    for r in _rows(seed_dir / "inputs.csv"):
        if r.get("eto_id"):
            curated[r["eto_id"]].append(r["id"])

    catalogue = []
    for iid, inp in inputs.items():
        conc = concentration.get(iid, {})
        catalogue.append({
            "id": iid,
            "name": inp["input_name"],
            "type": inp["type"],
            "stage": stages.get(iid),
            "description": inp.get("description", ""),
            "market_size": inp.get("market_share_chart_global_market_size_info") or None,
            "source": inp.get("market_share_chart_source") or None,
            "parent": parent.get(iid),
            "children": sorted(children.get(iid, [])),
            "goes_into": sorted(goes_into.get(iid, [])),
            "graph_inputs": curated.get(iid, []),
            "suppliers": sorted(suppliers.get(iid, []), key=lambda s: (-(s["share"] or 0), s["name"])),
            "country_shares": conc.get("country_shares", {}),
            "company_hhi": conc.get("company_hhi"),
            "year": conc.get("year"),
        })

    return {
        "node_positions": {k: sorted(v, key=lambda x: -(x["share"] or 0)) for k, v in node_positions.items()},
        "companies": sorted(companies, key=lambda c: c["name"].lower()),
        "inputs": sorted(catalogue, key=lambda i: int(i["id"][1:])),
        "skipped": [{"eto_provider_id": r["eto_provider_id"], "name": providers[r["eto_provider_id"]]["provider_name"], "reason": r["reason"]}
                    for r in load_map(seed_dir) if r["action"] == "skip" and r["eto_provider_id"] in providers],
        "sources": sources,
        "citation": "Emerging Technology Observatory Semiconductor Supply Chain Dataset",
        "license": "CC BY-NC 4.0",
    }
