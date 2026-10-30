# Data dictionary

The JSON Schemas in `schema/` are authoritative. This page maps them to files.

| File | Schema | Notes |
|---|---|---|
| `data/seed/nodes.csv` | `node.schema.json` | Hand-curated nodes. `aliases` is `;`-separated. |
| `data/seed/production.csv` | – | Where each node produces: `node_id,country,share,primary,source_id,excerpt,locator,as_of,notes`. Merged into `production_countries`; excerpts verified like edge evidence. |
| `data/seed/inputs.csv` | – | Controlled vocabulary for edge `input`: `id,name,stage,eto_id` |
| `data/seed/edges.csv` | `edge.schema.json` | One row per edge. Evidence lives in `evidence.csv`. |
| `data/seed/evidence.csv` | `evidence.schema.json` | One row per piece of evidence, keyed by `edge_id`. |
| `data/seed/groups.csv` | – | Parent groups for business units: `id,name,hq_country` |
| `data/seed/eto_providers.csv` | – | ETO provider mapping overrides: `eto_provider_id,eto_input_id,node_id,action,reason`. `action` is `map` or `skip`; a row with `eto_input_id` moves only that position. `reason` is required. |
| `data/sources/sources.csv` | `source.schema.json` | Registry of source documents. |
| `data/sources/sec_targets.csv` | – | Companies whose latest 10-K/20-F `scg collect sec` fetches |
| `data/extracted/decisions.csv` | – | Review decisions: reject, or override supplier/buyer/input/alternatives, with a reason |
| `data/sources/cache/<id>.txt` | – | Cached document text (gitignored). Used to verify excerpts. |
| `data/extracted/<source_id>.jsonl` | `extraction.schema.json` | Candidate relationships awaiting review. |
| `data/build/graph.v<N>.json` | – | Built graph loaded by the web app: nodes, edges with evidence, precomputed analysis. |

`analysis.stage_country_shares.<stage>` in the build:

| Field | Meaning |
|---|---|
| `shares` | Country (ISO alpha-2, or `EU` for the bloc) to share of the stage, 0–1 |
| `other_share` | ETO's unallocated "various countries" share |
| `basis` | What the figure measures (e.g. capacity by site location) |
| `years`, `source` | Data year(s) and citation |
| `note` | Present instead of `shares` when the stage has no source |
| `data/build/country_shares.json` | – | Country share per stage/input, with source and `as_of`. |

Identifiers are kebab-case (`tsmc`, `samsung-foundry`). Countries are ISO 3166-1 alpha-2 (`TW`, `KR`, `NL`). Dates are `YYYY[-MM[-DD]]`.

`market` in the build (ETO market catalogue; see methodology):

| Field | Meaning |
|---|---|
| `companies[]` | ETO companies not in the graph: `id, name, eto_provider_id, hq_country, aliases, stage, positions[]` |
| `inputs[]` | Every ETO input: `id, name, type, stage, description, market_size, parent, children, goes_into, graph_inputs, suppliers[], country_shares, company_hhi, year` |
| `positions[]` / node `market_positions[]` | `input` (ETO id), `share` (0–1 or null when ETO lists the supplier without a share), `year`, `source` (index into `sources`) |
| `sources` | ETO's per-row source citations |
| `skipped` | Providers skipped in `eto_providers.csv`, with reasons |
| `citation`, `license` | How to credit the dataset |
