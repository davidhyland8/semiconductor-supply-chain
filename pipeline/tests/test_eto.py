"""ETO market catalogue tests, on a fictional ETO snapshot and seed."""

import csv

import pytest

from scg import eto


def write(path, header, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def dirs(tmp_path):
    e, s = tmp_path / "eto", tmp_path / "seed"
    e.mkdir()
    s.mkdir()
    write(e / "inputs.csv", ["input_id", "input_name", "type", "stage_name", "market_share_chart_global_market_size_info"], [
        ["N19", "Lithography tools", "tool_resource", "", "$20 billion"],
        ["N20", "EUV tools", "tool_resource", "", ""],
        ["N26", "Wafers", "material_resource", "", ""],
        ["N8", "Crystal furnaces", "tool_resource", "", ""],
    ])
    write(e / "sequence.csv", ["input_id", "goes_into_id", "is_type_of_id"], [
        ["N20", "", "N19"],
        ["N8", "N26", ""],
    ])
    write(e / "providers.csv", ["provider_name", "alias", "provider_id", "provider_type", "country"], [
        ["NLD", "Netherlands", "P1", "country", ""],
        ["Lumen Litho", "", "P10", "organization", "NLD"],
        ["Quartzco", "", "P11", "organization", "JPN"],
        ["Conglomerate", "", "P12", "organization", "KOR"],
        ["Idle Corp", "", "P13", "organization", "USA"],
        ["Fabby", "Fabby Inc", "P14", "organization", "USA"],
        ["Various companies", "", "P15", "organization", "Various countries"],
    ])
    write(e / "provision.csv", ["provider_name", "provider_id", "provided_id", "share_provided", "year", "source"], [
        ["Lumen Litho", "P10", "N20", "100", "2025", "Analyst data (2025)"],
        ["Quartzco", "P11", "N8", "60", "2022", "Analyst data (2022)"],
        ["Quartzco", "P11", "N26", "", "", ""],
        ["Quartzco", "P11", "N19", "", "", ""],
        ["Conglomerate", "P12", "N26", "20", "2022", ""],
        ["Fabby", "P14", "N26", "", "", ""],
        ["Various companies", "P15", "N26", "80", "2022", ""],
        ["NLD", "P1", "N20", "100", "2025", ""],
    ])
    write(s / "nodes.csv", ["id", "name", "kind", "stage", "aliases", "eto_provider_id"], [
        ["lumen", "Lumen Litho", "company", "equipment", "", "P10"],
        ["fabby-fab", "Fabby Fab", "company", "fabrication", "", ""],
        ["fabby-design", "Fabby Design", "company", "chip_design", "Fabby Inc", ""],
    ])
    write(s / "inputs.csv", ["id", "name", "stage", "eto_id"], [["euv", "EUV", "equipment", "N20"]])
    write(s / "eto_providers.csv", eto.MAP_FIELDS, [
        ["P12", "", "", "skip", "Bundles several business units."],
    ])
    return e, s


def test_input_stage_follows_type_hierarchy_then_type(dirs):
    e, _ = dirs
    stages = eto.input_stages(e)
    assert stages["N20"] == "equipment"  # a type of lithography tools (N19)
    assert stages["N26"] == "materials"
    assert stages["N8"] == "equipment"  # goes into wafers, but is a tool


def test_name_match_without_mapping_is_an_error(dirs):
    e, s = dirs
    errors = eto.check_mapping(s, e)
    assert len(errors) == 1 and "P14" in errors[0] and "fabby-design" in errors[0]


def test_mapping_rows_need_reason_and_known_node(dirs):
    e, s = dirs
    write(s / "eto_providers.csv", eto.MAP_FIELDS, [
        ["P14", "", "nobody", "map", ""],
    ])
    errors = eto.check_mapping(s, e)
    assert any("reason is required" in x for x in errors)
    assert any("unknown node 'nobody'" in x for x in errors)


def test_market_attaches_positions_and_catalogues_the_rest(dirs):
    e, s = dirs
    write(s / "eto_providers.csv", eto.MAP_FIELDS, [
        ["P12", "", "", "skip", "Bundles several business units."],
        ["P14", "", "fabby-design", "map", "Same company."],
        ["P14", "N26", "fabby-fab", "map", "Wafers belong to the fab unit."],
    ])
    m = eto.market(s, e)
    assert m["node_positions"]["lumen"] == [{"input": "N20", "share": 1.0, "year": "2025", "source": 0}]
    assert m["sources"][0] == "Analyst data (2025)"
    assert m["node_positions"]["fabby-fab"][0]["input"] == "N26"  # per-input override
    assert "fabby-design" not in m["node_positions"]

    companies = {c["id"]: c for c in m["companies"]}
    # Skipped, mapped, empty and "various" providers are not catalogued.
    assert list(companies) == ["quartzco"]
    q = companies["quartzco"]
    assert q["hq_country"] == "JP"
    assert q["stage"] == "equipment"  # two tool positions beat one material position
    assert q["positions"][0] == {"input": "N8", "share": 0.6, "year": "2022", "source": 1}

    inputs = {i["id"]: i for i in m["inputs"]}
    assert inputs["N20"]["graph_inputs"] == ["euv"]
    assert inputs["N19"]["children"] == ["N20"]
    assert inputs["N8"]["goes_into"] == ["N26"]
    wafers = inputs["N26"]["suppliers"]
    assert {"name": "Conglomerate", "share": 0.2} in wafers  # skipped providers still listed, unlinked
    assert {"name": "Quartzco", "share": None, "company": "quartzco"} in wafers
    assert m["skipped"][0]["name"] == "Conglomerate"
    assert not any(x["name"].startswith("Various") for x in wafers)


def test_market_ids_avoid_graph_node_ids(dirs):
    e, s = dirs
    write(s / "nodes.csv", ["id", "name", "kind", "stage", "aliases", "eto_provider_id"], [
        ["quartzco", "Quartz Holdings", "company", "materials", "", ""],
        ["lumen", "Lumen Litho", "company", "equipment", "", "P10"],
    ])
    ids = {c["id"] for c in eto.market(s, e)["companies"]}
    assert "quartzco-eto" in ids and "quartzco" not in ids
