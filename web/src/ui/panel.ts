// Details panel for a selected node or edge, with every edge's evidence.

import type { Edge, EtoInput, Evidence, GraphDoc, Impact, MarketCompany, MarketPosition, Node } from "../data";
import { STATE_LABEL, countryName, explainCause, stageColor, stageLabel } from "../labels";
import type { ScenarioResult } from "../scenario/types";
import { esc, pct, safeUrl } from "./html";

export class Index {
  readonly node = new Map<string, Node>();
  readonly edge = new Map<string, Edge>();
  readonly into = new Map<string, Edge[]>();
  readonly out = new Map<string, Edge[]>();
  readonly inputName = new Map<string, string>();
  readonly groupName = new Map<string, string>();
  readonly companyImpact = new Map<string, Impact>();
  readonly etoInput = new Map<string, EtoInput>();
  readonly market = new Map<string, MarketCompany>();
  readonly inputEto = new Map<string, string>(); // graph input id -> ETO input id

  constructor(readonly doc: GraphDoc) {
    for (const n of doc.nodes) this.node.set(n.id, n);
    for (const e of doc.edges) {
      this.edge.set(e.id, e);
      (this.into.get(e.buyer) ?? this.into.set(e.buyer, []).get(e.buyer)!).push(e);
      (this.out.get(e.supplier) ?? this.out.set(e.supplier, []).get(e.supplier)!).push(e);
    }
    for (const i of doc.inputs) this.inputName.set(i.id, i.name);
    for (const g of doc.groups) this.groupName.set(g.id, g.name);
    for (const c of doc.analysis.criticality.companies) this.companyImpact.set(c.id, c);
    for (const i of doc.market.inputs) this.etoInput.set(i.id, i);
    for (const c of doc.market.companies) this.market.set(c.id, c);
    for (const i of doc.inputs) if (i.eto_id && this.etoInput.has(i.eto_id)) this.inputEto.set(i.id, i.eto_id);
  }

  name = (id: string) => this.node.get(id)?.name ?? id;
  input = (id: string) => this.inputName.get(id) ?? id;
}

/** A graph input's name, linked to its ETO market panel when ETO covers it. */
export function inputLink(idx: Index, id: string): string {
  const eto = idx.inputEto.get(id);
  return eto ? `<button class="link" data-eto-input="${esc(eto)}">${esc(idx.input(id))}</button>` : esc(idx.input(id));
}

/** ETO market positions: input, share (or "supplier" when ETO gives no share), year. */
export function positionsHtml(idx: Index, positions: MarketPosition[]): string {
  if (positions.length === 0) return `<p class="muted">None in the ETO dataset.</p>`;
  const rows = positions
    .map((p) => {
      const input = idx.etoInput.get(p.input);
      const share = p.share != null ? pct(p.share) : `<span class="muted">supplier</span>`;
      const source = p.source != null ? idx.doc.market.sources[p.source] : "";
      return `<li title="${esc(source)}"><button class="link" data-eto-input="${esc(p.input)}">${esc(input?.name ?? p.input)}</button>
        <span class="bar"><span style="width:${(p.share ?? 0) * 100}%"></span></span><span>${share}</span></li>`;
    })
    .join("");
  const years = [...new Set(positions.map((p) => p.year).filter(Boolean))].sort().join(", ");
  return `<ol class="share-list">${rows}</ol>
    <p class="hint">Global market share from the ${esc(idx.doc.market.citation)}${years ? ` (${esc(years)})` : ""}.
      Hover a row for ETO's underlying source.</p>`;
}

const badge = (strength: string) => `<span class="badge s-${esc(strength)}">${esc(strength)}</span>`;

