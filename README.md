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

`data/raw/eto/` holds a pinned copy of the ETO Advanced Semiconductor Supply Chain Dataset (commit in `SOURCE_COMMIT`, checksums in `SHA256SUMS`), from [georgetown-cset/eto-chip-explorer](https://github.com/georgetown-cset/eto-chip-explorer/tree/main/data).

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

Review decisions (reject, or correct an input, buyer or supplier, always with a reason) go in `data/extracted/decisions.csv`. Then merge candidates into the seed graph and validate it:

```bash
uv run scg promote
uv run scg validate seed
```

Hand-curated edges, including any `inferred` edge with its written reasoning, are edited directly in `data/seed/edges.csv` and `data/seed/evidence.csv`.

## Tests

```bash
uv run pytest
```
