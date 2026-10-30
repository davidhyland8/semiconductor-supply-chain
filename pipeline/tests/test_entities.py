"""Entity resolution and review-queue tests, with fictional companies."""

import json

from scg import entities, review


def test_canonical_ignores_case_punctuation_and_legal_suffixes():
    assert entities.canonical("Taiwan Widget Manufacturing Co., Ltd.") == "taiwanwidgetmanufacturing"
    assert entities.canonical("The Gamma Group Holdings Inc.") == "gamma"
    assert entities.canonical("A&B Corp") == "aandb"
    assert entities.keys_of("King Widget Electronics (KWE)") == ["kingwidgetelectronics", "kwe"]


def write_jsonl(path, recs):
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def rec(source, supplier, buyer, **kw):
    return {
        "source_id": source,
        "supplier": supplier,
        "buyer": buyer,
        "input": "x",
        "excerpt": f"{supplier['mention']} supplies {buyer['mention']}.",
        "locator": "Item 1",
        "strength": "disclosed",
        "has_alternatives": "unknown",
        "confidence": "high",
        "extractor": {"agent": "t", "date": "2026-10-30"},
        **kw,
    }


def test_refresh_groups_mentions_across_documents_and_keeps_decisions(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "nodes.csv").write_text("id,name,aliases\nbeta-fab,Beta Fab,\n")
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    fab = {"mention": "Beta", "node_id": "beta-fab"}
    write_jsonl(a, [rec("a", {"mention": "Gamma Gas Co., Ltd.", "node_id": None, "proposed_name": "Gamma Gas"}, fab)])
    write_jsonl(b, [rec("b", {"mention": "Gamma Gas Inc.", "node_id": None}, fab)])
    out = tmp_path / "entities.csv"

    [row] = entities.refresh([a, b], seed, out)
    assert row["key"] == "gammagas"
    assert row["mentions"] == "Gamma Gas Co., Ltd.;Gamma Gas Inc."
    assert row["sources"] == "a;b"
    assert row["candidates"] == "2"

    row.update(decision="ignore", reason="Out of scope")
    entities._write(out, entities.ENTITY_FIELDS, [row])
    [row] = entities.refresh([a, b], seed, out)
    assert (row["decision"], row["reason"]) == ("ignore", "Out of scope")


def test_check_flags_incomplete_decisions(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "nodes.csv").write_text("id,name\nbeta-fab,Beta Fab\n")
    path = tmp_path / "entities.csv"
    path.write_text(
        ",".join(entities.ENTITY_FIELDS) + "\n"
        "gammagas,Gamma Gas,Gamma Gas,a,1,,create,gamma-gas,Gamma Gas,company,materials,,,\n"
        "deltaco,Delta,Delta,a,1,,alias,nobody,,,,,,Same firm\n"
    )
    errors = entities.check(path, seed)
    assert any("reason is required" in e for e in errors)
    assert any("create needs hq_country" in e for e in errors)
    assert any("alias needs an existing node_id" in e for e in errors)


def test_review_states(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "nodes.csv").write_text("id,name,aliases\nacme,Acme,\nbeta-fab,Beta Fab,\n")
    (seed / "inputs.csv").write_text("id,name\nx,X\n")
    (seed / "evidence.csv").write_text("edge_id,source_id,excerpt\nacme-to-beta-fab-x,a,Acme supplies Old.\n")
    acme, fab = {"mention": "Acme", "node_id": "acme"}, {"mention": "Beta", "node_id": "beta-fab"}
    f = tmp_path / "a.jsonl"
    write_jsonl(f, [
        rec("a", acme, fab),
        rec("a", acme, fab, confidence="medium", excerpt="Medium one."),
        rec("a", {"mention": "Gamma", "node_id": None}, fab),
        rec("a", acme, {"mention": "Old", "node_id": "beta-fab"}),
        rec("a", acme, fab, has_alternatives="no", excerpt="Sole source."),
    ])
    decisions = {("a", 5): {"decision": "accept"}}
    states = [c.state for c in review.candidates([f], seed, decisions)]
    assert states == ["auto", "needs_review", "blocked", "promoted", "accepted"]
    md = review.review_markdown(review.candidates([f], seed, decisions), {"acme": "Acme"})
    assert "2 candidates need a decision" in md and "`a,2,accept,,,,,`" in md


def test_self_references_are_not_aliases(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "nodes.csv").write_text("id,name,aliases\nbeta-fab,Beta Fab,\n")
    f = tmp_path / "a.jsonl"
    write_jsonl(f, [rec("a", {"mention": "we", "node_id": None, "proposed_name": "Gamma Tools"}, {"mention": "Beta", "node_id": "beta-fab"})])
    [row] = entities.refresh([f], seed, tmp_path / "entities.csv")
    assert (row["key"], row["mentions"]) == ("gammatools", "")
