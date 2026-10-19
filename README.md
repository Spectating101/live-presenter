# Live Presenter

Prepare the meaning together, then let speech guide the visuals. Supply your
material, discuss the audience and unresolved questions with the preparation
partner, review the visual alternatives and approve a version. During the talk,
the app follows your explanation through that prepared material while you retain
direct stage controls.

The target is a live explanation environment: choose the visual form that makes
the idea understandable, procure missing material as needed, and let speech
direct attention within it. It is not a slide-deck generator. See
[`EXPLANATION_DESIGN.md`](EXPLANATION_DESIGN.md) for the research basis, current
implementation and the audience evidence still needed.

The audience output is the visual itself, with no visible webpage or operator
interface. The new native path renders charts and images directly, supports
speech-cue focus and grounded comparisons, and exports motion samples headlessly.
Start with [`NATIVE_OUTPUT.md`](NATIVE_OUTPUT.md). The existing web studio is a
legacy operator/diagnostic tool, rather than the target presentation experience.

The new local studio implements this preparation-to-stage loop. It is a functional
prototype with backend acceptance checks; browser layout and physical microphone/
projector operation remain unverified. The repository also contains the v10
research lane for evaluating causal visual editing and an advisory learned policy.

## Start here

- `make native-preview` — export the native visual-only motion sample without using the screen (optional native dependencies)
- `make native-test` — test native output and attention offscreen
- `make studio` — run the new preparation-first local app; open its terminal access URL
- `STUDIO.md` — intake, clarification, visual review, approval, rehearsal and projector guide
- `RECORDED_TALKS.md` — real audio replay, original-video comparison and measured pilot limitations
- `PREPARED_REFLEX.md` — experimental prepared-cue reaction, faster audio replay and latency limits
- `BOUNDED_AUDIO.md` — limited decoding, repetitive-output rejection and explicit stale-window replay
- `LIVE_AUDIO.md` — opt-in local English microphone input and wall-clock HTTP/ASR/stage probes (`make studio-local`)
- `VIDEO_COMPARISONS.md` — two additional TED tests, original-video comparison, preparation coverage and missing visual evidence
- `SUPPLIED_VISUALS.md` — supplied images, presenter-selected defaults and a follow-up test with original graphics and CSV values
- `LIVE_RESEARCH.md` — background lookup of unprepared related topics, online diagrams and source quotes; optional connected browsing-agent handoff
- `RESEARCHED_REHEARSAL.md` — automatic web procurement before preparation, unattended live search and a continuous paced-audio probe
- `FASTER_LIVE_RESEARCH.md` — progressive source publication, paired backend timing and a preserved recognition failure
- `WARMED_RESEARCH.md` — recheck returning online topics without refetching, single-thread ASR and follow-up audio timing
- `RESEARCH_ROADMAP.md` — current execution plan, measured results, acceptance gates and blockers
- `make verify` — reproducible offline checks from this checkout
- `HANDOFF.md` — canonical project handoff and restart instructions
- `ENGINEERING_PLAN_V10.md` — empirical/oracle engineering plan
- `PROJECT_STATUS_V10.md` — checkpoint status and non-claims
- `SOURCE_MANIFEST_V10.txt` — frozen v10 source inventory and hashes
- `THIRD_PARTY_INTEGRATION_V9.md` — upstream inspiration/integration notes

## What runs in this repository today

The new `presenter/` studio provides a complete local product path independently
of the missing historical runtime: import material, discuss the meaning with the
existing Copilot CLI, review prepared visuals and source quotes, approve a version,
then rehearse using typed utterances or browser speech recognition. A separate
projector displays prepared content under presenter controls. Jev advice is an
explicit optional switch; Source outline plus typed rehearsal works without AI
calls. See `STUDIO.md` for verified behavior and remaining limits.

Optional live research can procure fresh supporting material while prepared
following continues. `make studio-research` uses existing Jev credentials with
public-source adapters; `make studio-research-agent` connects an active agent
with broader browsing tools. Cold retrieval takes seconds and can time out;
prepared/cached selection is faster. See `LIVE_RESEARCH.md` for measured examples,
source attribution, agent requirements and the provisional display behavior.

This checkout runs the v10 empirical lane and System-1 (Jev) layer. The trace adapters,
consensus benchmark and several inherited modules have been integrated from `main`.
The historical runtime and its original Chromium stage remain blocked on recovery of the frozen
source package: `runtime_v10.py` still cannot import `runtime_v9`.

```bash
make verify      # offline tests, pilot comparison, causal mock replay, readiness report
make test        # stdlib-only tests; no key or network needed
make pilot       # score the windowed editor trace against the oracle trace for the NASA pilot talk
make eval-mock   # run the strictly causal System-1 harness with a mock backend (plumbing check)
# Set JEV_API_KEY / TYPESAFE_API_KEY, put it in an ignored .env file,
# or point JEV_ENV_FILE at an existing credentials file. Then:
make bench       # real Jev latency -> artifacts/jev_bench.json
make eval-jev    # serial, latency-adjusted caption replay -> artifacts/jev_eval.json
make corpus-acquire  # download the pinned 30 NASA caption candidates (network)
make corpus-audit    # timing, duplicate, rights/context and editor checks
make corpus-jobs     # 60 independent editor job prompts; does not run models
```

The replay reads a caption only when it ends and timestamps its candidate decision
after inference completes. It records every assessment, backend failure, resolved
model and token usage. It is an **offline advisory replay**, excluding STT and
stage rendering. The older windowed pilot has lookahead and is not directly
comparable to this stricter result.

The 30-source catalog is pinned in `data/corpus_sources_v10.json`; downloaded
captions and jobs live in ignored `artifacts/`. The first tranche covers NASA
science material, including talks, narrated explanations and interviews. These
are candidates pending source/asset review and independent annotation, not a
completed empirical training corpus. See `RESEARCH_ROADMAP.md` for the workflow.

| Piece | File |
|---|---|
| Fast typed decisions (Jev client, mock, fallback, batching) | `system1_v10.py` |
| Strictly causal evaluation on a real talk | `eval_system1_v10.py` |
| Editor prompts (oracle / causal) and trace validation | `editor_trace_tools_v10.py` |
| Trace comparison metrics | `compare_traces_v10.py` |
| Transcript readers (SRT/VTT/JSON) | `transcript_io_v10.py` |
| Real pilot data and caveats | `data/nasa_stgermain_cop26/` |
| Why the video-editing demos matter | `EDITOR_REFERENCES_V10.md` |

Python 3.13, standard library only for everything above. CI runs `make verify` (`.github/workflows/ci.yml`).

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

Complete source/context reviews and independent editor traces for the acquired
tranche; fill missing domain strata; train/evaluate by **held-out source group**
(which also isolates talks). Normal training rejects ineligible bundles and empty
splits. `--pipeline-only` permits explicit plumbing checks and cannot earn promotion.
Dataset/evaluation artifacts are bound to source hashes, and the gate reproduces
the transparent baseline before accepting measurements. Browser rehearsal remains
a separately supplied evidence assertion; the gate cannot certify human quality.

This repository is public, but no open-source license is granted yet. Third-party systems referenced in the docs are architectural/integration precedents; the project should keep source/provenance and licensing boundaries explicit.
