# Benchwarmer

**The capstone teardown — the whole stack, measured, with provenance.**

Every number below comes from a sibling repo's committed benchmark output or a live read-only scrape, and each names its source. Reproduce with `python benchwarmer.py` (aggregates sibling `benchmarks/` directories) — nothing here is hand-copied.

Part of the [TechGuardCoders portfolio](https://github.com/orgs/TechGuardCoders/repositories): Cost Peep → Batcher → Spinal → Ball Knowledge → Bastion → Furnace → Truffle → Popcorn → QueuedGPU → Circuiter → UberCode → Flunk → **Benchwarmer**.

## The architecture being torn down

```
                    ┌─────────────────────────────┐
                    │  Pocket Watching :3001      │  ← FinOps dashboard (feeds below)
                    └─────────────┬───────────────┘
                    ┌─────────────┴───────────────┐
                    │  Bastion :3200              │  keys·scopes·tamper-evident audit·sandbox
                    └─────────────┬───────────────┘
                    ┌─────────────┴───────────────┐
                    │  Ball Knowledge :3100       │  routing·failover·rate limits·budgets
                    └─────────────┬───────────────┘
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
  glm-spark (vLLM)          mock fallback            (any backend)
  2× DGX Spark, GB10        in-process               pluggable
  DFlash2 speculation
        │
        ├── QueuedGPU   autoscale on queue depth (pre-warm, drain)
        ├── Circuiter   8 MIG-style slices, WFQ, reservation-enforced limits
        ├── UberCode    sha256 content-addressed weight delivery
        ├── Furnace     checkpointed training: fault injection → resume
        └── Flunk       region failover drill: RTO/RPO measurement
```

## The numbers (all provenance-linked)

### Serving & throughput — Batcher
Aggregate 43.8 → 45.2 → **67.9 tok/s** at c=1/2/4; the knee at c=2 (spec-decode overhead), 0 failures, `MAX_SEQS=4` ceiling, 1.55× scaling at c=4 = bandwidth-bound MoE.

### Speculative decoding — Truffle (live, 48 req, 0 fail)
Acceptance **21.0–22.5%**, concurrency-insensitive; **1.47–1.58 accepted tokens per draft cycle** (vs 1.0 without speculation); per-position acceptance decays geometrically ~0.6 → draft-length sweet spot at position 3–4. Explains Batcher's knee from inside the engine.

### GPU partitioning — Circuiter (saturated contention, 30 ticks)
Weights 3:2:1 → units 60/40/20 → **fairness ratios 1.50 and 3.00, exact**. 263 oversubmission attempts rejected by reservation-at-admission limits.

### Autoscaling — QueuedGPU (3× burst drill)
Pre-warm controller: **15.0s drain, peak queue 34** vs naive reactive 18.0s / 42. The 3-second dividend is cold-start mitigation, measured.

### Weight delivery — UberCode
Cold bring-up 1.34s (12 shards, 100MB, sha256-verified); warm **0 bytes over network**; interrupted pulls resume pulling **only the missing shards**.

### Recovery — Furnace
2-rank job hard-killed at step 35 (both ranks exit 137) → supervisor restarts on a fresh rendezvous port → resumes from the step-30 checkpoint (Adam moments intact) → completes. Attempts: 2.

### Reliability — Flunk
**RTO 1.1s** (detection-bound at the 1.5s floor of 3 misses × 0.5s probes), **RPO 2 requests**, 18/20 served through failover, return-to-primary after heal with flapping protection.

### Security — Bastion
11/11 live attack checks: forged keys → 401, audit tampering → detected and named, scope escalation → 403 (and the drill caught the escalation bug that fix created the least-privilege rotation rule), sandbox runaway code → timeout kill.

### FinOps — Pocket Watching
$/1M tokens continuously against the live cluster; tenant attribution (gateway), cost-per-accepted-token (Truffle), per-slice costs (Circuiter), reliability panel (Flunk) — all feeds best-effort, dashboard never dies with a dependency.

## Cross-cutting findings (the synthesis)

1. **The knee at c=2 is a speculation tax.** Batcher measured it (no throughput gain c=1→2), Truffle explained it (acceptance is load-insensitive; fixed overhead per draft cycle), so the fix is engine-side (draft length ~pos 3–4), not load-side.
2. **Every recovery path was wrong before it was tested.** Furnace's checkpoint resume hit a Windows fsync bug and a seeded-shuffle fairness bug; UberCode's shard generator produced zero-entropy shards (caught by dedupe); Circuiter's limit check compared against memory nobody reserved; Flunk's detector starved (nothing fed it). Five for five. The lesson isn't "tests are good" — it's that recovery/fairness/limits code fails in ways only *drills* reveal.
3. **Measurement bugs hide behind working systems.** Twice (Flunk's RTO reading None; Circuiter's unreserved limit check passing everything) the system *looked* right while the metric lied. Honest provenance — every number naming its source — is what makes this report trustworthy.

## Reproduce

```bash
python benchwarmer.py          # aggregates sibling benchmarks + live scrape → report/teardown_data.json
```
Each sibling repo has its own drill + CI proving its numbers independently.
