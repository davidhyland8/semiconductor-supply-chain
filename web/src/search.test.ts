import { expect, it } from "vitest";
import type { GraphDoc } from "./data";
import { find, searchEntries } from "./search";

const doc = {
  nodes: [{ id: "lumen", name: "Lumen Litho", aliases: ["Lumen BV"], ticker: "LUM" }],
  market: {
    companies: [{ id: "lumenara", name: "Lumenara", aliases: [] }],
    inputs: [{ id: "N20", name: "EUV tools" }],
  },
} as unknown as GraphDoc;

const entries = searchEntries(doc);

it("labels ETO entries so they are distinguishable in suggestions", () => {
  expect(entries.map((e) => e.label)).toEqual(["Lumen Litho", "Lumenara (ETO company)", "EUV tools (input)"]);
});

it("matches labels, names, aliases, tickers and substrings", () => {
  expect(find(entries, "Lumenara (ETO company)")).toEqual({ kind: "market", id: "lumenara" });
  expect(find(entries, "lumenara")).toEqual({ kind: "market", id: "lumenara" });
  expect(find(entries, "lum")).toEqual({ kind: "node", id: "lumen" }); // ticker, graph first
  expect(find(entries, "lumen")).toEqual({ kind: "node", id: "lumen" }); // substring prefers graph companies
  expect(find(entries, "euv")).toEqual({ kind: "input", id: "N20" });
  expect(find(entries, "  ")).toBeNull();
  expect(find(entries, "nothing")).toBeNull();
});
