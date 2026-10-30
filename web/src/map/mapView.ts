// World map (D3 geo projection, SVG): country share of a stage, or scenario impact.

import { geoNaturalEarth1, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import type { GraphDoc } from "../data";
import { STAGES, countryName, stageLabel } from "../labels";
import type { ScenarioResult } from "../scenario/types";
import { esc, pct } from "../ui/html";
import { NUMERIC_TO_ISO2, POINT_COUNTRIES } from "./countries";
import { IMPACT_RAMP, SHARE_RAMP, countryShare, ramp, scenarioImpact } from "./metrics";

export type MapMode = "share" | "impact";

const NO_DATA = "#e2e8f0";
const OFFLINE = "#111827";

export class MapView {
  private readonly svg: SVGSVGElement;
  private readonly tooltip: HTMLDivElement;
  private readonly toolbar: HTMLDivElement;
  private readonly info: HTMLDivElement;
  private readonly countries: FeatureCollection<Geometry, { name: string }>;
  private stage = "fabrication";
  private mode: MapMode = "share";
  private result: ScenarioResult | null = null;
  private offline = new Set<string>();
  private selected: string | null = null;
  private drawnFor = "";

  constructor(
    private readonly el: HTMLElement,
    private readonly doc: GraphDoc,
    private readonly onCountry: (code: string) => void,
  ) {
    const topo = world as unknown as Topology<{ countries: GeometryCollection<{ name: string }> }>;
    const all = feature(topo, topo.objects.countries) as FeatureCollection<Geometry, { name: string }>;
    this.countries = { ...all, features: all.features.filter((f) => f.id !== "010") }; // drop Antarctica

    el.innerHTML = `
      <div class="map-toolbar">
        <label>Stage <select id="map-stage">${STAGES.map((s) => `<option value="${s.id}">${esc(s.label)}</option>`).join("")}</select></label>
        <div class="segmented small" role="group" aria-label="Map colouring">
          <button data-map-mode="share" aria-pressed="true">Country share</button>
          <button data-map-mode="impact" aria-pressed="false">Scenario impact</button>
        </div>
      </div>
      <svg class="map-svg" role="img" aria-label="World map"></svg>
      <div class="map-info"></div>
      <div class="map-tooltip" hidden></div>`;
    this.svg = el.querySelector("svg")!;
    this.tooltip = el.querySelector(".map-tooltip")!;
    this.toolbar = el.querySelector(".map-toolbar")!;
    this.info = el.querySelector(".map-info")!;
    (this.toolbar.querySelector("#map-stage") as HTMLSelectElement).value = this.stage;

    this.toolbar.querySelector("#map-stage")!.addEventListener("change", (ev) => {
      this.stage = (ev.target as HTMLSelectElement).value;
      this.setMode("share");
    });
    this.toolbar.querySelectorAll<HTMLButtonElement>("[data-map-mode]").forEach((b) =>
      b.addEventListener("click", () => this.setMode(b.dataset.mapMode as MapMode)),
    );
    this.svg.addEventListener("click", (ev) => {
      const code = (ev.target as Element).closest<SVGElement>("[data-code]")?.dataset.code;
      if (code) this.onCountry(code);
    });
    this.svg.addEventListener("mousemove", (ev) => this.hover(ev));
    this.svg.addEventListener("mouseleave", () => (this.tooltip.hidden = true));
    new ResizeObserver(() => this.draw()).observe(el);
  }

  setMode(mode: MapMode) {
    this.mode = mode === "impact" && !this.result ? "share" : mode;
    this.toolbar.querySelectorAll("[data-map-mode]").forEach((b) =>
      b.setAttribute("aria-pressed", String((b as HTMLElement).dataset.mapMode === this.mode)),
    );
    (this.toolbar.querySelector('[data-map-mode="impact"]') as HTMLButtonElement).disabled = !this.result;
    this.toolbar.querySelector("label")!.classList.toggle("dim", this.mode === "impact");
    this.colour();
  }

  setScenario(result: ScenarioResult | null, offlineCountries: string[]) {
    this.result = result;
    this.offline = new Set(offlineCountries);
    this.setMode(result ? "impact" : "share");
  }

  select(code: string | null) {
    this.selected = code;
    this.svg.querySelectorAll("[data-code]").forEach((p) =>
      p.classList.toggle("selected", (p as SVGElement).dataset.code === code),
    );
  }

  private draw() {
    const { width, height } = this.svg.getBoundingClientRect();
    const key = `${Math.round(width)}x${Math.round(height)}`;
    if (width === 0 || height === 0 || key === this.drawnFor) return;
    this.drawnFor = key;
    const projection = geoNaturalEarth1().fitExtent(
      [
        [8, 8],
        [width - 8, height - 8],
      ],
      this.countries,
    );
    const path = geoPath(projection);
    const shapes = this.countries.features
      .map((f: Feature<Geometry, { name: string }>) => {
        const code = NUMERIC_TO_ISO2[String(f.id)];
        return `<path d="${path(f) ?? ""}" ${code ? `data-code="${code}"` : ""} data-name="${esc(f.properties.name)}"></path>`;
      })
      .join("");
    const points = Object.entries(POINT_COUNTRIES)
      .map(([code, lonlat]) => {
        const [x, y] = projection(lonlat) ?? [0, 0];
        return `<circle class="point" cx="${x}" cy="${y}" r="4" data-code="${code}"></circle>`;
      })
      .join("");
    this.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    this.svg.innerHTML = `<g class="countries">${shapes}</g><g>${points}</g>`;
    this.colour();
    this.select(this.selected);
  }

  private colour() {
    const shares = this.doc.analysis.stage_country_shares[this.stage];
    const max = Math.max(0.01, ...Object.values(shares?.shares ?? {}));
    this.svg.querySelectorAll<SVGElement>("path, circle").forEach((p) => {
      const code = p.dataset.code;
      let fill = NO_DATA;
      let hatch = false;
      if (code && this.mode === "share") {
        const s = countryShare(code, shares);
        if (s) {
          fill = ramp(SHARE_RAMP, s.value / max);
          hatch = s.viaEU;
        }
      } else if (code && this.result) {
        const impact = scenarioImpact(this.doc.nodes, this.result, code);
        if (this.offline.has(code)) fill = OFFLINE;
        else if (impact && impact.score > 0) fill = ramp(IMPACT_RAMP, impact.score);
      }
      p.style.fill = fill;
      p.classList.toggle("eu-bloc", hatch);
    });
    this.renderInfo();
  }

  private renderInfo() {
    if (this.mode === "impact") {
      this.info.innerHTML = `
        <div class="legend-ramp" style="--ramp:linear-gradient(90deg, ${IMPACT_RAMP.join(",")})"><span>Some</span><span>All</span></div>
        <p class="hint">Share of companies headquartered in each country that are impacted (fully = 1, partially = ½).
          Black: taken offline in the scenario.</p>`;
      return;
    }
    const s = this.doc.analysis.stage_country_shares[this.stage];
    if (!s || Object.keys(s.shares).length === 0) {
      this.info.innerHTML = `<p><strong>${esc(stageLabel(this.stage))}</strong>: no public country-level figures found yet.
        This stage is not covered by the ETO dataset.</p>`;
      return;
    }
    const rows = Object.entries(s.shares)
      .slice(0, 8)
      .map(
        ([c, v]) => `<li data-code="${esc(c)}"><span>${esc(c === "EU" ? "European Union (bloc)" : countryName(c))}</span>
          <span class="bar"><span style="width:${(v / Object.values(s.shares)[0]!) * 100}%"></span></span><span>${pct(v)}</span></li>`,
      )
      .join("");
    const other = s.other_share ? `<li class="muted"><span>Other countries</span><span></span><span>${pct(s.other_share)}</span></li>` : "";
    this.info.innerHTML = `
      <h4>${esc(stageLabel(this.stage))}: share by country</h4>
      <ol class="share-list">${rows}${other}</ol>
      <p class="hint">${esc(s.basis ?? "")} ${esc((s.years ?? []).join(", "))}. Source: ${esc(s.source)}.
        ${"EU" in s.shares ? "Hatched countries show the EU bloc's combined figure." : ""}</p>`;
    this.info.querySelectorAll<HTMLElement>("li[data-code]").forEach((li) =>
      li.addEventListener("click", () => li.dataset.code !== "EU" && this.onCountry(li.dataset.code!)),
    );
  }

  private hover(ev: MouseEvent) {
    const t = (ev.target as Element).closest<SVGElement>("[data-code], [data-name]");
    if (!t) {
      this.tooltip.hidden = true;
      return;
    }
    const code = t.dataset.code;
    const name = code ? countryName(code) : (t.dataset.name ?? "");
    let detail = "No data";
    if (code && this.mode === "share") {
      const s = countryShare(code, this.doc.analysis.stage_country_shares[this.stage]);
      if (s) detail = s.viaEU ? `EU bloc: ${pct(s.value)}` : pct(s.value);
    } else if (code && this.result) {
      const i = scenarioImpact(this.doc.nodes, this.result, code);
      if (this.offline.has(code)) detail = "Offline";
      else if (i) detail = `${i.counts.offline + i.counts.full} of ${i.total} companies fully impacted, ${i.counts.partial} partially`;
    }
    this.tooltip.innerHTML = `<strong>${esc(name)}</strong><br>${esc(detail)}`;
    const box = this.el.getBoundingClientRect();
    this.tooltip.style.left = `${ev.clientX - box.left + 12}px`;
    this.tooltip.style.top = `${ev.clientY - box.top + 12}px`;
    this.tooltip.hidden = false;
  }
}