function evidenceHtml(ev: Evidence): string {
  const url = safeUrl(ev.url);
  const title = ev.source_title || ev.source_id || "Source";
  const source = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>` : esc(title);
  const meta = [ev.locator, ev.source_published].filter(Boolean).map(esc).join(" · ");
  const body =
    ev.strength === "inferred"
      ? `<p class="reasoning"><strong>Reasoning:</strong> ${esc(ev.reasoning)}</p>`
      : `<blockquote>${esc(ev.excerpt)}</blockquote>`;
  return `<div class="evidence">${badge(ev.strength)} ${body}<div class="meta">${source}${meta ? ` · ${meta}` : ""}</div></div>`;
}

function edgeFacts(e: Edge): string {
  const facts = [`Alternatives: <strong>${esc(e.has_alternatives)}</strong>`];
  if (e.weight) {
    const what = e.weight.metric === "share_of_buyer_input" ? "of buyer's input" : "of supplier's revenue";
    facts.push(`Weight: <strong>${pct(e.weight.value)}</strong> ${what} <span class="muted" title="${esc(e.weight.basis)}">(basis)</span>`);
  }
  if (e.as_of) facts.push(`As of ${esc(e.as_of)}`);
  return `<div class="facts">${facts.join(" · ")}</div>`;
}

function edgeList(idx: Index, edges: Edge[], other: "supplier" | "buyer", result: ScenarioResult | null): string {
  if (edges.length === 0) return `<p class="muted">None recorded.</p>`;
  const byInput = new Map<string, Edge[]>();
  for (const e of edges) (byInput.get(e.input) ?? byInput.set(e.input, []).get(e.input)!).push(e);
  return [...byInput.entries()]
    .sort(([a], [b]) => idx.input(a).localeCompare(idx.input(b)))
    .map(([input, list]) => {
      const rows = list
        .sort((a, b) => idx.name(a[other]).localeCompare(idx.name(b[other])))
        .map((e) => {
          const state = result?.state[e[other]];
          const dot = state && state !== "ok" ? `<span class="dot st-${state}" title="${STATE_LABEL[state]}"></span>` : "";
          return `<details class="edge-row">
            <summary>${dot}<button class="link" data-node="${esc(e[other])}">${esc(idx.name(e[other]))}</button>
              ${badge(e.strength)}${e.has_alternatives === "no" ? ` <span class="badge sole">sole source</span>` : ""}</summary>
            ${edgeFacts(e)}${e.evidence.map(evidenceHtml).join("")}
          </details>`;
        })
        .join("");
      return `<h4>${inputLink(idx, input)}</h4>${rows}`;
    })
    .join("");
}

function scenarioHtml(idx: Index, id: string, result: ScenarioResult | null): string {
  if (!result) return "";
  const state = result.state[id] ?? "ok";
  const causes = (result.causes[id] ?? []).map((c) => `<li>${esc(explainCause(c, idx.name, idx.input))}</li>`).join("");
  return `<section class="scenario-status st-${state}"><strong>${STATE_LABEL[state]}</strong>${causes ? `<ul>${causes}</ul>` : ""}</section>`;
}

export function nodePanel(idx: Index, id: string, result: ScenarioResult | null): string {
  const n = idx.node.get(id);
  if (!n) return "";
  const facts: string[] = [];
  if (n.hq_country) facts.push(`HQ: <button class="link" data-country="${esc(n.hq_country)}">${esc(countryName(n.hq_country))}</button>`);
  if (n.parent) facts.push(`Part of ${esc(idx.groupName.get(n.parent) ?? n.parent)}`);
  if (n.ticker) facts.push(esc(n.ticker));
  if (n.kind === "product_category") facts.push("End market (product category)");

  const prod = (n.production_countries ?? [])
    .map((p) => {
      const tags = [p.share != null ? pct(p.share) : "", p.primary ? "primary" : "", p.as_of ? `as of ${p.as_of}` : ""].filter(Boolean);
      return `<li title="${esc(p.basis)}"><button class="link" data-country="${esc(p.country)}">${esc(countryName(p.country))}</button>${tags.length ? ` <span class="muted">${esc(tags.join(", "))}</span>` : ""}</li>`;
    })
    .join("");

  const impact = idx.companyImpact.get(id);
  const impactLine = impact
    ? `<p class="muted">On its own, taking it offline fully impacts ${impact.full.length} and partially impacts ${impact.partial.length} other nodes.</p>`
    : "";

  return `
    <header class="panel-head">
      <span class="stage-chip" style="--c:${stageColor(n.stage)}">${esc(stageLabel(n.stage))}</span>
      <h2>${esc(n.name)}</h2>
      <p class="muted">${facts.join(" · ")}</p>
    </header>
    ${scenarioHtml(idx, id, result)}
    ${n.kind === "company" ? `<button class="primary" data-offline="${esc(id)}">What if ${esc(n.name)} goes offline?</button>${impactLine}` : ""}
    ${prod ? `<h3>Production</h3><ul class="plain">${prod}</ul>` : n.kind === "company" ? `<p class="muted">No production locations recorded; country scenarios use the HQ.</p>` : ""}
    ${n.notes ? `<p class="notes">${esc(n.notes)}</p>` : ""}
    ${n.market_positions?.length ? `<h3>Market position</h3>${positionsHtml(idx, n.market_positions)}` : ""}
    <h3>Suppliers <span class="count">${(idx.into.get(id) ?? []).length}</span></h3>
    ${edgeList(idx, idx.into.get(id) ?? [], "supplier", result)}
    <h3>Customers <span class="count">${(idx.out.get(id) ?? []).length}</span></h3>
    ${edgeList(idx, idx.out.get(id) ?? [], "buyer", result)}
  `;
}

export function edgePanel(idx: Index, id: string): string {
  const e = idx.edge.get(id);
  if (!e) return "";
  return `
    <header class="panel-head">
      <span class="stage-chip" style="--c:#475569">${inputLink(idx, e.input)}</span>
      <h2><button class="link" data-node="${esc(e.supplier)}">${esc(idx.name(e.supplier))}</button>
        → <button class="link" data-node="${esc(e.buyer)}">${esc(idx.name(e.buyer))}</button></h2>
    </header>
    ${edgeFacts(e)}
    ${e.notes ? `<p class="notes">${esc(e.notes)}</p>` : ""}
    <h3>Evidence <span class="count">${e.evidence.length}</span></h3>
    ${e.evidence.map(evidenceHtml).join("")}
  `;
}
