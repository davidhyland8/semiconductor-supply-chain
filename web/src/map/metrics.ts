// Per-country figures for the map and the country panel.

import type { GraphDoc, Impact, Node, StageShares } from "../data";
import type { NodeState, ScenarioResult } from "../scenario/types";
import { EU_MEMBERS } from "./countries";

export interface CountryShare {
  value: number;
  viaEU: boolean; // the figure is the EU bloc's, not this country's own
}

/** A country's share of a stage: its own figure, else the EU bloc's for EU members. */
export function countryShare(code: string, stage: StageShares | undefined): CountryShare | null {
  const shares = stage?.shares ?? {};
  if (code in shares) return { value: shares[code]!, viaEU: false };
  if (EU_MEMBERS.has(code) && "EU" in shares) return { value: shares.EU!, viaEU: true };
  return null;
}

export const hqCompanies = (nodes: Node[], code: string) =>
  nodes.filter((n) => n.kind === "company" && n.hq_country === code);

/** Companies headquartered elsewhere with recorded production in this country. */
export const producersIn = (nodes: Node[], code: string) =>
  nodes.filter((n) => n.hq_country !== code && (n.production_countries ?? []).some((p) => p.country === code));

export interface CountryImpact {
  total: number;
  counts: Record<NodeState, number>;
  score: number; // 0..1: (offline + full + ½ partial) / companies headquartered here
}

export function scenarioImpact(nodes: Node[], result: ScenarioResult, code: string): CountryImpact | null {
  const companies = hqCompanies(nodes, code);
  if (companies.length === 0) return null;
  const counts: Record<NodeState, number> = { ok: 0, partial: 0, full: 0, offline: 0 };
  for (const n of companies) counts[result.state[n.id] ?? "ok"]++;
  const score = (counts.offline + counts.full + 0.5 * counts.partial) / companies.length;
  return { total: companies.length, counts, score };
}

export const countryCriticality = (doc: GraphDoc, code: string): Impact | undefined =>
  doc.analysis.criticality.countries.find((c) => c.id === code);

/** Every country code that appears anywhere: HQs, production, stage shares. */
export function allCountries(doc: GraphDoc): string[] {
  const out = new Set<string>();
  for (const n of doc.nodes) {
    if (n.hq_country) out.add(n.hq_country);
    for (const p of n.production_countries ?? []) out.add(p.country);
  }
  for (const s of Object.values(doc.analysis.stage_country_shares)) for (const c of Object.keys(s.shares)) out.add(c);
  out.delete("EU");
  return [...out].sort();
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Colour at t in [0, 1] along evenly spaced colour stops. */
export function ramp(stops: string[], t: number): string {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const [a, b] = [hexToRgb(stops[i]!), hexToRgb(stops[i + 1]!)];
  const f = x - i;
  const mix = a.map((v, k) => Math.round(v + (b[k]! - v) * f));
  return `#${mix.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export const SHARE_RAMP = ["#e0f2fe", "#7dd3fc", "#0284c7", "#075985", "#0c2d48"];
export const IMPACT_RAMP = ["#fef3c7", "#fbbf24", "#ef4444", "#991b1b"];
