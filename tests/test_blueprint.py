"""Tests: provenance helpers, sibling aggregation, fleet node labels. No network."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import blueprint  # noqa: E402
from blueprint import FLEET_NODES, NODE_FOR_SECTION, latest_json, with_node  # noqa: E402


def test_latest_json_picks_newest(tmp_path):
    d = tmp_path / "benchmarks"
    d.mkdir()
    (d / "ubercode_20260101_000000.json").write_text(json.dumps({"v": 1}))
    (d / "ubercode_20260102_000000.json").write_text(json.dumps({"v": 2}))
    (d / "other_20260103.json").write_text(json.dumps({"v": 3}))
    assert latest_json(d, "ubercode") == {"v": 2}


def test_latest_json_missing_dir_is_none(tmp_path):
    assert latest_json(tmp_path / "nope", "ubercode") is None


def test_with_node_attaches_label():
    out = with_node({"source": "x", "cold": 1}, "weight_delivery")
    assert out["node"] == "tensorfold" and out["source"] == "x"


def test_with_node_none_passthrough_and_unknown_key():
    assert with_node(None, "batcher") is None
    assert with_node({"source": "y"}, "not-a-section") == {"source": "y"}


def test_fleet_labels_cover_all_sections():
    assert set(FLEET_NODES) == {"glm-head", "tensorfold", "bonsai-1",
                                "bonsai-2", "sushi"}
    for key in ("batcher", "spec_decode", "weight_delivery", "reliability",
                "security", "recovery", "live_cluster_now"):
        assert key in NODE_FOR_SECTION


def test_main_writes_report_with_node_labels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(blueprint, "live_cost_snapshot", lambda *a, **k: None)
    blueprint.main()
    data = json.loads((tmp_path / "report" / "teardown_data.json").read_text())
    assert data["reliability"]["node"] == "glm-head"
    assert data["reliability"]["rto_s"] == 1.1
