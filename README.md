# Live Presenter v10

Live Presenter is a **causal semantic visual editor for live explanation**: it listens to an unfolding presentation, tracks the semantic/argument state, prepares likely nearby representations backstage, and updates a continuous Chromium stage under conservative grounding and intervention rules.

V10 adds an **oracle-distilled representation policy in shadow mode** on top of the v9 provider/visual-grammar architecture. The learned layer can recommend and warm representations, but the semantic broker, grounding rules, visual grammar, intervention policy, and stage lock remain authoritative.

## Start here

- `HANDOFF.md` — canonical project handoff and restart instructions
- `ENGINEERING_PLAN_V10.md` — empirical/oracle engineering plan
- `PROJECT_STATUS_V10.md` — checkpoint status and non-claims
- `SOURCE_MANIFEST_V10.txt` — frozen v10 source inventory and hashes
- `THIRD_PARTY_INTEGRATION_V9.md` — upstream inspiration/integration notes

## Core invariant

> **Aggressive backstage speculation; conservative public intervention.**

The learned policy cannot escalate `HOLD` / `WITHHOLD` to `SHOW`.

## V10 path

```text
multiple offline/human editors
        ↓
EditorialEvent normalization
        ↓
per-talk consensus + transcript/context binding
        ↓
talk-isolated oracle dataset
        ↓
transparent representation policy
        ↓
confidence/support/entropy abstention
        ↓
shadow recommendation + provider warming
        ↓
safe broker + grounding + grammar + intervention policy
        ↓
continuous Chromium stage
```

## Frozen verification

- v10 unit/integration tests: **14/14 passing**
- repeated v10 runs: **5/5 passing**
- complete v1–v10 discovery suite: **101/101 passing**
- Chromium v10 rehearsal: **PASS**
- synthetic fixture: pipeline verification only; **not** empirical editorial-quality evidence
- canary promotion gate: **REJECTED as intended** pending real-corpus evidence

## Quick verification

```bash
python make_oracle_fixture_v10.py
python train_oracle_policy_v10.py data/oracle_v10/*.json --out-dir artifacts/v10
python oracle_manifest_v10.py data/oracle_v10/*.json --out artifacts/v10/oracle_manifest_v10.json --strict-rights
python -m unittest -v test_v10.py
python rehearsal_v10.py
python -m unittest discover -v
```

Dependencies are recorded in `requirements.txt`. Chromium/Playwright availability is required for the actual stage rehearsal path.

## Current restart point

Build the first rights-clean real editorial corpus (target: 30 talks, at least two independent editor traces per talk), train/evaluate by **held-out talk**, and keep the learned policy in shadow mode until the formal promotion gate is earned.

This repository is public, but no open-source license is granted yet. Third-party systems referenced in the docs are architectural/integration precedents; the project should keep source/provenance and licensing boundaries explicit.
