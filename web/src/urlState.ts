// App state in the URL hash, so a view, selection and scenario can be shared:
// #view=map&sel=node:asml&off=companies:asml,countries:JP

import type { Scenario } from "./scenario/types";

export type Mode = "layered" | "force" | "map" | "methodology";
export type SelKind = "node" | "edge" | "country" | "market" | "input";

export interface UrlState {
  view?: Mode;
  sel?: { kind: SelKind; id: string };
  scenario: Scenario;
}

const MODES: Mode[] = ["layered", "force", "map", "methodology"];
const KINDS: SelKind[] = ["node", "edge", "country", "market", "input"];
const SCENARIO_KEYS = ["companies", "stages", "countries"] as const;

export function parseHash(hash: string): UrlState {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const state: UrlState = { scenario: {} };
  const view = params.get("view");
  if (view && (MODES as string[]).includes(view)) state.view = view as Mode;
  const sel = params.get("sel");
  if (sel) {
    const i = sel.indexOf(":");
    const kind = sel.slice(0, i) as SelKind;
    if (i > 0 && KINDS.includes(kind)) state.sel = { kind, id: sel.slice(i + 1) };
  }
  for (const item of (params.get("off") ?? "").split(",").filter(Boolean)) {
    const i = item.indexOf(":");
    const key = item.slice(0, i) as (typeof SCENARIO_KEYS)[number];
    if (i > 0 && SCENARIO_KEYS.includes(key)) (state.scenario[key] ??= []).push(item.slice(i + 1));
  }
  return state;
}

export function toHash(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.view && state.view !== "layered") params.set("view", state.view);
  if (state.sel) params.set("sel", `${state.sel.kind}:${state.sel.id}`);
  const off = SCENARIO_KEYS.flatMap((k) => (state.scenario[k] ?? []).map((id) => `${k}:${id}`));
  if (off.length) params.set("off", off.join(","));
  const s = params.toString().replace(/%3A/g, ":").replace(/%2C/g, ",");
  return s ? `#${s}` : "";
}
