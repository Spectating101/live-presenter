# Live Presenter v10

Live Presenter is a **causal semantic visual editor for live explanation**: it listens to an unfolding presentation, tracks the semantic/argument state, prepares likely nearby representations backstage, and updates a continuous Chromium stage under conservative grounding and intervention rules.

V10 adds an **oracle-distilled representation policy in shadow mode** on top of the v9 provider/visual-grammar architecture. The learned layer can recommend and warm representations, but the semantic broker, grounding rules, visual grammar, intervention policy, and stage lock remain authoritative.

## Start here

- `HANDOFF.md` — canonical project handoff and restart instructions
- `ENGINEERING_PLAN_V10.md` — empirical/oracle engineering plan
- `PROJECT_STATUS_V10.md` — checkpoint status and non-claims
- `SOURCE_MANIFEST_V10.txt` — frozen v10 source inventory and hashes
- `THIRD_PARTY_INTEGRATION_V9.md` — upstream inspiration/integration notes

## What runs in this repository today

This repo holds the v10 empirical lane plus the System-1 (Jev) layer. The v1-v9 runtime, stage and the 101-test suite live in the
frozen checkpoint and are still being migrated here (`runtime_v10.py` needs `runtime_v9`, so it does not import yet).

```bash
make test        # 37 stdlib-only tests: policy, System-1 client, editor tools, trace comparison, strictly causal harness
make pilot       # score the windowed editor trace against the oracle trace for the NASA pilot talk
make eval-mock   # run the strictly causal System-1 harness with a mock backend (plumbing check)
cp .env.example .env && export JEV_API_KEY=...   # then:
make bench       # real Jev latency from this machine
make eval-jev    # real strictly causal comparison against the oracle trace -> artifacts/jev_eval.json
```

| Piece | File |
|---|---|
| Fast typed decisions (Jev client, mock, fallback, batching) | `system1_v10.py` |
| Strictly causal evaluation on a real talk | `eval_system1_v10.py` |
| Editor prompts (oracle / causal) and trace validation | `editor_trace_tools_v10.py` |
| Trace comparison metrics | `compare_traces_v10.py` |
| Transcript readers (SRT/VTT/JSON) | `transcript_io_v10.py` |
| Real pilot data and caveats | `data/nasa_stgermain_cop26/` |
| Why the video-editing demos matter | `EDITOR_REFERENCES_V10.md` |

Python 3.13, standard library only for everything above. CI runs `make test` and the mock harness (`.github/workflows/ci.yml`).

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

## Frozen verification (recorded at the checkpoint, re-run by the owner on a later date; not reproducible from this repo yet)

- v10 unit/integration tests: **14/14 passing**
- repeated v10 runs: **5/5 passing**
- complete v1–v10 discovery suite: **101/101 passing**
- Chromium v10 rehearsal: **PASS**
- synthetic fixture: pipeline verification only; **not** empirical editorial-quality evidence
- canary promotion gate: **REJECTED as intended** pending real-corpus evidence

## Full checkpoint verification (needs the frozen v1-v10 checkpoint; not runnable from this repo alone)

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
