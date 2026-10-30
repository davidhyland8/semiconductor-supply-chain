"""Runs the shared scenario fixtures (also run by web/ in TypeScript)."""

import json
from pathlib import Path

import pytest

from scg.analysis.scenario import OK, Scenario, propagate

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scenarios"


def load_cases():
    for path in sorted(FIXTURES.glob("*.json")):
        for case in json.loads(path.read_text())["cases"]:
            yield pytest.param(case, id=f"{path.stem}: {case['name']}")


@pytest.mark.parametrize("case", list(load_cases()))
def test_fixture(case):
    result = propagate(case["nodes"], case["edges"], Scenario(**case["scenario"]))
    expected = {n["id"]: case["expected"].get(n["id"], OK) for n in case["nodes"]}
    assert result.state == expected
    for node_id, rules in case.get("expected_rules", {}).items():
        found = {c["rule"] for c in result.causes.get(node_id, [])}
        assert set(rules) <= found, f"{node_id}: expected rules {rules}, got {sorted(found)}"


def test_causes_name_lost_suppliers():
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [
        {"supplier": "a", "buyer": "c", "input": "x", "has_alternatives": "unknown"},
        {"supplier": "b", "buyer": "c", "input": "x", "has_alternatives": "unknown"},
    ]
    result = propagate(nodes, edges, Scenario(companies=["a"]))
    assert result.causes["c"] == [{"rule": "some_suppliers_lost", "input": "x", "lost": ["a"], "degraded": []}]
    assert "b" not in result.causes
