"""Scenario propagation: take companies, stages or countries offline and work out
which nodes are fully or partially impacted. Rules are in docs/methodology.md.

Mirrors web/src/scenario/propagate.ts; both are tested against
tests/fixtures/scenarios/*.json, so change them together.
"""

from collections import defaultdict
from dataclasses import dataclass, field

OK, PARTIAL, FULL, OFFLINE = "ok", "partial", "full", "offline"
RANK = {OK: 0, PARTIAL: 1, FULL: 2, OFFLINE: 3}
LOST = {FULL, OFFLINE}
MAJORITY = 0.5


@dataclass
class Scenario:
    companies: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)


@dataclass
class Result:
    state: dict[str, str]
    causes: dict[str, list[dict]]

    def impacted(self) -> dict[str, str]:
        return {n: s for n, s in self.state.items() if s != OK}


def _country_seed(node: dict, countries: set[str]) -> tuple[str, str] | None:
    """(state, rule) for a node in a country scenario, or None if unaffected."""
    sites = node.get("production_countries") or []
    fallback = not sites
    if fallback:
        if not node.get("hq_country"):
            return None  # product categories have no location
        sites = [{"country": node["hq_country"]}]
    hit = [s for s in sites if s["country"] in countries]
    if not hit:
        return None
    if (
        len(hit) == len(sites)
        or any(s.get("primary") for s in hit)
        or sum(s.get("share", 0) for s in hit) >= MAJORITY
    ):
        return OFFLINE, "country_offline_hq_fallback" if fallback else "country_offline"
    return PARTIAL, "country_partial"


def seed(nodes: list[dict], scenario: Scenario) -> tuple[dict[str, str], dict[str, list[dict]]]:
    state = {n["id"]: OK for n in nodes}
    causes: dict[str, list[dict]] = defaultdict(list)
    companies, stages, countries = set(scenario.companies), set(scenario.stages), set(scenario.countries)

    def mark(node_id: str, new: str, cause: dict) -> None:
        if RANK[new] > RANK[state[node_id]]:
            state[node_id] = new
        causes[node_id].append(cause)

    for node in nodes:
        nid = node["id"]
        if nid in companies:
            mark(nid, OFFLINE, {"rule": "company_offline"})
        if node.get("stage") in stages:
            mark(nid, OFFLINE, {"rule": "stage_offline", "stage": node["stage"]})
        if countries:
            hit = _country_seed(node, countries)
            if hit:
                mark(nid, hit[0], {"rule": hit[1], "countries": sorted(countries)})
    return state, causes


def _assess_input(edges: list[dict], state: dict[str, str]) -> tuple[str, str, list[str], list[str]] | None:
    """(state, rule, lost, degraded) for one buyer input, or None if unaffected."""
    lost = [e for e in edges if state.get(e["supplier"]) in LOST]
    degraded = [e["supplier"] for e in edges if state.get(e["supplier"]) == PARTIAL]
    lost_ids = [e["supplier"] for e in lost]
    if lost:
        if len(lost) == len(edges):
            if all(e.get("has_alternatives") == "yes" for e in lost):
                return PARTIAL, "alternatives_unrecorded", lost_ids, degraded
            return FULL, "all_suppliers_lost", lost_ids, degraded
        if any(e.get("has_alternatives") == "no" for e in lost):
            return FULL, "sole_source", lost_ids, degraded
        lost_weight = sum(
            (e.get("weight") or {}).get("value", 0)
            for e in lost
            if (e.get("weight") or {}).get("metric") == "share_of_buyer_input"
        )
        if lost_weight >= MAJORITY:
            return FULL, "weight_threshold", lost_ids, degraded
        return PARTIAL, "some_suppliers_lost", lost_ids, degraded
    if degraded:
        return PARTIAL, "degraded_supplier", [], degraded
    return None


def propagate(nodes: list[dict], edges: list[dict], scenario: Scenario) -> Result:
    state, causes = seed(nodes, scenario)
    seed_causes = {n: list(c) for n, c in causes.items()}
    by_buyer: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for e in edges:
        if e["buyer"] in state and e["supplier"] in state:
            by_buyer[e["buyer"]][e["input"]].append(e)

    # States only get worse, so this reaches a fixed point even with cycles.
    changed = True
    while changed:
        changed = False
        for buyer, inputs in by_buyer.items():
            if state[buyer] == OFFLINE:
                continue
            worst = state[buyer]
            input_causes = []
            for input_id in sorted(inputs):
                assessed = _assess_input(inputs[input_id], state)
                if assessed is None:
                    continue
                new, rule, lost, degraded = assessed
                input_causes.append({"rule": rule, "input": input_id, "lost": lost, "degraded": degraded})
                if RANK[new] > RANK[worst]:
                    worst = new
            causes[buyer] = seed_causes.get(buyer, []) + input_causes
            if worst != state[buyer]:
                state[buyer] = worst
                changed = True

    return Result(state=state, causes={n: c for n, c in causes.items() if c and state[n] != OK})
