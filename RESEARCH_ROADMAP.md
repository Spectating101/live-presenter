# Research execution roadmap

Updated 2026-10-15. This is the current continuation of the v10 handoff, not a
claim that the historical full runtime has been restored or validated.

## Verified working baseline

- Python 3.13.5; offline tests, pilot comparison and mock causal replay run here.
- Integrated the restored trace/consensus and inherited modules from `main` with
  `claude/sharp-cerf-gb0llb` on `codex/presentation-readiness`.
- Jev credentials were found in the machine's existing secrets configuration.
  No key was copied into the repository. Both key aliases work; CLIs accept
  `--env-file` or `JEV_ENV_FILE` and read env files as data, without executing them.
- A persisted 20-call Jev probe resolved to `jev-1.13.0`: p50 222.4 ms,
  p95 418.0 ms, zero backend failures. An earlier probe observed a 5.3-second
  outlier. These small samples are machine/network observations, not an SLA.
- A corrected serial replay completed 106 NASA pilot captions without backend
  failures: p50 200.2 ms, p95 375.7 ms; abstention rate 0.547. Its 35 candidate
  events matched 15 of 32 oracle events: recall 0.469, precision 0.429,
  representation agreement on matches 0.400, both-label agreement over all
  reference events 0.094, median onset lag 5.76 s. This is one editor's opinion,
  not human editorial-quality evidence. No thresholds were tuned on this pilot.
- First acquisition tranche: 30 English caption candidates, 22 source groups,
  5.16 hours, 4,859 caption segments. Timing/duplicate audit passes. There are
  **zero empirical-eligible talks** until reviews and independent traces exist.
- 60 pending oracle-editor jobs are prepared. A job is a prompt and provenance
  record, not an annotation. Explicit model-family probes did not produce usable
  outputs; automatically routed model calls are not certified independent editors.

Local evidence: `artifacts/jev_bench.json`, `artifacts/jev_eval.json`,
`artifacts/readiness.json`, `artifacts/corpus_audit.json`, and
`artifacts/independent_review/review.txt`. Generated evidence stays git-ignored.
The source catalog is versioned in `data/corpus_sources_v10.json`.

## 1. Recover the full runtime

The repository still lacks the v1–v9 runtime chain, semantic/representation
broker, providers, visual grammar, stage surfaces, speech bridge and historical
tests. Neither this local filesystem search nor the original staging branch
contained the complete checkpoint. `runtime_v10` cannot import `runtime_v9`.

Recover the original source package identified by:

`sha256:6ba82011ada2523d802b6f1b767a7422c8c9e239c87ce211c86c8a150345a782`

Use `SOURCE_MANIFEST_V10.txt` to verify individual recovered files. Preserve current
System-1/transcript changes rather than overwriting the checkout wholesale.
Exit condition: runtime imports, recovered historical tests pass, and the actual
Chromium rehearsal is repeatable. Historical 101-test and browser results in
`HANDOFF.md` remain archival until reproduced here.

```bash
make doctor
python3 preflight_v10.py --require-stage  # currently exits 2, deliberately
```

## 2. Review and broaden the source corpus

Acquisition uses NASA's [documented SVS API](https://svs.gsfc.nasa.gov/help/).
The pinned catalog supports a reproducible download; raw captions are hashed.
Zero-duration/empty cues are omitted with their source indices logged; overlap
requires review. Sparse data-label animations are excluded. At most three
candidates come from one source page, and captions from one page share a split
group. Downloaded source files and prior annotations are preserved on rerun.

```bash
make corpus-acquire
make corpus-audit
```

Review each candidate for explanatory content, source-specific rights and any
third-party notices, transcript omissions, overlap with other recordings, speaker
and domain, and material actually available to a live stage. Keep combined
broadcasts/individual excerpts and near-duplicate versions in one source group.
The current science tranche includes interviews and narrated explainers; do not
report it as 30 stand-alone conference talks or six-domain coverage.

