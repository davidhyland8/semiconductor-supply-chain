// Left sidebar: scenario builder, most-critical rankings and display filters.

import { STRENGTHS, type GraphDoc, type Impact, type Strength } from "../data";
import { nodeCountries, type Filters } from "../filters";
import { STAGES, countryName, stageLabel } from "../labels";
import type { Scenario, ScenarioResult } from "../scenario/types";
import { esc } from "./html";

type ScenarioKey = keyof Scenario;
type RankKind = "companies" | "countries" | "stages";

export interface SidebarHandlers {
  onScenario(s: Scenario): void;
  onFilters(f: Filters): void;
}

const STRENGTH_HELP: Record<Strength, string> = {
  disclosed: "stated by a party to the relationship (filing, press release)",
  reported: "stated by a third party (news, analysts)",
  inferred: "not stated; reasoning written down",
};

export class Sidebar {
  private scenario: Scenario = {};
  private filters: Filters;
  private rank: RankKind = "companies";
  private readonly countries: [string, number][];

  constructor(
    private readonly el: HTMLElement,
    private readonly doc: GraphDoc,
    private readonly handlers: SidebarHandlers,
  ) {
    const counts = new Map<string, number>();
    for (const n of doc.nodes) for (const c of nodeCountries(n)) counts.set(c, (counts.get(c) ?? 0) + 1);
    this.countries = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    this.filters = { stages: new Set(STAGES.map((s) => s.id)), countries: new Set(), strengths: new Set(STRENGTHS) };
    this.el.innerHTML = this.skeleton();
    this.bind();
    this.fillValues();
    this.renderRanking();
  }

  get currentFilters() {
    return this.filters;
  }

  private label(kind: ScenarioKey, id: string) {
    if (kind === "stages") return stageLabel(id);
    if (kind === "countries") return countryName(id);
    return this.doc.nodes.find((n) => n.id === id)?.name ?? id;
  }

  private options(kind: ScenarioKey): [string, string][] {
    if (kind === "stages") return STAGES.map((s) => [s.id, s.label]);
    if (kind === "countries") return this.countries.map(([c]) => [c, countryName(c)] as [string, string]).sort((a, b) => a[1].localeCompare(b[1]));
    return this.doc.nodes
      .filter((n) => n.kind === "company")
      .map((n) => [n.id, n.name] as [string, string])
      .sort((a, b) => a[1].localeCompare(b[1]));
  }

  private skeleton(): string {
    const stageBoxes = STAGES.map(
      (s) => `<label class="check"><input type="checkbox" data-stage="${s.id}" checked>
        <span class="swatch" style="background:${s.color}"></span>${esc(s.label)}</label>`,
    ).join("");
    const countryBoxes = this.countries
      .map(([c, n]) => `<label class="check"><input type="checkbox" data-country="${esc(c)}">${esc(countryName(c))} <span class="muted">${n}</span></label>`)
      .join("");
    const strengthBoxes = STRENGTHS.map(
      (s) => `<label class="check" title="${esc(STRENGTH_HELP[s])}"><input type="checkbox" data-strength="${s}" checked>
        <svg class="line-swatch s-${s}" width="28" height="8"><line x1="0" y1="4" x2="28" y2="4"/></svg>${s}</label>`,
    ).join("");
    return `
      <section>
        <h3>What if… goes offline?</h3>
        <div class="add-row">
          <select id="scn-kind" aria-label="Scenario type">
            <option value="companies">Company</option><option value="countries">Country</option><option value="stages">Stage</option>
          </select>
          <select id="scn-value" aria-label="What to take offline"></select>
          <button id="scn-add">Add</button>
        </div>
        <div id="scn-chips" class="chips"></div>
        <div id="scn-summary"></div>
        <p class="hint">Scenarios always run on the full graph; filters only hide things.</p>
      </section>
      <section>
        <h3>Biggest single points of failure</h3>
        <div class="tabs" role="tablist">
          <button role="tab" data-rank="companies" aria-selected="true">Companies</button>
          <button role="tab" data-rank="countries">Countries</button>
          <button role="tab" data-rank="stages">Stages</button>
        </div>
        <ol id="ranking" class="ranking"></ol>
        <p class="hint">Score = nodes knocked out + fully impacted + ½ × partially impacted.</p>
      </section>
      <section>
        <h3>Filters</h3>
        <h4>Stages</h4>${stageBoxes}
        <h4>Countries <button class="link small" id="country-clear">all</button></h4>
        <div class="scroll">${countryBoxes}</div>
        <p class="hint">HQ or production location. End markets always show.</p>
        <h4>Evidence</h4>${strengthBoxes}
      </section>
      <section class="legend">
        <h3>Legend</h3>
        <div><span class="shape circle"></span>Company <span class="shape square"></span>End market</div>
        <div><span class="dot st-offline"></span>Offline <span class="dot st-full"></span>Fully impacted</div>
        <div><span class="dot st-partial"></span>Partially impacted <span class="dot st-ok"></span>Not impacted</div>
      </section>`;
  }

