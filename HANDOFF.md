# Live Presenter v10 — Canonical Handoff

Current execution and measured results: see `RESEARCH_ROADMAP.md`. The checkpoint
history below remains archival; `make doctor` reports what this checkout can run.

## Canonical repository

Repository: `Spectating101/live-presenter`

Branch: `main`

This repository supersedes the temporary Research Drive staging branch `prototype/live-presenter-v10` and draft PR #77.

Frozen source-package checksum:

`sha256:6ba82011ada2523d802b6f1b767a7422c8c9e239c87ce211c86c8a150345a782`

Frozen full-artifact checksum (includes generated rehearsal outputs/logs):

`sha256:6b58a7bf5fa6304bfc44aed5afc00a9e194769e7536ca605ba9eecde5c7a370d`

The recovered frozen source snapshot contains **156 files**, including **93 Python files**, **13 test modules**, and **38 top-level documentation/log files**. `SOURCE_MANIFEST_V10.txt` records the exact per-file SHA-256 inventory for that checkpoint.

## Project thesis

Live Presenter is not primarily “AI makes PowerPoint” and not primarily voice-command software. The intended system is a **causal semantic visual editor for live explanation**:

```text
source material / paper / data / URLs
                 ↓
          semantic world model
                 ↓
live speech → topic + discourse-act belief
                 ↓
      semantic frontier / argument state
                 ↓
     speculative preparation (WARM)
                 ↓
       representation selection
                 ↓
   grounding + visual grammar + policy
                 ↓
         continuous Chromium stage
```

The key asymmetry is:

> **Aggressive backstage speculation; conservative public intervention.**

Wasted background work is acceptable. Wrong projector actions are not.

## Evolution to v10

### v1–v4

Established the headless runtime, semantic HOT/WARM frontier, local corpus/RAG, async AI adviser, off-graph topics, asset prefetch, Chromium-owned stage, interim/final STT contract, natural controls, local charts, telemetry, and a trajectory-prefetch comparison. A controlled toy experiment showed prefetch can hide artificial asset latency, while skipped branches demonstrated speculative-waste risk.

### v5 — semantic stage

Separated **semantic concept** from **representation**. One concept can render as hero, definition, image grid, causal flow, concept map, evidence, chart, or comparison. Added `representation_broker.py`, `intervention_policy.py`, semantic-only graphing, deterministic Chromium rendering, source-bound evidence, and audience-state input.

### v6 — object-continuous stage

Introduced stable semantic object IDs and actual audience-exposure memory. Added object-level morph/add/remove continuity, Chrome View Transitions, topic-vs-representation firewall, contextual provenance, and exposure-aware backstage adaptation. Important correction: an utterance such as “what evidence supports this?” changes the representation, not the semantic topic.

### v7 — epistemic argument system

Added first-class claims/evidence, argumentative obligations (introduced vs substantiated), epistemic classes, safer off-script tangents, and bounded rehearsal learning that can make intervention policy more conservative but cannot override grounding/safety.

### v8 — unseen-corpus generalization

Added role-aware semantic compilation from raw notes/data, automatic dataset binding, derived visual affordances, live external evidence as a separate epistemic class, and persistent presenter-style preferences. A separate urban-heat corpus successfully drove the same runtime without a hand-authored presentation graph.

### v9 — upstream integration / editorial oracle

Imported useful patterns from adjacent systems without making them live-path dependencies: normalized offline-editor traces (AutoBroll/Video-Alchemy style), multi-editor consensus, oracle-gap metrics, Graphologue-style progressive diagrams, ARChat-style provider lifecycle, and a typed visual grammar. Remotion was kept as an optional offline oracle/rendering tool, not a live critical-path dependency.

### v10 — oracle-distilled representation policy

Added an empirical representation-policy layer trained from normalized human/offline-editor traces. The learned policy is **advisory only**: it can recommend and pre-warm representations/providers but cannot bypass the semantic broker, grounding ledger, visual grammar, intervention policy, or stage lock.

## v10 authority chain

```text
editor traces / human edits
          ↓
EditorialEvent normalization
          ↓
per-talk consensus + transcript/context binding
          ↓
talk-isolated train/eval split
          ↓
transparent representation policy
          ↓
confidence / support / entropy abstention
          ↓
SHADOW recommendation + provider warming
          ↓
safe broker + grounding + grammar + intervention policy
          ↓
projector
```

### Hard invariant

The learned policy **cannot escalate HOLD/WITHHOLD to SHOW**. A learned recommendation that disagrees with a safe broker result remains telemetry/advice; the broker wins.

## Verified checkpoint

Frozen v10 verification:

- v10 unit/integration tests: **14/14 passing**
- repeated v10 test runs: **5/5 passing**
- complete v1–v10 unittest discovery: **101/101 passing**
- Chromium v10 rehearsal: **PASS**
  - captures: 5
  - grammar rejections: 0
  - object morph rate: 0.80
  - oracle recommendations: 6
  - provider warms: 2
  - provider warm successes: 2/2
  - oracle authority: `advisory_only`
- synthetic fixture: 8 talks / 40 consensus examples
- synthetic held-out result: top1=1.0, coverage=1.0, selective_accuracy=1.0 — **pipeline fixture only, not empirical quality evidence**
- canary gate: **REJECTED as intended** because empirical corpus requirements were not met

See `V10_FREEZE_CHECK.txt` and `PROJECT_STATUS_V10.md`.

