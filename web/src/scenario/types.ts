// Shapes follow schema/node.schema.json and schema/edge.schema.json.

export type Alternatives = "yes" | "no" | "unknown";

export interface ProductionCountry {
  country: string;
  share?: number;
  primary?: boolean;
}

export interface GraphNode {
  id: string;
  stage?: string;
  kind?: "company" | "product_category";
  hq_country?: string;
  production_countries?: ProductionCountry[];
}

export interface Weight {
  value: number;
  metric: "share_of_buyer_input" | "share_of_supplier_revenue";
  basis: string;
}

export interface GraphEdge {
  supplier: string;
  buyer: string;
  input: string;
  has_alternatives: Alternatives;
  weight?: Weight | null;
}

export interface Scenario {
  companies?: string[];
  stages?: string[];
  countries?: string[];
}

export type NodeState = "ok" | "partial" | "full" | "offline";

export type Rule =
  | "company_offline"
  | "stage_offline"
  | "country_offline"
  | "country_offline_hq_fallback"
  | "country_partial"
  | "all_suppliers_lost"
  | "alternatives_unrecorded"
  | "sole_source"
  | "weight_threshold"
  | "some_suppliers_lost"
  | "degraded_supplier";

export interface Cause {
  rule: Rule;
  stage?: string;
  countries?: string[];
  input?: string;
  lost?: string[];
  degraded?: string[];
}

export interface ScenarioResult {
  state: Record<string, NodeState>;
  causes: Record<string, Cause[]>;
}
