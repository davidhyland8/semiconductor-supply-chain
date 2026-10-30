// Display names and plain-English explanations of scenario rules.

import type { Cause, NodeState } from "./scenario/types";

// Left-to-right order of the layered view, following the direction of supply.
export const STAGES = [
  { id: "design_tools_ip", label: "Design tools & IP", color: "#7c3aed" },
  { id: "equipment", label: "Equipment", color: "#2563eb" },
  { id: "materials", label: "Materials", color: "#0891b2" },
  { id: "fabrication", label: "Fabrication", color: "#059669" },
  { id: "packaging_test", label: "Packaging & test", color: "#ca8a04" },
  { id: "chip_design", label: "Chip design", color: "#db2777" },
  { id: "assembly_end_products", label: "Assembly & end products", color: "#64748b" },
] as const;

export const stageLabel = (id: string) => STAGES.find((s) => s.id === id)?.label ?? id;
export const stageColor = (id: string) => STAGES.find((s) => s.id === id)?.color ?? "#94a3b8";

const regions = new Intl.DisplayNames(["en"], { type: "region" });
export function countryName(code: string): string {
  try {
    return regions.of(code) ?? code;
  } catch {
    return code;
  }
}

export const STATE_LABEL: Record<NodeState, string> = {
  offline: "Offline",
  full: "Fully impacted",
  partial: "Partially impacted",
  ok: "Not impacted",
};

export function explainCause(c: Cause, name: (id: string) => string, inputName: (id: string) => string): string {
  const list = (ids: string[] = []) => ids.map(name).join(", ");
  const input = c.input ? inputName(c.input) : "";
  const countries = (c.countries ?? []).map(countryName).join(", ");
  switch (c.rule) {
    case "company_offline":
      return "Taken offline in this scenario.";
    case "stage_offline":
      return `Its whole stage (${stageLabel(c.stage ?? "")}) is offline.`;
    case "country_offline":
      return `All, the primary, or most of its recorded production is in ${countries}.`;
    case "country_offline_hq_fallback":
      return `No production locations recorded, so its headquarters country is used: ${countries}.`;
    case "country_partial":
      return `Some of its recorded production is in ${countries}.`;
    case "all_suppliers_lost":
      return `Lost every known supplier of ${input}: ${list(c.lost)}.`;
    case "alternatives_unrecorded":
      return `Lost every known supplier of ${input} (${list(c.lost)}), but the evidence says alternative suppliers exist outside this graph.`;
    case "sole_source":
      return `Lost a sole-source supplier of ${input}: ${list(c.lost)}.`;
    case "weight_threshold":
      return `Lost suppliers covering at least half of its ${input}: ${list(c.lost)}.`;
    case "some_suppliers_lost":
      return `Lost some suppliers of ${input} (${list(c.lost)}); others remain.`;
    case "degraded_supplier":
      return `Suppliers of ${input} are partially impacted: ${list(c.degraded)}.`;
  }
}
