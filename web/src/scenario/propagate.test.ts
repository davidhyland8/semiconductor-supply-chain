// Runs the shared scenario fixtures (also run by pipeline/tests/test_scenario.py).

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { propagate } from "./propagate";
import type { GraphEdge, GraphNode, NodeState, Scenario } from "./types";

interface Case {
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  scenario: Scenario;
  expected: Record<string, NodeState>;
  expected_rules?: Record<string, string[]>;
}

const FIXTURES = join(import.meta.dirname, "../../../tests/fixtures/scenarios");

for (const file of readdirSync(FIXTURES).filter((f) => f.endsWith(".json")).sort()) {
  const { cases } = JSON.parse(readFileSync(join(FIXTURES, file), "utf8")) as { cases: Case[] };
  describe(file, () => {
    for (const c of cases) {
      it(c.name, () => {
        const result = propagate(c.nodes, c.edges, c.scenario);
        const expected = Object.fromEntries(c.nodes.map((n) => [n.id, c.expected[n.id] ?? "ok"]));
        expect(result.state).toEqual(expected);
        for (const [id, rules] of Object.entries(c.expected_rules ?? {})) {
          const found = new Set((result.causes[id] ?? []).map((x) => x.rule));
          for (const r of rules) expect(found, `${id} should have rule ${r}`).toContain(r);
        }
      });
    }
  });
}

// Parity on real data: the build stores the Python engine's result for every
// single company, stage and country scenario; the TS engine must reproduce them.
const BUILD = join(import.meta.dirname, "../../../data/build");
const latest = readdirSync(BUILD)
  .filter((f) => /^graph\.v\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/\d+/)![0]) - Number(b.match(/\d+/)![0]))
  .pop();

describe.runIf(latest)("parity with the Python build", () => {
  const graph = JSON.parse(readFileSync(join(BUILD, latest!), "utf8"));
  const kinds = { companies: "companies", stages: "stages", countries: "countries" } as const;
  for (const [kind, key] of Object.entries(kinds)) {
    it(`matches every single-${kind.slice(0, -1)} scenario`, () => {
      for (const row of graph.analysis.criticality[kind]) {
        const { state } = propagate(graph.nodes, graph.edges, { [key]: [row.id] });
        const by = (s: NodeState) => Object.keys(state).filter((n) => state[n] === s).sort();
        const offline = by("offline").filter((n) => !(kind === "companies" && n === row.id));
        expect({ id: row.id, offline, full: by("full"), partial: by("partial") }).toEqual({
          id: row.id,
          offline: row.offline,
          full: row.full,
          partial: row.partial,
        });
      }
    });
  }
});

it("causes name the lost suppliers", () => {
  const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }];
  const edges: GraphEdge[] = [
    { supplier: "a", buyer: "c", input: "x", has_alternatives: "unknown" },
    { supplier: "b", buyer: "c", input: "x", has_alternatives: "unknown" },
  ];
  const result = propagate(nodes, edges, { companies: ["a"] });
  expect(result.causes.c).toEqual([{ rule: "some_suppliers_lost", input: "x", lost: ["a"], degraded: [] }]);
  expect(result.causes.b).toBeUndefined();
});
