// Shape of data/build/graph.v<N>.json (written by pipeline/src/scg/build.py)
// and loading of the latest version.

import type { GraphEdge, GraphNode, ProductionCountry } from "./scenario/types";

export type Strength = "disclosed" | "reported" | "inferred";
export const STRENGTHS: Strength[] = ["disclosed", "reported", "inferred"];

export interface Evidence {
  source_id?: string;
  url?: string;
  excerpt?: string;
  locator?: string;
  strength: Strength;
  reasoning?: string;
  source_title: string;
  source_published: string;
}

export interface Production extends ProductionCountry {
  basis?: string;
  source_id?: string;
  as_of?: string;
}

export interface Node extends GraphNode {
  name: string;
  kind: "company" | "product_category";
  stage: string;
  role?: string;
  parent?: string;
  aliases?: string[];
  ticker?: string;
  notes?: string;
  production_countries?: Production[];
  upstream_count: number;
  downstream_count: number;
}

export interface Edge extends GraphEdge {
  id: string;
  as_of?: string;
  notes?: string;
  evidence: Evidence[];
  strength: Strength;
}

export interface Input {
  id: string;
  name: string;
  stage: string;
  description?: string;
}

export interface Group {
  id: string;
  name: string;
  hq_country?: string;
}

export interface Impact {
  id: string;
  offline: string[];
  full: string[];
  partial: string[];
  score: number;
}

export interface StageShares {
  shares: Record<string, number>;
  hhi: number;
  inputs: string[];
  years: string[];
  source: string;
}

export interface GraphDoc {
  version: number;
  built: string;
  nodes: Node[];
  edges: Edge[];
  inputs: Input[];
  groups: Group[];
  analysis: {
    criticality: { companies: Impact[]; stages: Impact[]; countries: Impact[] };
    stage_country_shares: Record<string, StageShares>;
  };
}

const builds = import.meta.glob<string>("../../data/build/graph.v*.json", { query: "?url", import: "default" });

export const versionOf = (path: string) => Number(path.match(/graph\.v(\d+)\.json$/)?.[1] ?? 0);

export async function loadLatest(): Promise<GraphDoc> {
  const latest = Object.keys(builds).sort((a, b) => versionOf(a) - versionOf(b)).pop();
  if (!latest) throw new Error("No graph build found in data/build. Run `uv run scg build`.");
  const url = await builds[latest]!();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  return res.json();
}
