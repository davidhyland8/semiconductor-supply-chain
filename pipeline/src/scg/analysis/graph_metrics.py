"""Chokepoints and criticality on the evidenced graph."""

from collections import defaultdict

from scg.analysis.scenario import FULL, OFFLINE, PARTIAL, Scenario, propagate


def chokepoints(edges: list[dict]) -> list[dict]:
    """Buyer inputs with a single known supplier or a stated sole source, grouped by supplier.

    Based on known suppliers only: an input with one recorded supplier may have
    unrecorded alternatives, so 'single_known_supplier' is weaker than 'sole_source'.
    """
    by_buyer_input: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in edges:
        by_buyer_input[(e["buyer"], e["input"])].append(e)

    by_supplier: dict[str, list[dict]] = defaultdict(list)
    for (buyer, input_id), es in by_buyer_input.items():
        for e in es:
            if e.get("has_alternatives") == "no":
                reason = "sole_source"
            elif len(es) == 1:
                reason = "single_known_supplier"
            else:
                continue
            by_supplier[e["supplier"]].append({"buyer": buyer, "input": input_id, "reason": reason})

    out = [
        {
            "supplier": s,
            "dependents": sorted(deps, key=lambda d: (d["reason"] != "sole_source", d["buyer"])),
            "sole_source_count": sum(d["reason"] == "sole_source" for d in deps),
        }
        for s, deps in by_supplier.items()
    ]
    return sorted(out, key=lambda r: (-r["sole_source_count"], -len(r["dependents"]), r["supplier"]))


def _impact(nodes, edges, scenario: Scenario) -> dict:
    """Offline nodes other than the named companies count like full impact."""
    result = propagate(nodes, edges, scenario)
    offline = sorted(n for n, s in result.state.items() if s == OFFLINE and n not in scenario.companies)
    full = sorted(n for n, s in result.state.items() if s == FULL)
    partial = sorted(n for n, s in result.state.items() if s == PARTIAL)
    return {
        "offline": offline,
        "full": full,
        "partial": partial,
        "score": len(offline) + len(full) + 0.5 * len(partial),
    }


def criticality(nodes: list[dict], edges: list[dict]) -> dict[str, list[dict]]:
    """Impact of each single company, stage and country going offline, highest first."""
    countries = sorted({
        c["country"] for n in nodes for c in n.get("production_countries") or []
    } | {n["hq_country"] for n in nodes if n.get("hq_country")})
    stages = sorted({n["stage"] for n in nodes if n.get("stage")})
    companies = [n["id"] for n in nodes if n.get("kind", "company") == "company"]

    def ranked(items, make):
        rows = [{"id": i, **_impact(nodes, edges, make(i))} for i in items]
        return sorted(rows, key=lambda r: (-r["score"], r["id"]))

    return {
        "companies": ranked(companies, lambda i: Scenario(companies=[i])),
        "stages": ranked(stages, lambda i: Scenario(stages=[i])),
        "countries": ranked(countries, lambda i: Scenario(countries=[i])),
    }
