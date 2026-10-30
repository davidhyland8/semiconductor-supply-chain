// Search across graph companies, ETO market companies and ETO inputs.

import type { GraphDoc } from "./data";

export type Target = { kind: "node" | "market" | "input"; id: string };

export interface Entry extends Target {
  label: string; // shown in the suggestion list; unique
  keys: string[]; // lower-case strings matched against the query
}

const SUFFIX: Record<Target["kind"], string> = { node: "", market: " (ETO company)", input: " (input)" };

export function searchEntries(doc: GraphDoc): Entry[] {
  const entries: Entry[] = [
    ...doc.nodes.map((n) => ({ kind: "node" as const, id: n.id, name: n.name, keys: [n.name, ...(n.aliases ?? []), n.ticker ?? ""] })),
    ...doc.market.companies.map((c) => ({ kind: "market" as const, id: c.id, name: c.name, keys: [c.name, ...c.aliases] })),
    ...doc.market.inputs.map((i) => ({ kind: "input" as const, id: i.id, name: i.name, keys: [i.name] })),
  ].map((e) => ({
    kind: e.kind,
    id: e.id,
    label: e.name + SUFFIX[e.kind],
    keys: e.keys.filter(Boolean).map((k) => k.toLowerCase()),
  }));
  return entries;
}

/** Exact label, then exact name or alias, then substring; graph companies first at each step. */
export function find(entries: Entry[], query: string): Target | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const hit =
    entries.find((e) => e.label.toLowerCase() === q) ??
    entries.find((e) => e.keys.includes(q)) ??
    entries.find((e) => e.keys.some((k) => k.includes(q)));
  return hit ? { kind: hit.kind, id: hit.id } : null;
}
