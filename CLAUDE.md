# Semiconductor supply chain map

Interactive graph of the chip supply chain with disruption scenarios. Read `docs/methodology.md` before changing data or scenario logic.

## Layout

- `schema/` – JSON Schemas (authoritative data contract)
- `data/` – `seed/` hand-curated, `sources/` document registry + cache, `extracted/` agent output, `build/` built graph
- `pipeline/src/scg/` – Python package (uv). CLI: `uv run scg ...`
- `web/` – static front end (Vite + TypeScript, Cytoscape.js, D3)
- `.claude/agents/relationship-extractor.md` – extraction agent; invoke it with source_ids

## Commands

- `uv run pytest` – Python tests
- `uv run scg validate extraction data/extracted/<id>.jsonl`

## Rules

- Never invent relationships or figures. No source → `strength: inferred` with written reasoning.
- Excerpts are verbatim from the source and ≤ ~50 words.
- Nodes are one per business unit (`samsung-foundry`, not `samsung`).
- Scenario logic exists in Python and TypeScript. Change both together and keep `tests/fixtures/scenarios/` passing in both.
- Test fixtures use fictional companies, so tests never imply real relationships.
