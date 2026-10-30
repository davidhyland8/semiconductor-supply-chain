import { describe, expect, it } from "vitest";
import type { Node } from "../data";
import { countryShare, producersIn, ramp, scenarioImpact } from "./metrics";

const node = (id: string, hq: string, production: string[] = []): Node => ({
  id,
  name: id,
  kind: "company",
  stage: "fabrication",
  hq_country: hq,
  production_countries: production.map((country) => ({ country })),
  upstream_count: 0,
  downstream_count: 0,
});

describe("countryShare", () => {
  const stage = { shares: { US: 0.4, EU: 0.1, DE: 0.05 }, inputs: [] };

  it("uses a country's own figure first", () => {
    expect(countryShare("US", stage)).toEqual({ value: 0.4, viaEU: false });
    expect(countryShare("DE", stage)).toEqual({ value: 0.05, viaEU: false });
  });

  it("falls back to the EU bloc for EU members only", () => {
    expect(countryShare("FR", stage)).toEqual({ value: 0.1, viaEU: true });
    expect(countryShare("CH", stage)).toBeNull();
  });

  it("returns null for stages without data", () => {
    expect(countryShare("US", undefined)).toBeNull();
  });
});

describe("scenarioImpact", () => {
  const nodes = [node("a", "XA"), node("b", "XA"), node("c", "XA"), node("d", "XB", ["XA"])];

  it("scores companies headquartered in the country", () => {
    const result = { state: { a: "full", b: "partial", c: "ok", d: "full" } as const, causes: {} };
    const impact = scenarioImpact(nodes, result, "XA")!;
    expect(impact.total).toBe(3);
    expect(impact.counts).toEqual({ ok: 1, partial: 1, full: 1, offline: 0 });
    expect(impact.score).toBeCloseTo(0.5);
  });

  it("is null where no companies are headquartered", () => {
    expect(scenarioImpact(nodes, { state: {}, causes: {} }, "XC")).toBeNull();
  });

  it("lists producers headquartered elsewhere", () => {
    expect(producersIn(nodes, "XA").map((n) => n.id)).toEqual(["d"]);
  });
});

it("ramp interpolates between stops and clamps", () => {
  expect(ramp(["#000000", "#ffffff"], 0)).toBe("#000000");
  expect(ramp(["#000000", "#ffffff"], 0.5)).toBe("#808080");
  expect(ramp(["#000000", "#ffffff"], 2)).toBe("#ffffff");
});
