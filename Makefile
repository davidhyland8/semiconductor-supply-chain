# Rebuild everything from a clean clone: `make data && make web`.
# Collection and extraction are not part of this: they need network access and a
# Claude Code session (see README). This rebuilds the graph from the committed
# seed data and ETO snapshot.

.PHONY: all data web test check check-eto dev clean

all: data web

check-eto:
	cd data/raw/eto && shasum -a 256 -c --quiet SHA256SUMS

data: check-eto
	uv sync --frozen
	uv run scg promote
	uv run scg add-inferred
	uv run scg validate seed
	uv run scg build
	uv run pytest -q

web:
	cd web && npm ci && npm test && npm run build

test:
	uv run pytest -q
	cd web && npm test

# CI: the committed seed must reproduce the committed build exactly.
check: check-eto
	uv sync --frozen
	uv run scg promote
	uv run scg add-inferred
	git diff --exit-code -- data/seed
	uv run scg validate seed
	uv run scg build --check
	uv run pytest -q

dev:
	cd web && npm run dev

clean:
	rm -rf web/dist
