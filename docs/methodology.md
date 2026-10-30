# Methodology

## Scope

The graph covers the semiconductor supply chain in seven stages:

| Stage id | Stage | Example roles |
|---|---|---|
| `design_tools_ip` | Design tools and IP | eda, ip |
| `chip_design` | Chip designers | fabless, idm |
| `equipment` | Equipment | equipment |
| `materials` | Materials and inputs | wafers, photoresist, gases_chemicals, substrates |
| `fabrication` | Fabrication | foundry, memory |
| `packaging_test` | Packaging and test | osat, advanced_packaging |
| `assembly_end_products` | Assembly and end products | ems, oem, end_market |

## Nodes: one per business

A node is **one business in one stage**. Companies that span stages are split into units that share a `parent`:

- Samsung → `samsung-lsi` (chip_design), `samsung-foundry` (fabrication/foundry), `samsung-memory` (fabrication/memory), `samsung-electronics-devices` (assembly_end_products)
- Intel → `intel-products` (chip_design/idm), `intel-foundry` (fabrication/foundry)
- Apple → `apple-silicon` (chip_design/fabless), `apple-devices` (assembly_end_products/oem)

Without the split, "Samsung Foundry offline" would wrongly take out Samsung's memory customers too. The UI can merge units back into their parent for display.

End markets (`ai-servers`, `smartphones`, `pcs`, `automotive`) are nodes with `kind: product_category`. They are sinks that show how far a disruption reaches.

## Edges and evidence

An edge means **supplier provides `input` to buyer**. One edge per (supplier, buyer, input). `input` comes from the controlled vocabulary in `data/seed/inputs.csv`, built from the ETO input taxonomy where it fits.

Each edge has one or more pieces of evidence, each labelled:

| Strength | Meaning | Required fields |
|---|---|---|
| `disclosed` | Stated in a filing (10-K, 20-F, annual report) | source, verbatim excerpt |
| `reported` | Press release, news, earnings call, investor deck, market research | source, verbatim excerpt |
| `inferred` | No direct source; believed from industry structure | written reasoning |

No relationship or figure is invented. Anything without a source is `inferred`, and the reasoning is recorded. Excerpts are verbatim and short (at most ~50 words), enough to support the claim without reproducing the source.

Optional dependency data on an edge:

- `weight`: a published share, either `share_of_buyer_input` (e.g. 90% of the buyer's wafers come from this supplier) or `share_of_supplier_revenue` (e.g. customer X is 19% of the supplier's revenue), with its basis. Never estimated. A weight may be **derived** from figures the same source states (e.g. iPhone net sales ÷ total net sales), and the basis must then show the calculation. It may also come from combining two passages of one document, e.g. "TSMC is the only customer above 10%" plus "one customer was 19%".
- `has_alternatives`: `yes`, `no` or `unknown`, i.e. whether the buyer has other qualified sources for this input.

### End-market edges

An end-market node (`smartphones`, `pcs`, `ai-servers`, `automotive`) is linked from the company that **sells into** that market, i.e. a device maker, an EMS or a chip designer, often with a segment revenue share as weight. A foundry's revenue split by platform (e.g. TSMC: 29% smartphone) is market exposure, not a supply flow, and is rejected. Foundries reach end markets through the designers they supply.

### Inferred edges

Inferred edges are defined in code (`pipeline/src/scg/inferred.py`), so each rule and its reasoning can be reviewed, and are written by `scg add-inferred`. They are used in two cases:

1. **Dominant toolmakers.** If ETO/TechInsights 2025 data gives a toolmaker a dominant share of a tool category (ASML 100% of EUV, TEL 92.6% of coater/developer tracks, KLA 85.9% of defect inspection, Applied 82.4% of PVD, Lam 41% of dry etch), each major fab using that process step is linked to it. An inferred edge is skipped wherever a stated source already covers it.
2. **Close-but-unstated evidence.** A source describes co-development plus local production but stops short of a supply contract (e.g. TOK, Shin-Etsu and JSR photoresist for TSMC). The excerpt is kept, and the label stays `inferred`.

Every figure carries an `as_of` date. The ETO dataset is older than current filings, so its shares are shown with their date and replaced per stage where newer public figures exist.

## Countries

Each node has `hq_country` and `production_countries` (with shares where published). Country scenarios use **production location**. If a node has no production countries recorded, the scenario falls back to `hq_country` and the UI flags the fallback.

## Scenario propagation

A scenario takes a set of companies, stages or countries offline. Every node ends in one of four states: `ok`, `offline`, `partial` or `full`.

1. **Seeds.** Company and stage scenarios mark the selected nodes `offline`. In a country scenario, a node goes `offline` if that country is its only production country or holds at least 50% of its production. A smaller share makes the node `partial`.
2. **Inputs.** For each buyer, incoming edges are grouped by `input`. For one input, a supplier is **lost** if it is `offline` or `full`, and **degraded** if it is `partial`.
3. **Buyer state for that input:**
   - **partial** if every known supplier is lost but every lost edge says `has_alternatives: yes`, meaning the buyer has alternatives the graph doesn't record (`alternatives_unrecorded`);
   - **full** if every known supplier of the input is lost, or
   - **full** if a lost edge has `has_alternatives: no`, or
   - **full** if the known `share_of_buyer_input` weights of lost edges sum to at least 0.5;
   - otherwise **partial** if any supplier is lost or degraded;
   - otherwise unaffected.
