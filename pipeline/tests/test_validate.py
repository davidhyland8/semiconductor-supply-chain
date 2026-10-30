"""Validator tests. Fixtures use fictional companies so no real relationship is implied."""

import json

import pytest

from scg.schemas import validator
from scg.validate import normalise, validate_extraction

DOC = """Item 1A. Risk Factors
We rely on a single supplier, Acme Litho Corp., for our extreme ultra-
violet lithography systems, and we may not be able to find alternative
sources on acceptable terms."""


def record(**overrides):
    rec = {
        "source_id": "beta-fab-2025-annual",
        "supplier": {"mention": "Acme Litho Corp.", "node_id": "acme-litho"},
        "buyer": {"mention": "We", "node_id": "beta-fab"},
        "input": "euv-lithography",
        "excerpt": "We rely on a single supplier, Acme Litho Corp., for our extreme ultraviolet lithography systems",
        "locator": "Item 1A. Risk Factors",
        "strength": "disclosed",
        "has_alternatives": "no",
        "extractor": {"agent": "relationship-extractor", "date": "2026-10-30"},
    }
    rec.update(overrides)
    return rec


@pytest.fixture
def repo(tmp_path):
    seed, sources, cache = tmp_path / "seed", tmp_path / "sources", tmp_path / "sources" / "cache"
    cache.mkdir(parents=True)
    seed.mkdir()
    (seed / "nodes.csv").write_text("id,name\nacme-litho,Acme Litho\nbeta-fab,Beta Fab\n")
    (seed / "inputs.csv").write_text("id,name\neuv-lithography,EUV lithography\n")
    (sources / "sources.csv").write_text("id,url\nbeta-fab-2025-annual,https://example.com/ar\n")
    (cache / "beta-fab-2025-annual.txt").write_text(DOC)
    return tmp_path


def run(repo, *records):
    path = repo / "out.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return validate_extraction(
        path, seed_dir=repo / "seed", sources_dir=repo / "sources", cache_dir=repo / "sources" / "cache"
    )


def test_valid_record_passes(repo):
    report = run(repo, record())
    assert report.ok, report.errors
    assert report.records == 1


def test_normalise_joins_hyphenated_line_breaks_and_quotes():
    assert normalise("ultra-\n  violet “EUV”") == normalise('ultraviolet "euv"')


def test_paraphrased_excerpt_rejected(repo):
    report = run(repo, record(excerpt="Acme Litho is our only EUV lithography supplier"))
    assert any("not found verbatim" in e for e in report.errors)


def test_missing_cache_is_warning_not_error(repo):
    (repo / "sources" / "cache" / "beta-fab-2025-annual.txt").unlink()
    report = run(repo, record())
    assert report.ok
    assert any("not verified" in w for w in report.warnings)


def test_inferred_strength_not_allowed_in_extraction(repo):
    report = run(repo, record(strength="inferred"))
    assert not report.ok


def test_unknown_node_and_input_rejected(repo):
    report = run(
        repo,
        record(supplier={"mention": "Gamma", "node_id": "gamma"}, input="fairy-dust"),
    )
    assert any("supplier.node_id 'gamma'" in e for e in report.errors)
    assert any("input 'fairy-dust'" in e for e in report.errors)


def test_new_entity_needs_proposed_name(repo):
    bad = run(repo, record(supplier={"mention": "Gamma Gas", "node_id": None}))
    good = run(repo, record(supplier={"mention": "Gamma Gas", "node_id": None, "proposed_name": "Gamma Gas"}))
    assert not bad.ok
    assert good.ok, good.errors


def test_new_input_allowed_when_flagged(repo):
    assert run(repo, record(input="neon-gas", input_is_new=True)).ok


def test_anonymised_counterparty_needs_notes(repo):
    assert not run(repo, record(anonymised=True)).ok
    assert run(repo, record(anonymised=True, notes="Only EUV supplier named elsewhere in the filing.")).ok


def test_same_supplier_and_buyer_rejected(repo):
    report = run(repo, record(buyer={"mention": "Acme", "node_id": "acme-litho"}))
    assert any("same node" in e for e in report.errors)


def test_bad_json_line_reported(repo):
    path = repo / "out.jsonl"
    path.write_text("{not json\n")
    report = validate_extraction(path, seed_dir=repo / "seed", sources_dir=repo / "sources")
    assert any("invalid JSON" in e for e in report.errors)


@pytest.mark.parametrize(
    "evidence, ok",
    [
        ({"strength": "inferred", "reasoning": "Only commercial supplier of EUV scanners worldwide."}, True),
        ({"strength": "inferred"}, False),
        ({"strength": "disclosed", "excerpt": "We buy EUV systems from Acme.", "source_id": "doc-1"}, True),
        ({"strength": "reported", "excerpt": "We buy EUV systems from Acme."}, False),
    ],
)
def test_evidence_rules(evidence, ok):
    assert validator("evidence").is_valid(evidence) is ok


def test_edge_requires_evidence():
    edge = {
        "id": "acme-litho-beta-fab-euv",
        "supplier": "acme-litho",
        "buyer": "beta-fab",
        "input": "euv-lithography",
        "evidence": [],
        "has_alternatives": "no",
    }
    assert not validator("edge").is_valid(edge)