  private $<T extends HTMLElement>(sel: string) {
    return this.el.querySelector<T>(sel)!;
  }

  private bind() {
    this.$("#scn-kind").addEventListener("change", () => this.fillValues());
    this.$("#scn-add").addEventListener("click", () => {
      const kind = this.$<HTMLSelectElement>("#scn-kind").value as ScenarioKey;
      const value = this.$<HTMLSelectElement>("#scn-value").value;
      const list = this.scenario[kind] ?? [];
      if (value && !list.includes(value)) this.setScenario({ ...this.scenario, [kind]: [...list, value] });
    });
    this.$("#scn-chips").addEventListener("click", (ev) => {
      const btn = (ev.target as HTMLElement).closest<HTMLElement>("[data-remove]");
      if (btn) {
        const [kind, id] = btn.dataset.remove!.split(":") as [ScenarioKey, string];
        this.setScenario({ ...this.scenario, [kind]: (this.scenario[kind] ?? []).filter((x) => x !== id) });
      } else if ((ev.target as HTMLElement).id === "scn-clear") {
        this.setScenario({});
      }
    });
    this.el.querySelectorAll<HTMLButtonElement>("[data-rank]").forEach((b) =>
      b.addEventListener("click", () => {
        this.rank = b.dataset.rank as RankKind;
        this.el.querySelectorAll("[data-rank]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
        this.renderRanking();
      }),
    );
    this.$("#ranking").addEventListener("click", (ev) => {
      const li = (ev.target as HTMLElement).closest<HTMLElement>("[data-id]");
      if (li) this.setScenario({ [this.rank]: [li.dataset.id!] });
    });
    this.el.addEventListener("change", (ev) => {
      const t = ev.target as HTMLInputElement;
      const toggle = <T>(set: Set<T>, v: T) => (t.checked ? set.add(v) : set.delete(v));
      if (t.dataset.stage) toggle(this.filters.stages, t.dataset.stage);
      else if (t.dataset.country) toggle(this.filters.countries, t.dataset.country);
      else if (t.dataset.strength) toggle(this.filters.strengths, t.dataset.strength as Strength);
      else return;
      this.handlers.onFilters(this.filters);
    });
    this.$("#country-clear").addEventListener("click", () => {
      this.filters.countries.clear();
      this.el.querySelectorAll<HTMLInputElement>("[data-country]").forEach((c) => (c.checked = false));
      this.handlers.onFilters(this.filters);
    });
  }

  private fillValues() {
    const kind = this.$<HTMLSelectElement>("#scn-kind").value as ScenarioKey;
    this.$("#scn-value").innerHTML = this.options(kind)
      .map(([id, label]) => `<option value="${esc(id)}">${esc(label)}</option>`)
      .join("");
  }

  private renderRanking() {
    const rows: Impact[] = [...this.doc.analysis.criticality[this.rank]].sort((a, b) => b.score - a.score).slice(0, 8);
    const max = rows[0]?.score || 1;
    const kind: ScenarioKey = this.rank;
    this.$("#ranking").innerHTML = rows
      .map(
        (r) => `<li data-id="${esc(r.id)}" title="Run this scenario">
          <span class="rank-name">${esc(this.label(kind, r.id))}</span>
          <span class="bar"><span style="width:${(r.score / max) * 100}%"></span></span>
          <span class="rank-score">${r.score}</span></li>`,
      )
      .join("");
  }

  /** Set the scenario from outside (e.g. the node panel) or from the sidebar. */
  setScenario(s: Scenario) {
    this.scenario = s;
    const chips = (Object.keys(s) as ScenarioKey[]).flatMap((k) =>
      (s[k] ?? []).map((id) => `<span class="chip">${esc(this.label(k, id))}<button data-remove="${k}:${esc(id)}" aria-label="Remove">×</button></span>`),
    );
    this.$("#scn-chips").innerHTML = chips.length ? chips.join("") + `<button class="link small" id="scn-clear">clear</button>` : "";
    this.handlers.onScenario(s);
  }

  showSummary(result: ScenarioResult | null) {
    const el = this.$("#scn-summary");
    if (!result) {
      el.innerHTML = "";
      return;
    }
    const count = (s: string) => Object.values(result.state).filter((x) => x === s).length;
    el.innerHTML = `<div class="summary">
      <span><span class="dot st-offline"></span>${count("offline")} offline</span>
      <span><span class="dot st-full"></span>${count("full")} fully</span>
      <span><span class="dot st-partial"></span>${count("partial")} partially impacted</span></div>`;
  }
}
