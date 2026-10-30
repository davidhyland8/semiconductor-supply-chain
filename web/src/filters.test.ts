import { describe, expect, it } from "vitest";
import type { Edge, Node, Strength } from "./data";
import { visibleElements, type Filters } from "./filters";

const node = (id: string, stage: string, extra: Partial<Node> = {}): Node => ({
  id,
  name: id,
  kind: "company",
  stage,
  upstream_count: 0,
  downstream_count: 0,
  ...extra,
});

const edge = (supplier: string, buyer: string, strength: Strength): Edge => ({
  id: `${supplier}-${buyer}`,
  supplier,
  buyer,
  input: "x",
  has_alternatives: "unknown",
  evidence: [],
  strength,
});

const nodes = [
  node("toolco", "equipment", { hq_country: "NL" }),
  node("fab", "fabrication", { hq_country: "US", production_countries: [{ country: "TW" }] }),
  node("phones", "assembly_end_products", { kind: "product_category" }),
];
const edges = [edge("toolco", "fab", "disclosed"), edge("fab", "phones", "inferred")];

const all = (): Filters => ({
  stages: new Set(["equipment", "fabrication", "assembly_end_products"]),
  countries: new Set(),
  strengths: new Set<Strength>(["disclosed", "reported", "inferred"]),
});

describe("visibleElements", () => {
  it("shows everything by default", () => {
    const v = visibleElements(nodes, edges, all());
    expect(v.nodeIds.size).toBe(3);
    expect(v.edgeIds.size).toBe(2);
  });

  it("hides a stage and the edges touching it", () => {
    const f = all();
    f.stages.delete("equipment");
    const v = visibleElements(nodes, edges, f);
    expect([...v.nodeIds].sort()).toEqual(["fab", "phones"]);
    expect([...v.edgeIds]).toEqual(["fab-phones"]);
  });

  it("matches countries on production as well as HQ, and keeps end markets", () => {
    const f = all();
    f.countries.add("TW");
    expect([...visibleElements(nodes, edges, f).nodeIds].sort()).toEqual(["fab", "phones"]);
  });

  it("filters edges by evidence strength", () => {
    const f = all();
    f.strengths.delete("inferred");
    expect([...visibleElements(nodes, edges, f).edgeIds]).toEqual(["toolco-fab"]);
  });
});