Record the actual license/rights basis and source-specific review evidence in
bundle metadata. Set `rights_status: "reviewed"` only after that review. Apply
[NASA's media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/),
including third-party exceptions and AI source/output attribution requirements.
Acquisition alone does not imply permission or NASA endorsement. No video,
imagery, logos or datasets are downloaded by this runner.

All asset flags start false because only captions are loaded. Set
`context_reviewed: true` after confirming this conservative configuration, or
bind real assets and update flags to match. Seeing a chart mentioned in a talk
does not establish that its dataset exists in the runtime.

Fill the remaining planned strata with reviewed sources: software/technical,
finance/economics, policy/social science, data-heavy and concept-heavy material.
Record sampling exclusions and review decisions. Exit condition: at least 30
reviewed, non-fixture talks with a defensible sampling profile.

## 3. Produce independent editorial supervision

```bash
make corpus-jobs
# Or name the actual model/reviewer families used:
python3 corpus_v10.py prepare-jobs --corpus-dir artifacts/corpus_tranche1 \
  --families human_reviewer independent_model
```

Use a fresh model/session or independent human reviewer per job. Editors may see
the whole transcript in oracle mode; they must not see each other's traces.
Record the actual model/reviewer identity, version, run/session ID, prompt hash,
raw output and generation settings. Two accounts using one model family are
not automatically independent. A human or distinct model family is preferred.

```bash
python3 corpus_v10.py attach-editor \
  --bundle artifacts/corpus_tranche1/TALK/bundle.json \
  --job artifacts/editor_jobs/TALK/FAMILY/job.json \
  --trace /path/to/editor_output.json --name EDITOR --version EXACT_VERSION
```

Import validates events, prompt/context/transcript hashes and preserves the raw
trace hash. It rejects duplicate editor names and stale inputs. Completed jobs
are preserved when preparing prompts again. Audit flags reused imported trace
hashes. After inspecting independence evidence, set `independent_editors: true`;
the importer deliberately does not certify independence from a family label.
These declarations document a review; they do not cryptographically prove it.

Exit condition: at least two independent, versioned traces per eligible talk;
inspect agreement, disagreements, density and asset feasibility. Keep single
editor and synthetic runs marked as pipeline checks.

## 4. Train and reproduce a held-out baseline

Normal training rejects unresolved corpus checks and empty train/eval splits.
Related source groups stay together. Empirical training requires at least two
editor votes per consensus example; single-editor events cannot count as
multi-editor consensus. Talk/source overlap and duplicate transcript failures
must be resolved before training.

```bash
python3 train_oracle_policy_v10.py /path/to/reviewed/bundles/*.json \
  --out-dir artifacts/research
python3 oracle_manifest_v10.py /path/to/reviewed/bundles/*.json \
  --strict-rights --out artifacts/research/source_manifest.json
```

The manifest's rights check verifies that a rights field is present; the corpus
audit separately requires an explicit completed review. Neither tool grants a
license. Dataset and evaluation artifacts contain source/dataset/policy hashes.
Promotion verification reloads source bundles and reproduces splits, counts,
policy and held-out rows/metrics, rejecting stale or mismatched artifacts.

For plumbing only:

```bash
python3 train_oracle_policy_v10.py data/nasa_stgermain_cop26/bundle.json \
  --pipeline-only --out-dir artifacts/pilot
```

The single pilot currently falls entirely in evaluation and trains an empty
table. It is labeled pipeline-only; its output is not a useful learned policy.

Exit condition: reviewed corpus, nonempty isolated splits, reproducible count
baseline, and inspected per-domain/availability/disagreement results. Future
rankers must beat this baseline on unseen groups without tuning on the test set.

## 5. Evaluate causality and operational latency

```bash
make bench
make eval-jev
# If the key is held in a separate file:
JEV_ENV_FILE=/path/to/existing/credentials.env make bench eval-jev
```

Current caption text and prior context are separate inputs. A complete caption
becomes available at its end; simulated serial inference finishes after measured
latency, including any queueing. Candidate events begin at completion and end at
the next decision or talk end. Abstention ends a candidate interval. Every
decision, resolved model and token count is retained; malformed responses and
timeouts abstain, and incomplete evaluations exit nonzero.

Compare oracle agreement, event density, onset lag, abstention and availability
by held-out group. Add provider readiness, speculative waste and cache hits only
when actual runtime instrumentation exists. Caption replay excludes STT and
rendering. Measure microphone-to-projector latency and failures on the intended
presentation machine before any live-readiness claim.

## 6. Rehearse in shadow mode and enforce promotion gates

The restored runtime must preserve the semantic broker, grounding ledger, visual
grammar and stage lock. Jev/the learned policy may advise or warm; they cannot
escalate HOLD/WITHHOLD to SHOW. Test API failure, timeout, missing assets, off-script
speech, manual lock and long sessions in Chromium and then on real hardware.

```bash
python3 policy_gate_v10.py \
  --dataset artifacts/research/oracle_dataset_v10.json \
  --evaluation artifacts/research/oracle_policy_eval_v10.json --mode canary
```

Gate rejection exits 2. Canary still requires 30 empirical-eligible non-fixture
talks, 150 examples, 40 held-out examples, coverage >=0.65 and selective accuracy
>=0.75, isolated source groups and browser rehearsal evidence. Active thresholds
remain 100 talks, 500 examples, 100 held-out examples, coverage >=0.80 and
selective accuracy >=0.82, with warnings cleared. Pipeline-only runs cannot
promote. The browser CLI flag is an operator assertion: supply it only with
actual saved rehearsal evidence; it is not a browser test.

## 7. Validate usefulness and release

Run a bounded study with independent human judgments on unrelated rehearsals.
Predefine the comparison, sampling, outcome and failure criteria before viewing
test results. Distinguish model/editor agreement from audience usefulness.
Version source catalog, reviews, editor provenance, frozen train/eval groups,
policy, evaluation, benchmark and browser evidence together.

Final release requires a reproducible clean checkout, current tests, documented
runtime startup, physical presentation rehearsal, no unresolved critical
grounding/authority failures, and empirical gates earned from real evidence.
Until then, keep the research branch reviewable and the learned layer in shadow.
