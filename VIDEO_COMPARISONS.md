# Expanded TED audio/video comparisons

The separately labeled follow-up in [`SUPPLIED_VISUALS.md`](SUPPLIED_VISUALS.md)
adds actual image assets, explicit defaults and a small historical CSV. The
transcript-only first-pass results below remain unchanged.

Two additional talks have now completed full audio-only follower tests with the
controller frozen at `bfeebe9f9b826eac343cd16f318d6e65533e825d`:
[Derek Sivers, How to start a movement](https://www.ted.com/talks/derek_sivers_how_to_start_a_movement)
and [David McCandless, The beauty of data visualization](https://www.ted.com/talks/david_mccandless_the_beauty_of_data_visualization).
These extend the earlier Rosling and Marshall development experiments to four
recordings. They demonstrate prepared topic following and expose preparation and
visual-selection gaps; they do not establish audience usefulness or a general
replacement for presentation software.

## First-pass results

Each new recording was split into mono audio and silent reference video. The
preparation partner received its full untimed transcript. During following, local
Whisper `tiny.en` recognized only past audio: one-second updates, four seconds of
past context, one decoding pass, 48 tokens, four CPU threads. The follower received
neither official caption timing nor original video frames. Local and Jev-assisted
conditions shared the same package, audio recognition and frozen controller.

| Talk / preparation | Duration | Ideas shown | Coarse topic alignment, local / Jev | Chunk end to decision p95, local / Jev |
|---|---:|---:|---:|---:|
| Sivers, source-reviewed five-idea draft | 2:53 | 5/5 | 96.36% / 96.39% | 1.50 / 1.51 s |
| McCandless, original partial five-idea draft | 18:00 | 5/5 | 54.37% / 54.37% | 0.79 / 0.82 s |
| McCandless, assisted ten-idea preparation | 18:00 | 10/10 | 99.91% / 99.92% | 0.79 / 0.80 s |

The full-talk runs are **accelerated scheduling simulations using measured ASR
costs**, not measurements of continuous playback-speed execution. There were no
causality violations or adviser failures in these six runs. Sivers skipped three
stale windows in each mode; both McCandless conditions skipped none. Jev was called
13, 43 and 30 times respectively and changed little in these aggregate results.
These observations do not establish that advice is unnecessary on other talks.

References were fixed before inspecting each talk's follower outputs and are
bound to the approved package. They were written by the implementation operator,
with an approximate media intro offset and six seconds excluded on both sides of
every section boundary. Only **87.3 seconds** of Sivers and **951.3 seconds** of
McCandless count toward the percentages. The opening is preselected, and ambiguous
recap/broad-conclusion passages have declared acceptance rules. These are coarse
development checks, not independent accuracy scores. No runtime or cue-rule tuning
was performed after seeing these new results.

## What comparison with the original video reveals

Sivers's prepared flows and comparisons summarize roles in a movement, but the
original hillside footage *demonstrates* how individuals join and a crowd grows.
That temporal evidence is absent. The local trace also jumps prematurely to
momentum at 22.87 seconds, then returns to the first-follower idea at 26.04 seconds.
The high chapter score hides that wrong switch. First appearances of later topic
visuals lag coarse section starts by up to about 4.7 seconds in the local run.

McCandless is the more demanding visual test. The original uses scaled financial
areas, fear timelines, seasonal patterns, sensory proportions, relative military
measures, evidence/popularity bubbles, interactive filters and a political map.
Neither package was supplied those graphics or the underlying datasets. Textual
definitions and comparisons can explain some relationships, but cannot show the
patterns the speaker points at. Source-frame and package reviews were recorded
before follower outputs; no audience comprehension score was assigned.

Even the ten-idea package's near-perfect topic score conceals two issues:

- The local trace makes **19 visual changes**, including **10 within the same
  idea**. Six alternate between explanatory and evidence cards during the
  supplement section. Editorial usefulness of those changes remains unvalidated.
- During the final volcano comparison, the local trace retains the generic
  information-design definition rather than selecting the prepared historical
  emissions comparison. Matching the chapter does not mean showing the most
  useful scene. Topic transitions still take roughly 3–7 seconds from coarse
  section starts, despite processing p95 below one second.

Jev makes 26 visual changes in the expanded condition, including 17 within one
idea, compared with the local trace's 19 and 10. Its tiny coarse alignment gain
therefore does not establish better editorial behavior.

The experiments identify separate needs: prepare all substantial ideas, provide
the actual visual evidence, and choose the useful view within the current idea.
Fast processing alone does not solve those tasks.

## Actual playback-speed audio check

The first 172 seconds of Sivers's 172.8-second recording were also sent at
playback speed through the actual authenticated PCM HTTP API, persistent local
recognizer, controller and read-only stage observer. All 172 updates were
processed; none were dropped, expired or timed out. Five recognition outputs were
rejected. All five ideas appeared, with six observed visual changes. Processing
latency was **0.41 s median, 0.91 s p95, 1.95 s maximum**, after a 3.58-second model
startup. The six observed changes reached the stage API 0.21–0.69 seconds after
their audio windows ended. Actual stage observations give 96.21% coarse alignment
against the same previously fixed reference, including a brief premature momentum
switch.

This measures native audio processing at wall-clock pace. It excludes up to one
second of audio collection, the speech needed to disambiguate an idea, browser
capture/paint and physical display latency. It is not an instantaneous-live claim.
The command emitted final metrics after cleanup and wrote a complete measurement,
but its outer shell reported exit 143; that anomalous wrapper status is preserved
in the result audit rather than reported as a clean process exit.

## Preparation outcome, including failures

Sivers required clarification before approval: the first follower creates a shared
action, crowd counts are rhetorical, and the recap returns to an earlier idea.
The package still has no footage scene.

McCandless's initial valid Copilot draft supplied five broad ideas and omitted
data-soil/Facebook, visual-CV/senses and political perspectives. Those passages
remain in the partial condition's scoring denominator; displaying all five
prepared ideas therefore does not imply full-talk coverage. A subsequent expanded
request failed exact-quotation checks. A long quote-repair request also failed;
the operator had supplied 10,748 characters to an app that stores only the first
5,000. A shorter 3,848-character request with exact quote candidates succeeded.
Source review then corrected a mystery dataset and its Facebook reveal being
presented as two separate examples.

The ten-idea condition is **operator-assisted Copilot preparation**, not automatic
preparation success. Both original and expanded packages, failure logs, source
references and first follower outputs are preserved separately. The original
draft was approved only as an explicitly incomplete evaluation condition. Neither
condition has independent human approval.

## Inspect and reproduce

On the evaluation machine, open
`artifacts/recorded_talks/comparison-index.html`. It links the original video / actual
scene-renderer players for all four talks, including both McCandless conditions.
Each player uses a shared audio control and can switch local/Jev traces. Media,
transcripts, approved workspaces and detailed traces remain local and ignored.
Browser automation was previously declined; player layout/synchronization and
physical microphone/projector operation remain unverified.

Versioned evidence:

- `data/expanded_video_plan_v1.json`: controller fingerprints and prospective design.
- `data/expanded_video_plan_addendum_v1.json`: assisted preparation condition,
  failures and correction, committed before either McCandless follower run.
- `data/expanded_video_references_v1.json`: package-bound references and visual reviews.
- `data/expanded_video_results_v1.json`: metrics, preparation audit, artifact hashes
  and the separately measured Sivers paced run.

The acquisition, discussion, review and approval workflow is in
[`RECORDED_TALKS.md`](RECORDED_TALKS.md). After fixing a package-bound reference
before viewing outputs, use:

```bash
.venv-asr/bin/python -m presenter.recording transcribe \
  artifacts/recorded_talks/sivers/audio.wav \
  --out artifacts/recorded_talks/sivers/asr-bounded-1s-4s.json \
  --chunk-s 1 --window-s 4 --bounded --max-tokens 48
python3 -m presenter.recording run --folder artifacts/recorded_talks/sivers \
  --asr artifacts/recorded_talks/sivers/asr-bounded-1s-4s.json \
  --mode local --reflex --fresh
python3 -m presenter.recording run --folder artifacts/recorded_talks/sivers \
  --asr artifacts/recorded_talks/sivers/asr-bounded-1s-4s.json \
  --mode jev --reflex --fresh
python3 -m presenter.recording report --folder artifacts/recorded_talks/sivers \
  --reflex --fresh
```

Use a new experiment folder for reruns rather than overwriting first-pass evidence.
Preparation outputs, inference timings and network responses can vary; new
packages require new references. Copied media and transcripts are not redistributed
by this repository.

## Next evidence needed

Supply notes, datasets, image assets and clip permissions as advance material;
agree on required evidence with the presenter before approval. Then repeat on new
talks with an independent source-first reviewer who has not seen system outputs.
Score topic coverage, useful view selection, missing evidence, distracting changes
and transition delay separately. Test pauses, repetitions, paraphrases and reordered
sections rather than only replaying the exact supplied transcript. Complete a
physical microphone/browser/projector rehearsal to measure the remaining end-to-end
delay. These experiments do not promote the separate editorial training corpus.
