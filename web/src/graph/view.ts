// Cytoscape rendering of the graph: layered and force views, filter visibility,
// scenario colouring and neighbourhood highlighting.

import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";
import fcose from "cytoscape-fcose";
import type { GraphDoc } from "../data";
import { STAGES, stageColor } from "../labels";
import type { ScenarioResult } from "../scenario/types";
import { layeredPositions } from "./layout";

cytoscape.use(fcose);

export type ViewMode = "layered" | "force";

export interface ViewHandlers {
  onNode(id: string): void;
  onEdge(id: string): void;
  onBackground(): void;
}

const COLUMN_GAP = 210;

const STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      "background-color": "data(color)",
      label: "data(label)",
      width: "data(size)",
      height: "data(size)",
      "font-size": 12,
      "font-family": "Inter, system-ui, sans-serif",
      color: "#1e293b",
      "text-valign": "bottom",
      "text-margin-y": 3,
      "text-outline-color": "#f8fafc",
      "text-outline-width": 2,
      "border-width": 1.5,
      "border-color": "#ffffff",
    },
  },
  { selector: "node[kind = 'product_category']", style: { shape: "round-rectangle" } },
  {
    selector: "node.header",
    style: {
      shape: "rectangle",
      "background-opacity": 0,
      "border-width": 0,
      width: 1,
      height: 1,
      "font-size": 13,
      "font-weight": 600,
      color: "#475569",
      "text-valign": "center",
      events: "no",
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.3,
      "line-color": "#475569",
      "target-arrow-color": "#475569",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
      "curve-style": "bezier",
      opacity: 0.55,
    },
  },
  { selector: "edge[strength = 'reported']", style: { "line-style": "dashed", "line-dash-pattern": [6, 3] } },
  {
    selector: "edge[strength = 'inferred']",
    style: { "line-style": "dotted", "line-color": "#94a3b8", "target-arrow-color": "#94a3b8" },
  },
  // Scenario colouring
  { selector: "node.state-ok", style: { "background-color": "#cbd5e1" } },
  { selector: "node.state-partial", style: { "background-color": "#f59e0b" } },
  { selector: "node.state-full", style: { "background-color": "#dc2626" } },
  { selector: "node.state-offline", style: { "background-color": "#111827", "border-color": "#111827" } },
  { selector: "edge.lost", style: { "line-color": "#dc2626", "target-arrow-color": "#dc2626", opacity: 0.9 } },
  { selector: "edge.degraded", style: { "line-color": "#f59e0b", "target-arrow-color": "#f59e0b", opacity: 0.9 } },
  { selector: "edge.calm", style: { opacity: 0.2 } },
  // Selection
  { selector: "node.faded", style: { opacity: 0.15 } },
  { selector: "edge.faded", style: { opacity: 0.05 } },
  { selector: "edge.near", style: { opacity: 1, width: 2.2 } },
  { selector: "node:selected", style: { "border-width": 3, "border-color": "#0f172a" } },
  { selector: "edge:selected", style: { width: 3.2, opacity: 1 } },
  { selector: ".hidden", style: { display: "none" } },
];

function elements(doc: GraphDoc): ElementDefinition[] {
  const degree = new Map<string, number>();
  for (const e of doc.edges) {
    degree.set(e.supplier, (degree.get(e.supplier) ?? 0) + 1);
    degree.set(e.buyer, (degree.get(e.buyer) ?? 0) + 1);
  }
  const nodes: ElementDefinition[] = doc.nodes.map((n) => ({
    group: "nodes",
    data: {
      id: n.id,
      label: n.name,
      kind: n.kind,
      stage: n.stage,
      color: stageColor(n.stage),
      size: 14 + 3 * Math.sqrt(degree.get(n.id) ?? 0),
    },
  }));
  const headers: ElementDefinition[] = STAGES.map((s) => ({
    group: "nodes",
    data: { id: `header:${s.id}`, label: s.label, kind: "header" },
    classes: "header",
    selectable: false,
    grabbable: false,
  }));
  const edges: ElementDefinition[] = doc.edges.map((e) => ({
    group: "edges",
    data: { id: e.id, source: e.supplier, target: e.buyer, strength: e.strength },
  }));
  return [...nodes, ...headers, ...edges];
}

export class GraphView {
  readonly cy: Core;
  private mode: ViewMode = "layered";
  private laidOut = false;
  private running: cytoscape.Layouts | null = null;
  private names: Map<string, string>;

