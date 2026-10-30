// Scenario propagation: take companies, stages or countries offline and work out
// which nodes are fully or partially impacted. Rules are in docs/methodology.md.
//
// Mirrors pipeline/src/scg/analysis/scenario.py; both are tested against
// tests/fixtures/scenarios/*.json, so change them together.

import type { Cause, GraphEdge, GraphNode, NodeState, Rule, Scenario, ScenarioResult } from "./types";

const RANK: Record<NodeState, number> = { ok: 0, partial: 1, full: 2, offline: 3 };
const MAJORITY = 0.5;

const isLost = (s: NodeState | undefined) => s === "full" || s === "offline";

function countrySeed(node: GraphNode, countries: Set<string>): [NodeState, Rule] | null {
  let sites = node.production_countries ?? [];
  const fallback = sites.length === 0;
  if (fallback) {
    if (!node.hq_country) return null; // product categories have no location
    sites = [{ country: node.hq_country }];
  }
  const hit = sites.filter((s) => countries.has(s.country));
  if (hit.length === 0) return null;
  const share = hit.reduce((sum, s) => sum + (s.share ?? 0), 0);
  if (hit.length === sites.length || hit.some((s) => s.primary) || share >= MAJORITY) {
    return ["offline", fallback ? "country_offline_hq_fallback" : "country_offline"];
  }
  return ["partial", "country_partial"];
}

export function seed(nodes: GraphNode[], scenario: Scenario) {
  const state: Record<string, NodeState> = {};
  const causes: Record<string, Cause[]> = {};
  for (const n of nodes) state[n.id] = "ok";
  const companies = new Set(scenario.companies ?? []);
  const stages = new Set(scenario.stages ?? []);
  const countries = new Set(scenario.countries ?? []);

  const mark = (id: string, next: NodeState, cause: Cause) => {
    if (RANK[next] > RANK[state[id]!]) state[id] = next;
    (causes[id] ??= []).push(cause);
  };

  for (const node of nodes) {
    if (companies.has(node.id)) mark(node.id, "offline", { rule: "company_offline" });
    if (node.stage && stages.has(node.stage)) mark(node.id, "offline", { rule: "stage_offline", stage: node.stage });
    if (countries.size > 0) {
      const hit = countrySeed(node, countries);
      if (hit) mark(node.id, hit[0], { rule: hit[1], countries: [...countries].sort() });
    }
  }
  return { state, causes };
}

function assessInput(edges: GraphEdge[], state: Record<string, NodeState>): [NodeState, Cause] | null {
  const lost = edges.filter((e) => isLost(state[e.supplier]));
  const degraded = edges.filter((e) => state[e.supplier] === "partial").map((e) => e.supplier);
  const lostIds = lost.map((e) => e.supplier);
  const cause = (rule: Rule): Cause => ({ rule, input: edges[0]!.input, lost: lostIds, degraded });

  if (lost.length > 0) {
    if (lost.length === edges.length) {
      if (lost.every((e) => e.has_alternatives === "yes")) return ["partial", cause("alternatives_unrecorded")];
      return ["full", cause("all_suppliers_lost")];
    }
    if (lost.some((e) => e.has_alternatives === "no")) return ["full", cause("sole_source")];
    const lostWeight = lost
      .filter((e) => e.weight?.metric === "share_of_buyer_input")
      .reduce((sum, e) => sum + (e.weight?.value ?? 0), 0);
    if (lostWeight >= MAJORITY) return ["full", cause("weight_threshold")];
    return ["partial", cause("some_suppliers_lost")];
  }
  if (degraded.length > 0) return ["partial", { ...cause("degraded_supplier"), lost: [] }];
  return null;
}

export function propagate(nodes: GraphNode[], edges: GraphEdge[], scenario: Scenario): ScenarioResult {
  const { state, causes } = seed(nodes, scenario);
  const seedCauses: Record<string, Cause[]> = Object.fromEntries(
    Object.entries(causes).map(([id, c]) => [id, [...c]]),
  );

  const byBuyer = new Map<string, Map<string, GraphEdge[]>>();
  for (const e of edges) {
    if (!(e.buyer in state) || !(e.supplier in state)) continue;
    const inputs = byBuyer.get(e.buyer) ?? new Map<string, GraphEdge[]>();
    inputs.set(e.input, [...(inputs.get(e.input) ?? []), e]);
    byBuyer.set(e.buyer, inputs);
  }

  // States only get worse, so this reaches a fixed point even with cycles.
  let changed = true;
  while (changed) {
    changed = false;
    for (const [buyer, inputs] of byBuyer) {
      if (state[buyer] === "offline") continue;
      let worst: NodeState = state[buyer]!;
      const inputCauses: Cause[] = [];
      for (const input of [...inputs.keys()].sort()) {
        const assessed = assessInput(inputs.get(input)!, state);
        if (!assessed) continue;
        const [next, cause] = assessed;
        inputCauses.push(cause);
        if (RANK[next] > RANK[worst]) worst = next;
      }
      causes[buyer] = [...(seedCauses[buyer] ?? []), ...inputCauses];
      if (worst !== state[buyer]) {
        state[buyer] = worst;
        changed = true;
      }
    }
  }

  const impactedCauses: Record<string, Cause[]> = {};
  for (const [id, c] of Object.entries(causes)) {
    if (c.length > 0 && state[id] !== "ok") impactedCauses[id] = c;
  }
  return { state, causes: impactedCauses };
}