## What is implemented in v10

- portable oracle-bundle contract
- hash/provenance/rights manifest
- editor-trace ingestion and consensus
- timed transcript/context binding
- talk-level train/eval isolation
- transparent context-aware representation policy
- availability filtering and explicit abstention
- held-out evaluation
- shadow runtime integration
- policy disagreement telemetry
- learned-policy-driven provider warming
- shadow → canary → active promotion gate
- real bundle assembler for SRT/VTT/JSON transcripts + editor traces
- Chromium rehearsal and regression suite

Primary v10 files:

- `runtime_v10.py`
- `representation_policy_v10.py`
- `assemble_oracle_bundle_v10.py`
- `oracle_manifest_v10.py`
- `policy_gate_v10.py`
- `train_oracle_policy_v10.py`
- `ENGINEERING_PLAN_V10.md`
- `PROJECT_STATUS_V10.md`
- `V10_FREEZE_CHECK.txt`

## What is NOT yet proven

- No claim that the synthetic 100% held-out score predicts real editorial quality.
- No 30–100 talk real corpus has been collected yet.
- No learned policy has earned canary/active authority.
- No human study proves that audiences prefer the intervention style.
- No claim that internal millisecond benchmarks are microphone/network/end-to-end latency.
- No claim that a physical lab is required for current engineering validation.

## Immediate restart point

The project stopped while starting the **first real-corpus tranche**.

Goal:

> Build a rights-clean empirical corpus of real explanatory discourse and independent editorial traces, then test whether the learned representation policy generalizes by completely unseen talk.

Recommended first target:

1. ingest **30 real talks** before scaling farther;
2. use at least **two genuinely independent editorial traces per talk**, preferably three where practical;
3. preserve exact transcript timing, editor/model identity/version, source URI, domain/language/style metadata, and rights basis;
4. normalize all editor output into the v9 `EditorialEvent` contract;
5. hash and manifest every bundle before training;
6. split by talk, never by event;
7. train the transparent count/backoff baseline first;
8. inspect consensus/disagreements and domain/availability slices;
9. run the policy in v10 shadow mode on unrelated rehearsals;
10. only then compare a calibrated multinomial/ranker and consider canary authority.

### Canary threshold

- >=30 talks
- >=150 examples
- >=40 held-out examples
- >=0.65 coverage
- >=0.75 selective accuracy
- >=30 non-fixture talks
- successful browser rehearsal evidence

### Active threshold

- >=100 talks
- >=500 examples
- >=100 held-out examples
- >=0.80 coverage
- >=0.82 selective accuracy
- >=100 non-fixture talks
- browser pass
- no unresolved dataset warnings

## Real-corpus candidates already investigated

Useful rights-clean or bounded-use candidates included:

- AMI / ICSI meeting corpora for permissive research engineering
- AMI-ME (CC BY 4.0) for fine-grained, timestamped topical segments with human effectiveness/objective annotations
- MIT OpenCourseWare and Open Yale Courses for noncommercial educational/explanatory benchmarking, subject to their Creative Commons terms
- NASA educational/science media where source-specific attribution and third-party-rights checks permit use

Re-check current source terms before ingesting anything and record the exact rights basis in each bundle.

## Offline editor / video-oracle direction

Treat offline AI/human video editing as an **oracle for live presentation decisions**:

```text
semantic visual editor
       ├─ offline: complete future timeline → edited video
       └─ online: causal past/present only → adaptive stage
```

Benchmark the causal runtime against a full-future editor using semantic agreement, representation agreement, timing lag, prefetch hits, causal availability, and speculative waste.

A further useful lane is **video-to-oracle extraction**: align raw and AI-edited versions of an explanatory video and infer editorial interventions from timestamped frames, transcript, OCR, shot/overlay changes, motion/audio metadata, etc. This can reduce dependence on editors exporting clean JSON traces.

## Quick verification

```bash
python make_oracle_fixture_v10.py
python train_oracle_policy_v10.py data/oracle_v10/*.json --out-dir artifacts/v10
python oracle_manifest_v10.py data/oracle_v10/*.json --out artifacts/v10/oracle_manifest_v10.json --strict-rights
python -m unittest -v test_v10.py
python rehearsal_v10.py
python -m unittest discover -v
```

Dependencies recorded at freeze:

```text
aiohttp>=3.9
playwright>=1.45
scikit-learn>=1.4
pypdf>=4
python-docx>=1
```

Chromium/Playwright browser availability is required for the actual stage rehearsal path.

## Repository hygiene

Generated screenshots, rehearsal state JSON, event logs, caches, and benchmark output are evidence artifacts, not canonical source. Keep them out of normal source commits unless explicitly freezing an experiment.

This public repository currently carries **no open-source license**. Third-party projects mentioned in the integration notes are precedents/donors of ideas and contracts; keep code/provenance/licensing boundaries explicit.

## Decision posture

Keep this project a bounded, high-upside presentation/research tool unless empirical evidence earns more priority. The strongest unresolved question is no longer whether the architecture can run; it is whether an empirical editorial policy learned from real talks/offline editors materially improves representation choice and causal prefetch over hand-authored heuristics.

## One-line restart instruction

> Ingest the first rights-clean real editorial corpus into the v10 bundle format, train/evaluate by held-out talk, and keep the learned layer in shadow mode until the formal promotion gate is earned.
