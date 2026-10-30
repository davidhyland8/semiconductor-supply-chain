// Details panel for a country: stage shares, companies, production sites, scenario impact.

import { STAGES, STATE_LABEL, countryName, explainCause, stageColor } from "../labels";
import { countryCriticality, countryShare, hqCompanies, producersIn } from "../map/metrics";
import type { ScenarioResult } from "../scenario/types";
import { esc, pct } from "./html";
import type { Index } from "./panel";

function companyRow(idx: Index, id: string, result: ScenarioResult | null, extra = ""): string {
  const n = idx.node.get(id)!;
  const state = result?.state[id];
  const dot = state && state !== "ok" ? `<span class="dot st-${state}" title="${STATE_LABEL[state]}"></span>` : "";
  return `<li>${dot}<span class="swatch" style="background:${stageColor(n.stage)}"></span>
    <button class="link" data-node="${esc(id)}">${esc(n.name)}</button>${extra ? ` <span class="muted">${esc(extra)}</span>` : ""}</li>`;
}

function marketHtml(idx: Index, code: string): string {
  const companies = idx.doc.market.companies.filter((c) => c.hq_country === code);
  if (companies.length === 0) return "";
  const byStage = STAGES.map((s) => [s, companies.filter((c) => c.stage === s.id)] as const).filter(([, cs]) => cs.length);
  return `<h3>Also headquartered here (ETO market data) <span class="count">${companies.length}</span></h3>
    <p class="hint">Companies with ETO market shares but no sourced relationships yet, so not in the graph.</p>
    ${byStage
      .map(
        ([s, cs]) => `<details class="edge-row"><summary><span class="swatch" style="background:${s.color}"></span>${esc(s.label)}
          <span class="count">${cs.length}</span></summary>
          <p>${cs.map((c) => `<button class="link" data-market="${esc(c.id)}">${esc(c.name)}</button>`).join(", ")}</p></details>`,
      )
      .join("")}`;
}

export function countryPanel(idx: Index, code: string, result: ScenarioResult | null): string {
  const { doc } = idx;
  const name = countryName(code);

  const shareRows = STAGES.map((s) => {
    const stage = doc.analysis.stage_country_shares[s.id];
    const share = countryShare(code, stage);
    const covered = stage && Object.keys(stage.shares).length > 0;
    const value = share ? (share.viaEU ? `${pct(share.value)} <span class="muted">EU bloc</span>` : pct(share.value)) : covered ? "—" : `<span class="muted">no data</span>`;
    const width = share && !share.viaEU ? share.value * 100 : 0;
    return `<li><span>${esc(s.label)}</span><span class="bar"><span style="width:${width}%;background:${s.color}"></span></span><span>${value}</span></li>`;
  }).join("");

  const hq = hqCompanies(doc.nodes, code).sort((a, b) => a.name.localeCompare(b.name));
  const producers = producersIn(doc.nodes, code).sort((a, b) => a.name.localeCompare(b.name));

  const crit = countryCriticality(doc, code);
  const critLine = crit
    ? `<p class="muted">On its own, taking ${esc(name)} offline knocks out ${crit.offline.length}, fully impacts ${crit.full.length}
       and partially impacts ${crit.partial.length} nodes.</p>`
    : "";

  let status = "";
  if (result) {
    const hit = [...hq, ...producers].filter((n) => (result.state[n.id] ?? "ok") !== "ok");
    status = hit.length
      ? `<section class="scenario-status st-full"><strong>${hit.length} companies here or producing here are impacted</strong>
          <ul>${hit
            .slice(0, 6)
            .map((n) => `<li>${esc(n.name)}: ${esc(explainCause(result.causes[n.id]![0]!, idx.name, idx.input))}</li>`)
            .join("")}${hit.length > 6 ? `<li>…and ${hit.length - 6} more</li>` : ""}</ul></section>`
      : `<section class="scenario-status"><strong>No companies here are impacted in this scenario</strong></section>`;
  }

  return `
    <header class="panel-head">
      <span class="stage-chip" style="--c:#475569">Country</span>
      <h2>${esc(name)}</h2>
    </header>
    ${status}
    <button class="primary" data-offline-country="${esc(code)}">What if ${esc(name)} goes offline?</button>
    ${critLine}
    <h3>Share of each stage</h3>
    <ol class="share-list stages">${shareRows}</ol>
    <p class="hint">From the ETO dataset; see the map's notes for what each stage's figure measures.</p>
    <h3>Headquartered here <span class="count">${hq.length}</span></h3>
    ${hq.length ? `<ul class="plain companies">${hq.map((n) => companyRow(idx, n.id, result)).join("")}</ul>` : `<p class="muted">None in the graph.</p>`}
    <h3>Producing here, headquartered elsewhere <span class="count">${producers.length}</span></h3>
    ${
      producers.length
        ? `<ul class="plain companies">${producers
            .map((n) => {
              const p = n.production_countries!.find((x) => x.country === code)!;
              const tags = [p.share != null ? pct(p.share) : "", p.primary ? "primary site" : ""].filter(Boolean).join(", ");
              return companyRow(idx, n.id, result, tags);
            })
            .join("")}</ul>`
        : `<p class="muted">None recorded.</p>`
    }
    ${marketHtml(idx, code)}`;
}
