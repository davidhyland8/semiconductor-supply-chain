// Panels for ETO market data: an input (who sells it, market shares, where it
// fits) and an ETO company that has no supply relationships in the graph yet.

import type { EtoSupplier } from "../data";
import { countryName, stageColor, stageLabel } from "../labels";
import { esc, pct } from "./html";
import { type Index, inputLink, positionsHtml } from "./panel";

function supplierName(idx: Index, s: EtoSupplier): string {
  if (s.node) return `<button class="link" data-node="${esc(s.node)}">${esc(idx.name(s.node))}</button> <span class="badge">in graph</span>`;
  if (s.company) return `<button class="link" data-market="${esc(s.company)}">${esc(s.name)}</button>`;
  return esc(s.name);
}

const etoLink = (idx: Index, id: string) =>
  `<button class="link" data-eto-input="${esc(id)}">${esc(idx.etoInput.get(id)?.name ?? id)}</button>`;

export function etoInputPanel(idx: Index, id: string): string {
  const input = idx.etoInput.get(id);
  if (!input) return "";
  const withShare = input.suppliers.filter((s) => s.share != null);
  const without = input.suppliers.filter((s) => s.share == null);
  const max = withShare[0]?.share || 1;

  const shareRows = withShare
    .map(
      (s) => `<li><span>${supplierName(idx, s)}</span>
        <span class="bar"><span style="width:${(s.share! / max) * 100}%"></span></span><span>${pct(s.share!)}</span></li>`,
    )
    .join("");
  const totalNamed = withShare.reduce((sum, s) => sum + s.share!, 0);
  const rest = withShare.length && totalNamed < 0.995 ? `<li class="muted"><span>Others / unattributed</span><span></span><span>${pct(1 - totalNamed)}</span></li>` : "";

  const countries = Object.entries(input.country_shares)
    .sort((a, b) => b[1] - a[1])
    .map(([c, v]) => `<li><span>${c === "EU" ? "European Union (bloc)" : `<button class="link" data-country="${esc(c)}">${esc(countryName(c))}</button>`}</span>
      <span class="bar"><span style="width:${v * 100}%"></span></span><span>${pct(v)}</span></li>`)
    .join("");

  const where = [
    input.parent ? `A type of ${etoLink(idx, input.parent)}.` : "",
    input.children.length ? `Types: ${input.children.map((c) => etoLink(idx, c)).join(", ")}.` : "",
    input.goes_into.length ? `Used in ${input.goes_into.map((c) => etoLink(idx, c)).join(", ")}.` : "",
  ].filter(Boolean);

  const graphEdges = idx.doc.edges.filter((e) => input.graph_inputs.includes(e.input));
  const graphLine = input.graph_inputs.length
    ? `<p>In this graph as ${input.graph_inputs.map((g) => inputLink(idx, g)).join(", ")}: ${graphEdges.length} supply relationships.</p>`
    : "";

  return `
    <header class="panel-head">
      ${input.stage ? `<span class="stage-chip" style="--c:${stageColor(input.stage)}">${esc(stageLabel(input.stage))}</span>` : ""}
      <h2>${esc(input.name)}</h2>
      <p class="muted">${[input.market_size ? `Global market: ${esc(input.market_size)}` : "", input.company_hhi != null ? `HHI ${Math.round(input.company_hhi).toLocaleString()}` : ""].filter(Boolean).join(" · ")}</p>
    </header>
    ${graphLine}
    ${where.length ? `<p>${where.join(" ")}</p>` : ""}
    ${input.description ? `<details class="desc"><summary>About this input (ETO)</summary><p>${esc(input.description)}</p></details>` : ""}
    ${shareRows ? `<h3>Market share by company${input.year ? ` <span class="count">${esc(input.year)}</span>` : ""}</h3><ol class="share-list">${shareRows}${rest}</ol>` : ""}
    ${countries ? `<h3>Market share by country</h3><ol class="share-list">${countries}</ol>` : ""}
    ${without.length ? `<h3>Other suppliers ETO lists <span class="count">${without.length}</span></h3><p>${without.map((s) => supplierName(idx, s)).join(", ")}</p>` : ""}
    ${!input.suppliers.length && !countries ? `<p class="muted">ETO lists no suppliers for this input.</p>` : ""}
    <p class="hint">From the ${esc(idx.doc.market.citation)} (${esc(idx.doc.market.license)}). Market share is not a supply relationship:
      it says who sells this input, not to whom.</p>`;
}

export function marketCompanyPanel(idx: Index, id: string): string {
  const c = idx.market.get(id);
  if (!c) return "";
  const facts = [
    c.hq_country ? `HQ: <button class="link" data-country="${esc(c.hq_country)}">${esc(countryName(c.hq_country))}</button>` : "",
    c.aliases.length ? `Also: ${esc(c.aliases.join(", "))}` : "",
  ].filter(Boolean);
  return `
    <header class="panel-head">
      ${c.stage ? `<span class="stage-chip" style="--c:${stageColor(c.stage)}">${esc(stageLabel(c.stage))}</span>` : ""}
      <h2>${esc(c.name)}</h2>
      <p class="muted">${facts.join(" · ")}</p>
    </header>
    <p class="notes">In the ETO dataset, but no supply relationships with a source are recorded for it yet, so it isn't
      in the graph or in scenarios. Its stage is inferred from what it sells.</p>
    <h3>Market position</h3>
    ${positionsHtml(idx, c.positions)}`;
}
