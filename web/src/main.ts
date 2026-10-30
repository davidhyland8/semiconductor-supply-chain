import "./style.css";
import { loadLatest, type GraphDoc } from "./data";
import { visibleElements } from "./filters";
import { GraphView, type ViewMode } from "./graph/view";
import { MapView } from "./map/mapView";
import { propagate } from "./scenario/propagate";
import type { Scenario, ScenarioResult } from "./scenario/types";
import { countryPanel } from "./ui/countryPanel";
import { esc } from "./ui/html";
import { Index, edgePanel, nodePanel } from "./ui/panel";
import { Sidebar } from "./ui/sidebar";

type Selection = { kind: "node" | "edge" | "country"; id: string } | null;

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
    <p class="muted">Graph build v${esc(doc.version)} (${esc(doc.built)}). Public sources only: company filings,
      press releases, news and the ETO Advanced Semiconductor Supply Chain Dataset.</p>`;
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
          : countryPanel(idx, selection.id, result);
    panelEl.scrollTop = 0;
  };

  const select = (sel: Selection, zoom = false) => {
    selection = sel;
    view.select(sel && sel.kind !== "country" ? { kind: sel.kind, id: sel.id } : null);
    map.select(sel?.kind === "country" ? sel.id : null);
    if (zoom && sel && sel.kind !== "country") view.fitTo(sel.id);
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
    if (nodeLink) {
      ev.preventDefault();
      select({ kind: "node", id: nodeLink.dataset.node! }, true);
    } else if (offline) {
      sidebar.setScenario({ companies: [offline.dataset.offline!] });
    } else if (countryOffline) {
      sidebar.setScenario({ countries: [countryOffline.dataset.offlineCountry!] });
    } else if (country) {
      select({ kind: "country", id: country.dataset.country! });
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
  document.getElementById("node-names")!.innerHTML = doc.nodes
    .map((n) => `<option value="${esc(n.name)}"></option>`)
    .join("");
  search.addEventListener("change", () => {
    const q = search.value.trim().toLowerCase();
    const hit =
      doc.nodes.find((n) => n.name.toLowerCase() === q) ??
      doc.nodes.find((n) => [n.name, ...(n.aliases ?? []), n.ticker ?? ""].some((s) => s.toLowerCase().includes(q)));
    if (q && hit) select({ kind: "node", id: hit.id }, true);
  });

  view.relayout();
  renderPanel();
}

main().catch((err) => {
  document.getElementById("graph")!.innerHTML = `<p class="error">${esc(err instanceof Error ? err.message : err)}</p>`;
  console.error(err);
});