4. **Node state.** A buyer takes the worst state across its inputs.
5. **Repeat until nothing changes.** States only get worse (ok → partial → full), so this terminates even if the graph has cycles.
6. **Explanation.** Each impacted node records which input and which suppliers caused its state, so the UI can show the path.

Limitations: the graph only knows the suppliers it has evidence for. "Every known supplier lost" can overstate impact where unrecorded alternatives exist. The UI labels results as "based on known suppliers".

The logic is implemented twice, in Python (`pipeline/src/scg/analysis/scenario.py`) and TypeScript (`web/src/scenario/`). Both run the shared test cases in `tests/fixtures/scenarios/` so they can't drift apart.

Country scenarios use these rules:
- A node goes `offline` if every production site is in an offline country, if a `primary` site is, or if the offline countries' shares sum to at least 50%.
- Otherwise a hit on any of its sites makes it `partial`.
- A node with no recorded production countries uses its HQ country instead, with rule `country_offline_hq_fallback`.
- Product categories have no location and are only affected through their suppliers.

## Concentration

- **Chokepoints:** inputs where a buyer has a single known supplier (or `has_alternatives: no`), and inputs where one supplier serves most buyers in the graph.
- **HHI** per ETO input from company shares and from country shares. ETO's "Various" buckets are excluded. HHI = Σ(share × 100)², from 0 to 10,000; above 2,500 is highly concentrated.
- **Country share per stage** (the map). The figures measure different things per stage, and the map states the basis for each:
  - *Design tools & IP, chip design, equipment, materials:* each top-level ETO input's country shares, weighted by its market size. The inputs are listed in `STAGE_INPUTS` in `analysis/concentration.py` and chosen so none is a sub-type of another.
  - *Fabrication, packaging & test:* ETO's stage-level shares of capacity by site location (2022, citing SIA), i.e. where fabs and ATP plants are, not where their owners are headquartered.
  - *Assembly & end products:* no public country breakdown found for the whole stage (sources cover single products such as smartphones), so it is shown as a gap rather than estimated.
  - ETO's "various countries" bucket is kept separately as `other_share`, not spread across named countries. Where ETO reports the EU as a bloc, the map shades every EU member with the bloc's figure, hatched, and never presents it as a member's own share.
- **Scenario impact on the map:** for each country, the share of companies headquartered there that a scenario impacts (fully or offline = 1, partially = ½). Countries taken offline are drawn black.
- **Criticality:** every single company, stage and country is taken offline in turn. Score = offline nodes (other than the named company) + fully impacted nodes + ½ × partially impacted nodes. It is precomputed into the build.

## ETO market catalogue

The ETO dataset says which companies sell each input and their global market share. It does not say who buys from them, so **market share is never turned into a supply edge** on its own. The only exception is the curated rules in `inferred.py`, which are written out with their reasoning.

- **Companies already in the graph** get their ETO positions attached as `market_positions`. Matching uses `eto_provider_id` in `nodes.csv`, or a row in `data/seed/eto_providers.csv`.
- **`eto_providers.csv`** maps or skips ETO providers, and can move a single position to another business unit. Every row needs a written reason. For example:
  - ETO's "Samsung" is skipped: its positions span Samsung affiliates and can't be given to one unit.
  - Mentor Graphics maps to Siemens EDA.
  - Intel's photomasks go to Intel Foundry.
- **Name check:** `scg validate seed` fails if an ETO provider's name or alias matches a graph node but the provider is neither mapped nor skipped. This catches duplicates.
- **Other ETO companies** with at least one market position go into a market catalogue (`market.companies`). They are not graph nodes and take no part in scenarios or criticality, because they have no recorded relationships. Their stage is inferred from what they sell: the most common stage among their inputs. ETO providers listed with no positions are left out.
- **ETO inputs** (`market.inputs`) carry:
  - the type hierarchy (`parent`, `children`) and where each input `goes_into`;
  - every listed supplier, with a share where ETO gives one;
  - country shares and company HHI;
  - which graph inputs correspond to them (`graph_inputs`).
- **Stage of an ETO input:** the stage of the top-level input it is a type of (`STAGE_INPUTS`). Failing that, ETO's own stage. Failing that, its type: tool goes to equipment, material to materials, design resource to chip design.
- **Licence:** the dataset is CC BY-NC 4.0 (`data/raw/eto/LICENSE-NOTE.md`). The app credits it wherever its figures appear.

## Extraction

Relationships beyond the hand-curated seed come from the `relationship-extractor` Claude Code agent (`.claude/agents/relationship-extractor.md`). The flow:

1. Register the document in `data/sources/sources.csv` and cache its text at `data/sources/cache/<source_id>.txt`.
2. The agent writes candidate records to `data/extracted/<source_id>.jsonl` (`schema/extraction.schema.json`).
3. `scg validate extraction` checks the schema and the references, and confirms each excerpt appears verbatim in the cached text.
4. A human reviews the candidates. Rejections and corrections go in `data/extracted/decisions.csv` with a reason. `scg promote` then merges the rest into `data/seed/edges.csv` and `evidence.csv`. Entities with no `node_id` are matched through node names and aliases. Candidates still unmatched are skipped and listed.

Anonymised counterparties ("Customer A: 22% of revenue") are skipped, not guessed. Their shares are listed in the extraction summaries, so a later pass can identify them from other public sources.

Extraction only produces `disclosed` or `reported` evidence. `inferred` is reserved for human curation.