  constructor(container: HTMLElement, doc: GraphDoc, handlers: ViewHandlers) {
    this.names = new Map(doc.nodes.map((n) => [n.id, n.name]));
    this.cy = cytoscape({
      container,
      elements: elements(doc),
      style: STYLE,
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
    });
    // Re-fit when the canvas changes size (window resize, panels toggling, a view switch).
    let resizeTimer: number | undefined;
    new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        this.cy.resize();
        this.cy.fit(this.cy.elements().not(".hidden"), 40);
      }, 100);
    }).observe(container);
    this.cy.on("tap", "node", (ev) => handlers.onNode(ev.target.id()));
    this.cy.on("tap", "edge", (ev) => handlers.onEdge(ev.target.id()));
    this.cy.on("tap", (ev) => {
      if (ev.target === this.cy) handlers.onBackground();
    });
  }

  private headers() {
    return this.cy.nodes(".header");
  }

  private visibleGraph() {
    return this.cy.elements().not(".hidden").not(".header");
  }

  setMode(mode: ViewMode) {
    this.mode = mode;
    this.relayout();
  }

  relayout() {
    this.running?.stop();
    const visible = this.visibleGraph();
    if (this.mode === "layered") {
      const nodes = visible.nodes().map((n) => ({ id: n.id(), stage: n.data("stage"), name: this.names.get(n.id()) }));
      const edges = visible.edges().map((e) => ({ supplier: e.source().id(), buyer: e.target().id() }));
      // Spread rows to roughly match the canvas's aspect ratio, so labels stay readable.
      const tallest = Math.max(1, ...STAGES.map((s) => nodes.filter((n) => n.stage === s.id).length));
      const aspect = this.cy.height() / Math.max(1, this.cy.width());
      const rowGap = Math.min(110, Math.max(56, (aspect * STAGES.length * COLUMN_GAP) / tallest));
      const positions = layeredPositions(nodes, edges, {
        stageOrder: STAGES.map((s) => s.id),
        columnGap: COLUMN_GAP,
        subColumnGap: 70,
        rowGap,
      });
      const top = Math.min(0, ...Object.values(positions).map((p) => p.y)) - 60;
      STAGES.forEach((s, i) => (positions[`header:${s.id}`] = { x: i * COLUMN_GAP + 40, y: top }));
      this.headers().removeClass("hidden");
      // Hide headers for stages with nothing visible.
      this.headers().forEach((h) => {
        const stage = h.id().slice("header:".length);
        if (!nodes.some((n) => n.stage === stage)) h.addClass("hidden");
      });
      this.running = this.cy
        .elements()
        .not(".hidden")
        .layout({ name: "preset", positions, fit: true, padding: 40, animate: this.laidOut, animationDuration: 300 });
    } else {
      this.headers().addClass("hidden");
      this.running = visible.layout({
          name: "fcose",
          quality: "proof",
          randomize: true,
          animate: this.laidOut,
          animationDuration: 500,
          nodeRepulsion: () => 9000,
          idealEdgeLength: () => 90,
          nodeSeparation: 90,
          padding: 40,
        } as cytoscape.LayoutOptions);
    }
    this.running.run();
    this.laidOut = true;
  }

  setVisible(nodeIds: Set<string>, edgeIds: Set<string>) {
    this.cy.batch(() => {
      this.cy.nodes().not(".header").forEach((n) => {
        n.toggleClass("hidden", !nodeIds.has(n.id()));
      });
      this.cy.edges().forEach((e) => {
        e.toggleClass("hidden", !edgeIds.has(e.id()));
      });
    });
    this.relayout();
  }

  setScenario(result: ScenarioResult | null) {
    this.cy.batch(() => {
      this.cy.elements().removeClass("state-ok state-partial state-full state-offline lost degraded calm");
      if (!result) return;
      this.cy.nodes().not(".header").forEach((n) => {
        n.addClass(`state-${result.state[n.id()] ?? "ok"}`);
      });
      this.cy.edges().forEach((e) => {
        const s = result.state[e.source().id()];
        e.addClass(s === "full" || s === "offline" ? "lost" : s === "partial" ? "degraded" : "calm");
      });
    });
  }

  select(sel: { kind: "node" | "edge"; id: string } | null) {
    this.cy.batch(() => {
      this.cy.elements().unselect().removeClass("faded near");
      if (!sel) return;
      const el = this.cy.getElementById(sel.id);
      if (el.empty()) return;
      el.select();
      const keep = sel.kind === "node" ? el.closedNeighborhood() : el.union(el.connectedNodes());
      this.cy.elements().not(".header").not(keep).addClass("faded");
      keep.edges().addClass("near");
    });
  }

  fitTo(id: string) {
    const el = this.cy.getElementById(id);
    if (el.nonempty() && !el.hasClass("hidden")) {
      this.cy.animate({ fit: { eles: el.closedNeighborhood().not(".hidden"), padding: 80 }, duration: 300 });
    }
  }

  fit() {
    this.cy.animate({ fit: { eles: this.cy.elements().not(".hidden"), padding: 40 }, duration: 300 });
  }
}
