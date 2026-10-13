# Migration Status — Dedicated Live Presenter Repository

Canonical repository: `Spectating101/live-presenter`

This repository supersedes the temporary staging branch/PR in `Spectating101/research-drive-private`. The old draft PR #77 was closed without merge and retained only as migration history.

## Safety posture

The migration is being performed as ordinary fast-forward commits on `main`.

- no force push
- no history rewrite
- no deletion of the recovered checkpoint
- no restructuring of the historical flat import layout during migration
- frozen v10 hashes remain recorded in `SOURCE_MANIFEST_V10.txt`

## Recovered checkpoint

The frozen source package contains:

- 156 source/package files
- 93 Python files
- 13 test modules
- all files UTF-8 text
- approximately 679 KB uncompressed source text

Canonical checkpoint hashes and per-file SHA-256 values are recorded in `HANDOFF.md` and `SOURCE_MANIFEST_V10.txt`.

## Already canonicalized here

The dedicated repo currently contains the root README/handoff/status material, v10 empirical/oracle control layer, v9 editorial trace normalization and oracle benchmark helpers, dependency/schema files, and a growing restoration of inherited runtime modules.

Core empirical lane present:

- `editorial_trace_v9.py`
- `oracle_benchmark_v9.py`
- `oracle_dataset_v10.py`
- `representation_policy_v10.py`
- `assemble_oracle_bundle_v10.py`
- `oracle_manifest_v10.py`
- `policy_gate_v10.py`
- `train_oracle_policy_v10.py`
- `oracle_bundle_schema_v10.json`
- `requirements.txt`

Restored inherited runtime pieces include:

- `audience_state.py`
- `intervention_policy.py`
- `argument_state.py`
- `live_evidence.py`
- `claim_ledger.py`

## Validation performed during migration

Against the recovered frozen source checkpoint:

```text
python -m py_compile editorial_trace_v9.py oracle_benchmark_v9.py \
  oracle_dataset_v10.py representation_policy_v10.py \
  assemble_oracle_bundle_v10.py oracle_manifest_v10.py \
  policy_gate_v10.py train_oracle_policy_v10.py runtime_v10.py
```

Result: `V10_IMPORT_SEAM_SYNTAX_OK`.

Direct imports of the core oracle modules also succeeded locally from the recovered checkpoint.

A direct `git clone` of the new public repo from the execution container could not be used for verification because that container currently has no DNS/network access. This is an environment limitation, not a GitHub repository failure; GitHub connector reads/writes continue to succeed normally.

## Remaining migration work

The complete historical/runtime dependency closure has not yet been expanded file-for-file into the dedicated repo. The remaining high-priority runtime closure includes the v1–v9 runtime chain, stage surfaces, semantic/representation broker, provider/visual grammar modules, memory/prefetch/data helpers, rehearsal and v10 tests.

Until that closure is finished, treat `SOURCE_MANIFEST_V10.txt` + the recovered frozen source package as the archival truth and the dedicated repo as the canonical active migration destination.

Do not promote a learned representation policy beyond shadow mode merely because migration is complete; empirical promotion gates in `policy_gate_v10.py` remain authoritative.
