"""Build versioning and changelog tests (graph content stubbed with fictional data)."""

import json

from scg import build


def doc(edges):
    return {"nodes": [{"id": "a"}, {"id": "b"}], "edges": edges}


E1 = {"id": "a-to-b-x", "supplier": "a", "buyer": "b", "has_alternatives": "unknown"}


def test_changelog_lists_added_removed_and_changed():
    prev = doc([E1, {"id": "gone"}])
    new = doc([{**E1, "has_alternatives": "yes"}, {"id": "fresh"}])
    entry = build._changelog_entry(2, prev, new)
    assert "- Added 1 edges: fresh" in entry
    assert "- Removed 1 edges: gone" in entry
    assert "- Changed 1 edges: a-to-b-x" in entry
    assert "nodes" not in entry.split("\n", 3)[3]  # no node lines when nodes are unchanged


def test_write_build_versions_only_on_change(tmp_path, monkeypatch):
    current = {"value": doc([E1])}
    monkeypatch.setattr(build, "graph_document", lambda: current["value"])

    path, written = build.write_build(tmp_path)
    assert (path.name, written) == ("graph.v1.json", True)
    assert build.write_build(tmp_path) == (path, False)

    current["value"] = doc([{**E1, "has_alternatives": "no"}])
    path2, written2 = build.write_build(tmp_path)
    assert (path2.name, written2) == ("graph.v2.json", True)
    assert json.loads(path2.read_text())["version"] == 2

    log = (tmp_path / "CHANGELOG.md").read_text()
    assert log.index("## v2") < log.index("## v1")  # newest first
    assert "- Changed 1 edges: a-to-b-x" in log


def test_changelog_notes_analysis_changes():
    prev = {**doc([E1]), "analysis": {"chokepoints": [], "stage_country_shares": {}}}
    new = {**doc([E1]), "analysis": {"chokepoints": [], "stage_country_shares": {"fabrication": {}}}}
    assert "- Analysis changed: stage_country_shares" in build._changelog_entry(2, prev, new)
