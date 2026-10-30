"""Seed loader/validator tests with fictional companies."""

import pytest

from scg.seed import load_edges, load_nodes, parse_production_countries, validate_seed

NODES = """id,name,kind,parent,stage,role,hq_country,production_countries,aliases,ticker,eto_provider_id,notes
acme-litho,Acme Litho,company,,equipment,equipment,NL,NL*,Acme;Acme Litho BV,,P88,
beta-fab,Beta Fab,company,beta-group,fabrication,foundry,TW,TW:0.8;US:0.2,,,,
gadgets,Gadgets,product_category,,assembly_end_products,end_market,,,,,,
"""
EDGE_HEADER = "id,supplier,buyer,input,has_alternatives,weight_value,weight_metric,weight_basis,as_of,notes\n"
EVIDENCE_HEADER = "edge_id,source_id,url,excerpt,locator,strength,reasoning\n"


@pytest.fixture
def repo(tmp_path):
    seed, cache = tmp_path / "seed", tmp_path / "sources" / "cache"
    seed.mkdir()
    cache.mkdir(parents=True)
    (seed / "nodes.csv").write_text(NODES)
    (seed / "groups.csv").write_text("id,name,hq_country\nbeta-group,Beta Group,TW\n")
    (seed / "inputs.csv").write_text("id,name\neuv-lithography,EUV\nlogic-foundry-leading,Foundry\n")
    (tmp_path / "sources" / "sources.csv").write_text("id,url\nbeta-20f-2025,https://example.com\n")
    (cache / "beta-20f-2025.txt").write_text("We purchase all of our EUV scanners from Acme Litho.\n")
    return tmp_path


def write(repo, edges="", evidence=""):
    (repo / "seed" / "edges.csv").write_text(EDGE_HEADER + edges)
    (repo / "seed" / "evidence.csv").write_text(EVIDENCE_HEADER + evidence)
    return validate_seed(repo / "seed", repo / "sources", repo / "sources" / "cache")


GOOD_EDGE = "acme-beta-euv,acme-litho,beta-fab,euv-lithography,no,0.9,share_of_buyer_input,Beta 20-F,2025,\n"
GOOD_EV = "acme-beta-euv,beta-20f-2025,,We purchase all of our EUV scanners from Acme Litho.,Item 4,disclosed,\n"


def test_parse_production_countries():
    assert parse_production_countries("TW*;US:0.2;JP") == [
        {"country": "TW", "primary": True},
        {"country": "US", "share": 0.2},
        {"country": "JP"},
    ]


def test_load_nodes_splits_lists(repo):
    nodes = {n["id"]: n for n in load_nodes(repo / "seed")}
    assert nodes["acme-litho"]["aliases"] == ["Acme", "Acme Litho BV"]
    assert nodes["beta-fab"]["production_countries"][0] == {"country": "TW", "share": 0.8}
    assert "hq_country" not in nodes["gadgets"]


def test_valid_seed(repo):
    report = write(repo, GOOD_EDGE, GOOD_EV)
    assert report.ok, report.errors
    edge = load_edges(repo / "seed")[0]
    assert edge["weight"] == {"value": 0.9, "metric": "share_of_buyer_input", "basis": "Beta 20-F"}


def test_edge_without_evidence_rejected(repo):
    assert not write(repo, GOOD_EDGE).ok


def test_inferred_needs_reasoning(repo):
    edge = "acme-beta-euv,acme-litho,beta-fab,euv-lithography,unknown,,,,,\n"
    assert not write(repo, edge, "acme-beta-euv,,,,,inferred,\n").ok
    ok = write(repo, edge, "acme-beta-euv,,,,,inferred,Acme is the only maker of EUV scanners in this fictional world.\n")
    assert ok.ok, ok.errors


def test_excerpt_must_be_verbatim(repo):
    ev = "acme-beta-euv,beta-20f-2025,,Acme Litho supplies all our EUV scanners.,Item 4,disclosed,\n"
    assert any("verbatim" in e for e in write(repo, GOOD_EDGE, ev).errors)


def test_unknown_references_rejected(repo):
    edge = "e1,acme-litho,nobody,fairy-dust,no,,,,,\n"
    report = write(repo, edge, "e1,,,,,inferred,Placeholder reasoning for a fictional edge.\n")
    assert any("buyer 'nobody'" in e for e in report.errors)
    assert any("input 'fairy-dust'" in e for e in report.errors)


def test_duplicate_triple_and_orphan_evidence(repo):
    dup = GOOD_EDGE + GOOD_EDGE.replace("acme-beta-euv", "acme-beta-euv-2", 1)
    ev = GOOD_EV + GOOD_EV.replace("acme-beta-euv", "acme-beta-euv-2", 1) + GOOD_EV.replace("acme-beta-euv", "ghost", 1)
    errors = write(repo, dup, ev).errors
    assert any("same supplier/buyer/input" in e for e in errors)
    assert any("unknown edge_id 'ghost'" in e for e in errors)


def test_unknown_parent_rejected(repo):
    (repo / "seed" / "groups.csv").write_text("id,name,hq_country\n")
    assert any("parent 'beta-group'" in e for e in write(repo, GOOD_EDGE, GOOD_EV).errors)
