# Project status — v10 oracle-shadow tranche

## Implemented

- Portable oracle bundle schema.
- Hash-pinned provenance manifest with optional strict rights checks.
- Multi-editor trace ingestion using v9 adapters.
- Consensus event construction and timed transcript binding.
- Talk-level train/eval isolation.
- Context-aware, confidence-weighted representation policy.
- Availability filtering and explicit abstention.
- Held-out policy evaluation.
- Shadow-mode runtime integration.
- Learned-policy disagreement telemetry.
- Learned-policy-driven provider warming for supported explain/relate intents.
- Promotion gate that blocks fixture-only success from canary/active authority.
- Chromium rehearsal and regression suite.

## Verification at this snapshot

- v10 unit/integration tests: 14 passing.
- complete v1–v10 discovery suite: 101 passing.
- Chromium v10 rehearsal: 5 captures, 0 grammar rejections, 0.80 morph rate, 6 oracle recommendations, 2/2 provider warms successful.
- synthetic policy fixture: 40 consensus events across 8 talks. Held-out performance is a pipeline check only.
- canary promotion gate: correctly rejected because empirical corpus size/non-fixture evidence is absent.

## Not claimed

- No claim that the synthetic 100% held-out result predicts real editorial performance.
- No learned model has authority to bypass broker/grounding/grammar/intervention safety.
- No real 30–100 talk corpus has been collected yet.
- No canary or active-mode promotion has been earned.

## Next engineering target

Build the real acquisition runners and ingest the first rights-clean 30-talk corpus with at least two independent editor traces per talk.
