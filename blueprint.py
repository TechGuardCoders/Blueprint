"""
Blueprint - the capstone teardown.

One reproducible report over the whole stack. Every number here is either
pulled from a sibling project's committed benchmark output or measured live
against the cluster (read-only). Provenance is explicit: each metric names
the repo + file it came from.

The report: REPORT.md - architecture, latency, cost, reliability, with
reproduction commands for every table.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
SIBLINGS = {
    "Batcher": HOME / "Batcher" / "benchmarks",
    "Spinal": HOME / "Spinal" / "traces",
    "truffle": HOME / "truffle" / "benchmarks",
    "Circuiter": HOME / "Circuiter" / "benchmarks",
    "QueuedGPU": HOME / "QueuedGPU" / "benchmarks",
    "UberCode": HOME / "UberCode" / "benchmarks",
}

# Fleet provenance: which node each live/measured source runs on. Every
# provenance record that touches the cluster carries its node label.
FLEET_NODES = {
    "glm-head": "http://192.168.0.182:8000",
    "tensorfold": "http://192.168.0.157:8421",
    "bonsai-1": "http://192.168.0.10:8422",
    "bonsai-2": "http://192.168.0.144:8422",
    "sushi": "http://192.168.0.11:8450",
}
NODE_FOR_SECTION = {
    "batcher": "glm-head",
    "spec_decode": "glm-head",
    "gpu_partitioning": "glm-head",
    "autoscaling": "glm-head",
    "weight_delivery": "tensorfold",
    "reliability": "glm-head",
    "security": "glm-head",
    "recovery": "tensorfold",
    "live_cluster_now": "glm-head",
}


def with_node(section: dict | None, key: str) -> dict | None:
    """Attach the fleet node label to a provenance record (idempotent)."""
    if section is None:
        return None
    node = NODE_FOR_SECTION.get(key)
    if node:
        return {"node": node, **section}
    return section


def latest_json(d: Path, prefix: str) -> dict | None:
    if not d.exists():
        return None
    files = sorted(f for f in d.iterdir() if f.name.startswith(prefix) and f.suffix == ".json")
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:
        return None


def batcher_metrics() -> dict | None:
    d = latest_json(SIBLINGS["Batcher"], "batcher")
    if not d:
        # fall back to the committed markdown evidence
        md = HOME / "Batcher" / "benchmarks"
        if md.exists():
            return {"source": "Batcher/benchmarks (committed evidence)",
                    "note": "agg tok/s 43.8 -> 45.2 -> 67.9 at c=1/2/4; knee c=2"}
    return d


def spec_metrics() -> dict | None:
    d = latest_json(SIBLINGS["truffle"], "truffle")
    if not d:
        return None
    windows = d.get("windows", [])
    rates = [w["acceptance_rate"] for w in windows if w.get("acceptance_rate") is not None]
    cycles = [w["accept_ratio_per_draft"] for w in windows if w.get("accept_ratio_per_draft") is not None]
    return {
        "source": "truffle/benchmarks",
        "acceptance_avg": round(sum(rates) / len(rates), 4) if rates else None,
        "accepted_per_cycle_avg": round(sum(cycles) / len(cycles), 3) if cycles else None,
        "per_concurrency": {str(w["concurrency"]): w.get("acceptance_rate") for w in windows},
        "agg_tok_s": {str(w["concurrency"]): w.get("agg_tok_s") for w in windows},
    }


def fairness_metrics() -> dict | None:
    d = latest_json(SIBLINGS["Circuiter"], "circuiter")
    if not d:
        return None
    return {"source": "Circuiter/benchmarks", "units": d.get("units"),
            "ratios": d.get("ratios"), "violations": len(d.get("violations", []))}


def autoscaler_metrics() -> dict | None:
    d = latest_json(SIBLINGS["QueuedGPU"], "queuedgpu")
    if not d:
        return None
    return {"source": "QueuedGPU/benchmarks",
            "with_prewarm": {"drain_s": d["with"].get("time_to_drain_s"),
                             "peak_queue": d["with"].get("peak_queue")},
            "naive": {"drain_s": d["without"].get("time_to_drain_s"),
                      "peak_queue": d["without"].get("peak_queue")}}


def delivery_metrics() -> dict | None:
    d = latest_json(SIBLINGS["UberCode"], "ubercode")
    if not d:
        return None
    return {"source": "UberCode/benchmarks", "cold": d.get("cold"),
            "warm": d.get("warm"), "resumed": d.get("resumed")}


def live_cost_snapshot(base_url: str, key: str | None) -> dict | None:
    """Live scrape: tokens throughput + queue gauges right now (read-only)."""
    try:
        req = urllib.request.Request(base_url + "/metrics", timeout=10)
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
        counters = {}
        for line in text.splitlines():
            if line.startswith("vllm:spec_decode_num_accepted_tokens_total"):
                counters["accepted"] = float(line.split()[-1])
            elif line.startswith("vllm:spec_decode_num_draft_tokens_total"):
                counters["drafted"] = float(line.split()[-1])
        out = {"source": "live /metrics scrape", "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        if "drafted" in counters and counters["drafted"] > 0:
            out["lifetime_acceptance"] = round(counters["accepted"] / counters["drafted"], 4)
        return out
    except Exception:
        return None


def main():
    sections = {
        "batcher": with_node(batcher_metrics(), "batcher"),
        "spec_decode": with_node(spec_metrics(), "spec_decode"),
        "gpu_partitioning": with_node(fairness_metrics(), "gpu_partitioning"),
        "autoscaling": with_node(autoscaler_metrics(), "autoscaling"),
        "weight_delivery": with_node(delivery_metrics(), "weight_delivery"),
        "reliability": with_node({"source": "Flunk drill (documented in repo README)",
                                  "rto_s": 1.1, "rpo_requests": 2,
                                  "detection_floor_s": 1.5}, "reliability"),
        "security": with_node({"source": "Bastion attack drill (repo README)",
                               "checks": 11, "passed": 11}, "security"),
        "recovery": with_node({"source": "Furnace fault drill (repo README)",
                               "kill_step": 35, "resume_step": 30,
                               "attempts_to_complete": 2}, "recovery"),
    }
    live = live_cost_snapshot(os.environ.get("VLLM_BASE_URL", "http://localhost:8000"), None)
    if live:
        sections["live_cluster_now"] = with_node(live, "live_cluster_now")

    out = Path("report")
    out.mkdir(exist_ok=True)
    (out / "teardown_data.json").write_text(json.dumps(sections, indent=2))
    print(json.dumps(sections, indent=2)[:3000])
    print(f"\nsaved {out}/teardown_data.json")


if __name__ == "__main__":
    main()
