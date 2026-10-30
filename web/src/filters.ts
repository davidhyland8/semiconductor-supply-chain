// Display filters. They only hide elements: scenarios always run on the full graph.

import type { Edge, Node, Strength } from "./data";

export interface Filters {
  stages: Set<string>;
  countries: Set<string>; // empty = all countries
  strengths: Set<Strength>;
}

// HQ plus recorded production countries.
export function nodeCountries(n: Node): string[] {
  const out = new Set<string>();
  if (n.hq_country) out.add(n.hq_country);
  for (const p of n.production_countries ?? []) out.add(p.country);
  return [...out].sort();
}

export function visibleElements(nodes: Node[], edges: Edge[], f: Filters) {
  const nodeIds = new Set(
    nodes
      .filter((n) => f.stages.has(n.stage))
      .filter(
        (n) =>
          f.countries.size === 0 ||
          n.kind === "product_category" || // end markets have no location; keep them
          nodeCountries(n).some((c) => f.countries.has(c)),
      )
      .map((n) => n.id),
  );
  const edgeIds = new Set(
    edges
      .filter((e) => nodeIds.has(e.supplier) && nodeIds.has(e.buyer) && f.strengths.has(e.strength))
      .map((e) => e.id),
  );
  return { nodeIds, edgeIds };
}
