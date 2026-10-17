# Recorded-talk audio experiments

This lane tests the preparation-first studio using a real recording rather than
typed examples. It extracts mono audio and a silent reference video, recognizes
bounded audio chunks locally, passes each recognized utterance through the actual
`Studio.transcript` controller, and records when each approved scene would appear.
A local comparison player puts the original video beside the app's scene renderer
with one shared audio control. The player reconstructs saved decisions; it does
not rerun inference when seeking.

## First completed development experiment

Source: Hans Rosling, [The magic washing machine](https://www.ted.com/talks/hans_rosling_the_magic_washing_machine),
TEDWomen 2010. This has a narrative, historical numbers, an animated energy
diagram, photographs and a physical prop. The actual downloaded media is about
539 seconds long. Source statistics are historical talk claims, not current facts.

The preparation partner received the complete **untimed transcript** in advance.
It initially combined the historical energy picture with a future projection and
numbered several parallel responses. A preparation discussion separated those
ideas and removed the false sequence before approval. The resulting development
package contains seven ideas and eighteen visuals. Codex reviewed the source
support for this isolated experiment; there was no independent human sign-off.

The live follower received **audio-derived recognition**, not the official
captions. `tiny.en` processed 90 consecutive six-second chunks with no future
audio, caption hints or reference frames supplied to recognition. The same
recognized chunks and approved package were used for local and Jev-assisted runs.
No semantic thresholds were tuned on this talk during the experiment.

Observed results in the final verification run:

| Observation | Local matching | Jev-assisted matching |
|---|---:|---:|
| Prepared ideas displayed | 6 of 7 | 7 of 7 |
| Visual changes during the audio | 5 | 6 |
| Coarse chapter alignment during scored time | 65.4% | 82.2% |
| Chunk end to decision, median / p95 | 0.40 / 0.56 s | 0.66 / 0.92 s |
| Invalid early decision timestamps | 0 | 0 |

The chapter reference was written before replay results were inspected, using
the argument, official cue starts, and sampled original video frames. It is a
**coarse development reference written by the implementation operator**, not
independent editorial supervision. It excludes six seconds on each side of
chapter boundaries, uses an approximate 3.3-second media intro offset, and allows
neighboring fairness/burden ideas during a short passage with no dedicated prepared
concept. The preselected opening contributes scored time. The percentages do not
measure visual quality, factual accuracy, audience understanding or generalization.

The important failures are visible in the trace:

- Jev reached the concluding books/learning idea; local matching never did.
- First matching visuals for later chapters arrived about **10–37 seconds late**
  relative to coarse section starts. Chunking accounts for up to six seconds;
  conservative matching of short, imperfect utterances adds more delay.
- The original conveys quantitative relations with animated graphics and uses
  photographs/props. This text-only prepared package uses cards, comparisons and
  a flow. It has no supplied dataset or imagery and does not reproduce the
  original's visual richness.
- “All ideas displayed” does not mean every moment was well assisted. A held
  visual can remain stale while the speaker moves on.

Recognition took about 36.3 seconds of CPU processing for 538.6 seconds of audio
on this machine, after approximately 3.3 seconds of model readiness. The final run attempted 89
advisory calls; one was unavailable and used the conservative local fallback.
Successful calls resolved to `jev-1.13.0`. These are development
measurements, not service guarantees. Six-second chunk fill time, browser rendering,
physical audio input and projector latency are excluded from the processing figures.

Machine-readable pilot summary: `data/recorded_talk_pilot_v1.json`. Detailed
recognition, decisions, package, references and media remain in the ignored local
experiment directory. Later reruns can vary; the summary preserves the final verification run.

## Reproduce a recording experiment

FFmpeg and FFprobe are needed for media preparation. Network access is needed for
acquisition, initial model download, preparation conversation and optional Jev
advice. Other than the optional recognition dependency, the runner uses Python's
standard library. It uses the machine's existing Copilot/Jev authentication.

```bash
python3 -m presenter.recording acquire-ted \
  https://www.ted.com/talks/hans_rosling_the_magic_washing_machine \
  --folder artifacts/recorded_talks/rosling

python3 -m presenter.recording prepare --folder artifacts/recorded_talks/rosling
```

The preparation command prints the revision and full draft. To discuss/review it
in the existing studio, start the server against this workspace, open its private
terminal URL, and select the presentation:

```bash
python3 -m presenter.server --data-dir artifacts/recorded_talks/rosling/studio
```

Stop that server before using commands that write the workspace. The runner uses
the same single-writer lock as the studio. Resolve any blocking questions and
inspect the quotes, paraphrases, numeric context and visual relationships before
approving. Approval is never automatic. Alternatively, after reviewing the CLI
draft, explicitly supply its current revision:

```bash
python3 -m presenter.recording approve --folder artifacts/recorded_talks/rosling \
  --revision 1 --reviewed --reviewer 'Your name'
```

Install local recognition in an optional environment, or use an existing Python
interpreter that already contains Whisper:

```bash
python3 -m venv .venv-asr
.venv-asr/bin/python -m pip install -r requirements-recorded-audio.txt
.venv-asr/bin/python -m presenter.recording transcribe \
  artifacts/recorded_talks/rosling/audio.wav \
  --out artifacts/recorded_talks/rosling/asr.json --model tiny.en --chunk-s 6
```

This project was exercised with `openai-whisper==20250625` on Python 3.13.5, CPU,
four Torch threads. The recognizer is local; no OpenAI API call or key is used.
See the [Whisper source and installation instructions](https://github.com/openai/whisper).
Recognition uses only the current chunk, with no prior-text prompt. Short chunks
can break words or sentences and reduce transcription quality.

Before viewing replay outputs, write `reference.json` in the experiment directory.
Record the approved `package_hash`, reviewer identity, independence status, timing
basis, `boundary_exclusion_s`, and `spans`. Each span contains `start`, `end`,
`label`, `acceptable_concept_ids`, and a description of the `original_visual`.
Add source-specific `visual_comparison_notes` and declare any ambiguous/uncovered
passages. A reference for one generated package cannot score a different package.
Treat this as a development review unless independently authored and validated.

```bash
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr.json --mode local
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr.json --mode jev
python3 -m presenter.recording report --folder artifacts/recorded_talks/rosling
```

Open `artifacts/recorded_talks/rosling/comparison.html` locally. Keep its adjacent
`audio.wav` and `video.mp4` files in place. The report bundles the actual scene
renderer and CSS and does not need a studio capability or send data externally.
Browser access was declined during implementation, so the player layout, media
synchronization and physical microphone/projector operation remain unverified.
HTML/JSON binding, JavaScript syntax and controller data flow are tested separately.

## Timing and scope

The replay is accelerated rather than wall-clock playback. ASR release time is
`max(chunk_end, previous_asr_completion) + measured_asr_duration`. The serial
controller starts at the later of that release and its prior completion. The
actual controller uses an injected audio clock, preserving its minimum dwell;
real adviser request time advances that clock. No complete chunk can influence
a recorded decision before its audio ends and recognition completes. An initial
approved opening is deliberately displayed before recognized speech.

The original video is a **comparison reference, not the only correct visual
answer**. Camera cuts are not automatically editorial events. Full-file Whisper
segment timestamps would not establish causal recognition, so this runner reads
independent bounded chunks instead. Source, audio, preparation, ASR, package,
controller and runner hashes are recorded. Replay runs copy the approved workspace
into separate local/Jev workspaces and leave the preparation project untouched.

All media/transcripts stay local and git-ignored; only source links, code and
measurement summaries are versioned. TED content remains subject to its
[usage policy](https://www.ted.com/about/our-organization/our-policies-terms/ted-talks-usage-policy).
This runner does not grant redistribution rights or imply TED endorsement.

## Next experiments

`PREPARED_REFLEX.md` records the subsequent one-second rolling-audio experiment
on Rosling and Melissa Marshall's short concept-driven talk, including a speech
recognition backlog failure. `data/recorded_talk_sources.json` still reserves the
visual/data-heavy talk by David McCandless, which has not been run or scored.
`BOUNDED_AUDIO.md` documents the subsequent limited-decoding and stale-window
experiment on the same two recordings; the old baseline remains available.
Test that recording with the frozen controller before tuning on its results.
Also add a condition with separately supplied notes/datasets rather than the
complete talk transcript, and a second reviewer who cannot see system outputs.

The first engineering target is earlier reliable topic transitions from recent
past speech, followed by richer approved visual assets. Re-score changes on the
development talk, then assess them on the reserved talks. This experiment does not
complete or promote the separate multi-talk editorial training corpus.
