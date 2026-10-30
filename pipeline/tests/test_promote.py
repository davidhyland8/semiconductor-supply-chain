"""Promotion tests with fictional companies."""

import json

import pytest

from scg.promote import promote
from scg.seed import load_edges


def cand(line_overrides=None, **kw):
    rec = {
        "source_id": "beta-20f-2025",
        "supplier": {"mention": "Acme", "node_id": "acme-litho"},
        "buyer": {"mention": "We", "node_id": "beta-fab"},
        "input": "euv-lithography",
        "excerpt": "We purchase all of our EUV scanners from Acme Litho.",
        "locator": "Item 4",
        "strength": "disclosed",
        "has_alternatives": "unknown",
        "extractor": {"agent": "t", "date": "2026-10-30"},
    }
    rec.update(kw)
    return rec


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "seed").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "sources.csv").write_text(
        "id,url,published\nbeta-20f-2025,https://example.com/20f,2026-04-15\n"
    )
    return tmp_path


def run(repo, records, decisions=""):
    f = repo / "beta-20f-2025.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    d = repo / "decisions.csv"
    d.write_text("source_id,line,decision,set_supplier,set_buyer,set_input,set_has_alternatives,reason\n" + decisions)
    return promote([f], repo / "seed", repo / "sources", d)


def test_promote_creates_edge_and_evidence(repo):
    res = run(repo, [cand()])
    assert (res.edges_added, res.evidence_added) == (1, 1)
    [edge] = load_edges(repo / "seed")
    assert edge["id"] == "acme-litho-to-beta-fab-euv-lithography"
    assert edge["as_of"] == "2026-04"
    assert edge["evidence"][0]["url"] == "https://example.com/20f"


def test_promote_is_idempotent(repo):
    run(repo, [cand()])
    res = run(repo, [cand()])
    assert (res.edges_added, res.evidence_added) == (0, 0)


def test_two_excerpts_one_edge_and_strongest_alternatives(repo):
    run(repo, [cand(), cand(excerpt="Acme Litho is our sole EUV supplier.", has_alternatives="no")])
    [edge] = load_edges(repo / "seed")
    assert len(edge["evidence"]) == 2
    assert edge["has_alternatives"] == "no"


def test_reject_and_override(repo):
    res = run(
        repo,
        [cand(), cand(input="duv-lithography")],
        "beta-20f-2025,1,reject,,,,,Duplicate of a better passage\n"
        "beta-20f-2025,2,accept,,,euv-lithography,,Passage is about EUV scanners\n",
    )
    assert res.rejected == ["beta-20f-2025:1 (Duplicate of a better passage)"]
    [edge] = load_edges(repo / "seed")
    assert edge["input"] == "euv-lithography"
    assert edge["evidence"][0]["reasoning"] == "Passage is about EUV scanners"


def test_override_needs_reason(repo):
    with pytest.raises(ValueError):
        run(repo, [cand()], "beta-20f-2025,1,accept,,,duv-lithography,,\n")


def test_null_node_id_resolved_through_alias(repo):
    (repo / "seed" / "nodes.csv").write_text("id,name,aliases\ngamma-gas,Gamma Gas,Gamma Gas Co.;GGC\n")
    res = run(repo, [cand(supplier={"mention": "Gamma Gas Co.", "node_id": None, "proposed_name": "Gamma"})])
    assert res.edges_added == 1
    assert load_edges(repo / "seed")[0]["supplier"] == "gamma-gas"


def test_unresolved_entity_skipped(repo):
    res = run(repo, [cand(supplier={"mention": "Gamma Gas", "node_id": None, "proposed_name": "Gamma Gas"})])
    assert res.edges_added == 0
    assert "Gamma Gas" in res.skipped[0]
