# Semiconductor Supply Chain Map

An interactive map of the global semiconductor supply chain, with disruption scenarios. Companies are nodes, supply relationships are edges, and every edge carries its evidence (source, verbatim excerpt, strength label).

- `data/`: seed, extracted and built graph data (versioned)
- `schema/`: JSON Schemas for nodes, edges, evidence, sources and extraction output
- `pipeline/`: Python package `scg`: collection, extraction validation, promotion, graph build, analysis
- `web/`: static front end (Vite + TypeScript, Cytoscape.js, D3)
- `docs/`: [methodology](docs/methodology.md) and [data dictionary](docs/data-dictionary.md)

## Rebuilding the data

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### 1. ETO dataset

`data/raw/eto/` holds a pinned copy of the ETO Advanced Semiconductor Supply Chain Dataset (commit in `SOURCE_COMMIT`, checksums in `SHA256SUMS`), from [georgetown-cset/eto-chip-explorer](https://github.com/georgetown-cset/eto-chip-explorer/tree/main/data). It is licensed CC BY-NC 4.0 (see `data/raw/eto/LICENSE-NOTE.md`) and committed to the repo. Check it with:

```bash
cd data/raw/eto && shasum -a 256 -c SHA256SUMS
```

The build adds every ETO input, and every ETO company with market-share data, as a market catalogue. ETO companies that are also graph nodes are matched by `eto_provider_id` in `nodes.csv` or by `data/seed/eto_providers.csv`; `scg validate seed` flags name matches that are neither mapped nor skipped.

### 2. Source documents

SEC filings for the companies in `data/sources/sec_targets.csv` are downloaded from EDGAR and cached as text in `data/sources/cache/` (gitignored). SEC requires a contact email in the User-Agent:

```bash
SCG_SEC_CONTACT=you@example.com uv run scg collect sec
```

The registry `data/sources/sources.csv` records each document's URL, filing date and the SHA-256 of the cached text, so you can check a re-download against the version that was extracted.

### 3. Extraction

Relationships are extracted by the `relationship-extractor` Claude Code agent (`.claude/agents/relationship-extractor.md`). In a Claude Code session in this repo:

> Run the relationship-extractor on nvidia-10k-2026 and amd-10k-2025

It writes `data/extracted/<source_id>.jsonl` and validates it:

```bash
uv run scg validate extraction data/extracted/*.jsonl
```

The validator checks the schema, references to known nodes and inputs, and that every excerpt appears verbatim in the cached document.

### 4. Review and promotion

```bash
uv run scg status      # per-source state; --todo prints sources waiting for extraction
uv run scg entities    # unmatched companies across documents -> data/extracted/entities.csv
uv run scg review      # candidates needing a decision -> data/extracted/review.md
```

Decide each new company in `entities.csv` (`create`, `alias` or `ignore`, with a reason). Then decide each queued candidate in `data/extracted/decisions.csv` (accept, or reject, or correct an input, buyer or supplier, always with a reason). High-confidence candidates with nothing to check are promoted without a decision. Then merge and validate:

```bash
uv run scg promote
uv run scg validate seed
```

Hand-curated edges, including any `inferred` edge with its written reasoning, are edited directly in `data/seed/edges.csv` and `data/seed/evidence.csv`.

Inferred edges (defined with their reasoning in `pipeline/src/scg/inferred.py`) are regenerated with:

```bash
uv run scg add-inferred
```

### 5. Build

```bash
uv run scg build
```

This writes `data/build/graph.v<N>.json`: nodes, edges with evidence, inputs and precomputed analysis (chokepoints, single-company/stage/country criticality, ETO concentration, country share per stage). A new version is written only when content changes, and `data/build/CHANGELOG.md` lists what was added, removed or changed.

## Web app

Requires Node.js.

```bash
cd web && npm install
npm run dev      # http://localhost:5173
npm run build    # static site in web/dist
```

The app loads the latest `data/build/graph.v<N>.json`. Restart `npm run dev` after `scg build` writes a new version, so the dev server sees the new file. It has a layered view (one column per stage, in supply order) and a force-directed network view. Click a company to see its suppliers and customers grouped by input, with each edge's evidence: the verbatim excerpt and source link, or the written reasoning for inferred edges. Edges are solid when disclosed, dashed when reported and dotted when inferred.

Search also finds ETO inputs and ETO-only companies. An input's panel shows who sells it and their market shares; an ETO-only company's panel shows its market position and notes that it has no sourced relationships yet.

The Map view shades each country by its share of a chosen stage (from the ETO dataset; assembly has no source yet) or, during a scenario, by how many of its companies are impacted. Click a country for its share of every stage, the companies headquartered or producing there, and a button to take it offline.

Scenarios take companies, countries or stages offline. The TypeScript engine runs in the browser, colours each node as offline, fully impacted or partially impacted, and explains why. Stage, country and evidence-strength filters only hide elements; scenarios always run on the full graph.

## Tests

```bash
uv run pytest
cd web && npm install && npm test
```

The scenario engine exists in Python (`pipeline/src/scg/analysis/scenario.py`) and TypeScript (`web/src/scenario/propagate.ts`). Both run the shared test cases in `tests/fixtures/scenarios/`, and the TypeScript tests also replay every scenario precomputed in the latest build, so the two engines can't drift apart.
