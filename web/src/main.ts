import "./style.css";
import { loadLatest, type GraphDoc } from "./data";
import { visibleElements } from "./filters";
import { GraphView, type ViewMode } from "./graph/view";
import { MapView } from "./map/mapView";
import { propagate } from "./scenario/propagate";
import type { Scenario, ScenarioResult } from "./scenario/types";
import { countryPanel } from "./ui/countryPanel";
import { find, searchEntries } from "./search";
import { esc } from "./ui/html";
import { etoInputPanel, marketCompanyPanel } from "./ui/marketPanel";
import { Index, edgePanel, nodePanel } from "./ui/panel";
import { Sidebar } from "./ui/sidebar";

type Selection = { kind: "node" | "edge" | "country" | "market" | "input"; id: string } | null;

function aboutPanel(doc: GraphDoc): string {
  const count = (s: string) => doc.edges.filter((e) => e.strength === s).length;
  return `
    <header class="panel-head"><h2>About this map</h2></header>
    <p>${doc.nodes.length} companies and end markets, linked by ${doc.edges.length} supply relationships.
      Arrows point from supplier to buyer. Every relationship carries its evidence.</p>
    <ul class="plain">
      <li><svg class="line-swatch s-disclosed" width="28" height="8"><line x1="0" y1="4" x2="28" y2="4"/></svg>
        <strong>${count("disclosed")}</strong> disclosed by a party to the deal</li>
      <li><svg class="line-swatch s-reported" width="28" height="8"><line x1="0" y1="4" x2="28" y2="4"/></svg>
        <strong>${count("reported")}</strong> reported by a third party</li>
      <li><svg class="line-swatch s-inferred" width="28" height="8"><line x1="0" y1="4" x2="28" y2="4"/></svg>
        <strong>${count("inferred")}</strong> inferred from market shares, with the reasoning written down</li>
    </ul>
    <p>Click a company to see its suppliers, customers and the source behind each link, or take something offline from the left to see what breaks.</p>
    <p>Search also covers ${doc.market.companies.length} more companies and ${doc.market.inputs.length} inputs from the ETO
      dataset, with their market shares. Those companies have no sourced relationships yet, so they aren't in the graph.</p>
    <p class="muted">Graph build v${esc(doc.version)} (${esc(doc.built)}). Public sources only: company filings,
      press releases, news and the ${esc(doc.market.citation)} (${esc(doc.market.license)}).</p>`;
}

async function main() {
  const doc = await loadLatest();
  const idx = new Index(doc);
  const panelEl = document.getElementById("panel")!;
  let selection: Selection = null;
  let scenario: Scenario = {};
  let result: ScenarioResult | null = null;

  const renderPanel = () => {
    panelEl.innerHTML = !selection
      ? aboutPanel(doc)
      : selection.kind === "node"
        ? nodePanel(idx, selection.id, result)
        : selection.kind === "edge"
          ? edgePanel(idx, selection.id)
          : selection.kind === "market"
            ? marketCompanyPanel(idx, selection.id)
            : selection.kind === "input"
              ? etoInputPanel(idx, selection.id)
              : countryPanel(idx, selection.id, result);
    panelEl.scrollTop = 0;
  };

  const select = (sel: Selection, zoom = false) => {
    selection = sel;
    const inGraph = sel && (sel.kind === "node" || sel.kind === "edge") ? { kind: sel.kind, id: sel.id } : null;
    view.select(inGraph);
    map.select(sel?.kind === "country" ? sel.id : null);
    if (zoom && inGraph) view.fitTo(inGraph.id);
    renderPanel();
  };

  const view = new GraphView(document.getElementById("graph")!, doc, {
    onNode: (id) => select({ kind: "node", id }),
    onEdge: (id) => select({ kind: "edge", id }),
    onBackground: () => select(null),
  });

  const map = new MapView(document.getElementById("map")!, doc, (code) => select({ kind: "country", id: code }));

  const sidebar = new Sidebar(document.getElementById("sidebar")!, doc, {
    onScenario: (s) => {
      scenario = s;
      const active = Object.values(scenario).some((v) => v && v.length > 0);
      result = active ? propagate(doc.nodes, doc.edges, scenario) : null;
      view.setScenario(result);
      map.setScenario(result, scenario.countries ?? []);
      sidebar.showSummary(result);
      renderPanel();
    },
    onFilters: (f) => {
      const { nodeIds, edgeIds } = visibleElements(doc.nodes, doc.edges, f);
      view.setVisible(nodeIds, edgeIds);
      if (selection?.kind === "node" && !nodeIds.has(selection.id)) select(null);
    },
  });

  // Links in the panel: jump to a node, or take it offline.
  panelEl.addEventListener("click", (ev) => {
    const t = ev.target as HTMLElement;
    const nodeLink = t.closest<HTMLElement>("[data-node]");
    const offline = t.closest<HTMLElement>("[data-offline]");
    const country = t.closest<HTMLElement>("[data-country]");
    const countryOffline = t.closest<HTMLElement>("[data-offline-country]");
    const marketLink = t.closest<HTMLElement>("[data-market]");
    const inputLink = t.closest<HTMLElement>("[data-eto-input]");
    if (nodeLink) {
      ev.preventDefault();
      select({ kind: "node", id: nodeLink.dataset.node! }, true);
    } else if (offline) {
      sidebar.setScenario({ companies: [offline.dataset.offline!] });
    } else if (countryOffline) {
      sidebar.setScenario({ countries: [countryOffline.dataset.offlineCountry!] });
    } else if (country) {
      select({ kind: "country", id: country.dataset.country! });
    } else if (marketLink) {
      select({ kind: "market", id: marketLink.dataset.market! });
    } else if (inputLink) {
      select({ kind: "input", id: inputLink.dataset.etoInput! });
    }
  });

  document.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      const mode = b.dataset.mode as ViewMode | "map";
      document.body.classList.toggle("map-mode", mode === "map");
      if (mode !== "map") view.setMode(mode);
    }),
  );
  document.getElementById("fit")!.addEventListener("click", () => view.fit());

  const search = document.getElementById("search") as HTMLInputElement;
  const entries = searchEntries(doc);
  document.getElementById("node-names")!.innerHTML = entries.map((e) => `<option value="${esc(e.label)}"></option>`).join("");
  search.addEventListener("change", () => {
    const hit = find(entries, search.value);
    if (hit) select(hit, true);
  });

  view.relayout();
  renderPanel();
}

main().catch((err) => {
  document.getElementById("graph")!.innerHTML = `<p class="error">${esc(err instanceof Error ? err.message : err)}</p>`;
  console.error(err);
});
