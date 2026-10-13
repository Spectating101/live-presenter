# Live Presenter v9 — Offline Editor Oracle Benchmark

This fixture validates the **benchmark machinery**, not editorial intelligence. The included editor traces are synthetic examples in donor-style formats so the adapters and scoring logic can be exercised deterministically.

## Consensus oracle

```json
{
  "editors": 3,
  "clusters": 5,
  "consensus_events": 5,
  "agreement_histogram": {
    "3": 5
  }
}
```

Consensus events are derived from the three independent trace labels, rather than designating any single editor as truth.

## Causal-runtime result

```json
{
  "oracle_events": 5,
  "live_events": 6,
  "matches": 5,
  "intervention_recall": 1.0,
  "intervention_precision": 0.8333,
  "function_agreement": 1.0,
  "representation_agreement": 1.0,
  "median_causal_lag_s": 0.0,
  "mean_causal_lag_s": 0.12,
  "timing_quality": 0.9698,
  "prefetch_hit_rate": 0.6,
  "causal_availability_rate": 0.6,
  "speculative_waste_rate": 0.1667,
  "oracle_gap": 0.0101
}
```

The score rewards semantic/editorial agreement **and timing quality**. A system that eventually chooses the right visual but consistently shows it late therefore retains non-zero oracle gap.

This demo intentionally includes:

- one live event arriving 0.6 seconds after the oracle target;
- three oracle events whose assets/providers were already warm;
- two events marked not causally obvious from recent speech alone;
- one speculative live intervention that the oracle editors did not use.

## What to do with real editor agents

The adapters accept:

- `VideoAlchemyAdapter`: simple B-roll rows such as `{time, duration, src}`;
- `AutoBrollAdapter`: richer rows with start/end, visual kind, placement, query, reason, source transcript and alternatives;
- `GenericJSONAdapter`: a portable export format for human editors, Fable/Astra traces, Premiere/NLE scripts, or other agents;
- `load_generic_csv`: lightweight human-coded CSV traces.

A practical empirical run should use the same raw explanatory recording and create at least two genuinely independent editorial traces. Three or more editors are preferable because consensus can then separate shared editorial signal from one model's stylistic quirks.

Recommended conditions:

1. reactive live runtime;
2. recent-context proactive runtime;
3. trajectory-aware semantic prefetch;
4. trajectory-aware + learned editorial policy;
5. full-future offline oracle.

Then measure not only representation agreement but also the **causal gap**: how much of the offline editor's advantage survives when future speech is hidden.
