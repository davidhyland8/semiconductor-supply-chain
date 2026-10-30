import { expect, it } from "vitest";
import { parseHash, toHash } from "./urlState";

it("round-trips view, selection and scenario", () => {
  const state = {
    view: "map" as const,
    sel: { kind: "node" as const, id: "acme-litho" },
    scenario: { companies: ["acme-litho"], countries: ["JP", "TW"] },
  };
  const hash = toHash(state);
  expect(hash).toBe("#view=map&sel=node:acme-litho&off=companies:acme-litho,countries:JP,countries:TW");
  expect(parseHash(hash)).toEqual(state);
});

it("omits defaults and ignores unknown values", () => {
  expect(toHash({ view: "layered", scenario: {} })).toBe("");
  expect(parseHash("#view=nope&sel=thing:x&off=planets:mars,stages:equipment")).toEqual({
    scenario: { stages: ["equipment"] },
  });
});

it("keeps colons inside ids", () => {
  expect(parseHash("#sel=edge:a:b")).toEqual({ sel: { kind: "edge", id: "a:b" }, scenario: {} });
});
