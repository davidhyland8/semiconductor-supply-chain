"""Concentration and graph-metric tests. Fictional data except the ETO parsing check."""

import csv

import pytest

from scg.analysis.concentration import hhi, input_concentration, parse_market_size, stage_country_shares
from scg.analysis.graph_metrics import chokepoints, criticality


def test_hhi():
    assert hhi([100]) == 10000
    assert hhi([50, 50]) == 5000
    assert hhi([]) == 0


@pytest.mark.parametrize("text, value", [
    ("$13 billion (2025)", 13e9),
    ("$852.6 million (2025)", 852.6e6),
    ("$3.3 billion (all photoresists)", 3.3e9),
    ("", None),
])
def test_parse_market_size(text, value):
    assert parse_market_size(text) == value


@pytest.fixture
def eto(tmp_path):
    def write(name, header, rows):
        with (tmp_path / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    ih = ["input_id", "input_name", "type", "market_share_chart_global_market_size_info"]
    write("inputs.csv", ih, [["N84", "EDA", "tool", "$3 billion"], ["N85", "IP", "material", "$1 billion"]])
    write("providers.csv", ["provider_name", "provider_id", "provider_type"], [
        ["USA", "P1", "country"], ["GBR", "P2", "country"], ["Various countries", "P3", "country"],
        ["Acme EDA", "P10", "organization"], ["Beta EDA", "P11", "organization"], ["Various companies", "P12", "organization"],
    ])
    write("provision.csv", ["provider_name", "provider_id", "provided_id", "share_provided", "year"], [
        ["Acme EDA", "P10", "N84", "60", "2025"], ["Beta EDA", "P11", "N84", "30", "2025"],
        ["Various companies", "P12", "N84", "10", "2025"],
        ["USA", "P1", "N84", "90", "2025"], ["Various countries", "P3", "N84", "10", "2025"],
        ["USA", "P1", "N85", "40", "2019"], ["GBR", "P2", "N85", "60", "2019"],
    ])
    return tmp_path


def test_input_concentration_excludes_various(eto):
    eda = next(r for r in input_concentration(eto) if r["eto_id"] == "N84")
    assert eda["company_hhi"] == 60**2 + 30**2
    assert eda["top_company"] == {"name": "Acme EDA", "share": 0.6}
    assert eda["country_shares"] == {"US": 0.9}


def test_stage_shares_weighted_by_market_size(eto):
    stage = stage_country_shares(eto)["design_tools_ip"]
    # US: (0.9 * 3 + 0.4 * 1) / 4 = 0.775 ; GB: 0.6 * 1 / 4 = 0.15
    assert stage["shares"] == {"US": 0.775, "GB": 0.15}
    assert stage["weighting"] == "market_size"
    assert stage_country_shares(eto)["fabrication"]["shares"] == {}


def test_chokepoints():
    edges = [
        {"supplier": "optics", "buyer": "litho", "input": "lenses", "has_alternatives": "no"},
        {"supplier": "other", "buyer": "litho", "input": "lenses", "has_alternatives": "unknown"},
        {"supplier": "litho", "buyer": "fab", "input": "scanners", "has_alternatives": "unknown"},
        {"supplier": "fab-a", "buyer": "designer", "input": "wafers", "has_alternatives": "unknown"},
        {"supplier": "fab-b", "buyer": "designer", "input": "wafers", "has_alternatives": "unknown"},
    ]
    result = {r["supplier"]: r for r in chokepoints(edges)}
    assert result["optics"]["dependents"] == [{"buyer": "litho", "input": "lenses", "reason": "sole_source"}]
    assert result["litho"]["dependents"][0]["reason"] == "single_known_supplier"
    assert "fab-a" not in result and "other" not in result
    assert next(iter(result)) == "optics"  # sole sources rank first


def test_criticality_ranks_upstream_chokepoint_first():
    nodes = [
        {"id": "litho", "stage": "equipment", "hq_country": "NL"},
        {"id": "fab", "stage": "fabrication", "hq_country": "TW"},
        {"id": "designer", "stage": "chip_design", "hq_country": "US"},
        {"id": "phones", "stage": "assembly_end_products", "kind": "product_category"},
    ]
    edges = [
        {"supplier": "litho", "buyer": "fab", "input": "s", "has_alternatives": "unknown"},
        {"supplier": "fab", "buyer": "designer", "input": "w", "has_alternatives": "unknown"},
        {"supplier": "designer", "buyer": "phones", "input": "c", "has_alternatives": "unknown"},
    ]
    crit = criticality(nodes, edges)
    assert [r["id"] for r in crit["companies"]] == ["litho", "fab", "designer"]
    assert crit["companies"][0]["full"] == ["designer", "fab", "phones"]
    assert "phones" not in [r["id"] for r in crit["companies"]]
    assert crit["countries"][0]["id"] == "NL"
