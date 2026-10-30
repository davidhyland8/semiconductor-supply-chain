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
  market_positions?: MarketPosition[];
}

// ETO market data (pipeline/src/scg/eto.py): what a company sells and its share.
export interface MarketPosition {
  input: string; // ETO input id
  share: number | null;
  year: string | null;
  source: number | null; // index into Market.sources
}

export interface MarketCompany {
  id: string;
  name: string;
  eto_provider_id: string;
  hq_country?: string;
  aliases: string[];
  stage: string | null;
  positions: MarketPosition[];
}

export interface EtoSupplier {
  name: string;
  share: number | null;
  node?: string;
  company?: string;
}

export interface EtoInput {
  id: string;
  name: string;
  type: string;
  stage: string | null;
  description: string;
  market_size: string | null;
  source: string | null;
  parent: string | null;
  children: string[];
  goes_into: string[];
  graph_inputs: string[];
  suppliers: EtoSupplier[];
  country_shares: Record<string, number>;
  company_hhi: number | null;
  year: string | null;
}

export interface Market {
  companies: MarketCompany[];
  inputs: EtoInput[];
  sources: string[];
  skipped: { eto_provider_id: string; name: string; reason: string }[];
  citation: string;
  license: string;
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
  eto_id?: string;
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
  shares: Record<string, number>; // ISO alpha-2, or "EU" for the bloc
  hhi?: number;
  inputs: string[];
  years?: string[];
  basis?: string;
  other_share?: number; // ETO's unallocated "various countries" bucket
  source?: string;
  note?: string;
}

export interface GraphDoc {
  version: number;
  built: string;
  nodes: Node[];
  edges: Edge[];
  inputs: Input[];
  groups: Group[];
  market: Market;
  analysis: {
    criticality: { companies: Impact[]; stages: Impact[]; countries: Impact[] };
    stage_country_shares: Record<string, StageShares>;
  };
}

// "@graph" is aliased to the latest data/build/graph.v<N>.json in vite.config.ts.
import graphUrl from "@graph?url";

export async function loadLatest(): Promise<GraphDoc> {
  const url = graphUrl;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  return res.json();
}
