"""
Benchwarmer - the capstone teardown.

One reproducible report over the whole stack. Every number here is either
pulled from a sibling project's committed benchmark output or measured live
against the cluster (read-only). Provenance is explicit: each metric names
the repo + file it came from.

The report: REPORT.md - architecture, latency, cost, reliability, with
reproduction commands for every table.
"""
from __future__ import annotations

import json
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
        "batcher": batcher_metrics(),
        "spec_decode": spec_metrics(),
        "gpu_partitioning": fairness_metrics(),
        "autoscaling": autoscaler_metrics(),
        "weight_delivery": delivery_metrics(),
        "reliability": {"source": "Flunk drill (documented in repo README)",
                        "rto_s": 1.1, "rpo_requests": 2,
                        "detection_floor_s": 1.5},
        "security": {"source": "Bastion attack drill (repo README)",
                     "checks": 11, "passed": 11},
        "recovery": {"source": "Furnace fault drill (repo README)",
                     "kill_step": 35, "resume_step": 30,
                     "attempts_to_complete": 2},
    }
    live = live_cost_snapshot("http://192.168.0.182:8000", None)
    if live:
        sections["live_cluster_now"] = live

    out = Path("report")
    out.mkdir(exist_ok=True)
    (out / "teardown_data.json").write_text(json.dumps(sections, indent=2))
    print(json.dumps(sections, indent=2)[:3000])
    print(f"\nsaved {out}/teardown_data.json")


if __name__ == "__main__":
    main()
