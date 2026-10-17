# Bounded recognition experiment

This continues the [prepared reflex experiment](PREPARED_REFLEX.md). Preparation
and approved cue matching stay fixed. The change targets speech recognition
stalls before the prepared cue can reach the controller.

## Mechanism

`transcribe --bounded` runs one Whisper decoder pass per past audio window, with
an explicit output token budget (48 by default). It disables timestamps and does
not enter the transcription seek loop or retry decoding. This bounds generated
tokens, **not CPU wall time**. The experiment still uses one-second updates and
four seconds of past audio, on CPU with `tiny.en` and four Torch threads.

Obvious repeated characters or phrases are withheld from the controller. The
existing nonspeech probability and low log probability also jointly reject
output. These are conservative heuristics, not a voice activity detector or a
guarantee against hallucination. Raw output and rejection reasons remain in the
private recognition trace. Ordinary short repetition is retained. Reaching the
token budget is recorded; the potentially truncated output is still eligible for
matching, so the limit can lose a cue at the end of a window.

`run --fresh` simulates a serial recognition worker that chooses the **latest
already available audio window** when it becomes free. Older pending windows
are explicitly logged as dropped. Selection uses only audio arrival times and
the worker's current completion time, never future recognition results or the
reference. A dropped window's words cannot reach the controller. Four seconds of
overlapping context can retain cues from skipped windows, but missed cues remain
possible. A window already being decoded is not cancelled.

Every window is decoded separately to measure its cost before replay. The
freshness schedule is therefore a counterfactual simulation using those costs,
not an integrated streaming microphone implementation. It does not include model
startup, browser endpointing, paint, microphone capture or physical projection.
The original all-window path remains available for comparisons.

## Recorded results

The same two full recordings were rerun, with approved packages, cue/controller
code and reference sections checked against the previous experiment's hashes.
These are **95th-percentile chunk-end-to-decision delays**, excluding up to one
second of audio collection:

| Recording | Original queued local | Bounded, all windows | Bounded, fresh local | Bounded, fresh + Jev |
|---|---:|---:|---:|---:|
| Marshall, *Talk nerdy to me* | 12.28 s | 0.69 s | 0.69 s | 0.72 s |
| Rosling, *The magic washing machine* | 1.89 s | 2.19 s | 0.94 s | 0.96 s |

The worst new fresh-scheduled decision still took **1.47 seconds on Marshall and
3.39 seconds on Rosling**. Single-pass decoding alone did not fix Rosling's
queued tail. Other workloads were present on this shared CPU; original timings
were measured earlier, so this is not an isolated decoder speed benchmark.

Scheduling the **original** ASR costs with the fresh policy reduced local p95
delay to 1.47 seconds on Marshall and 0.93 seconds on Rosling, skipping 12 and 7
windows respectively. This isolates scheduling within the replay model. It still
cannot interrupt the original slow decode: Marshall's maximum remained 10.07
seconds. The new bounded traces needed zero and six skips respectively.

Both new local and Jev-assisted runs reached **all 12 prepared ideas**. Local
coarse chapter alignment was 97.3% on Marshall and 98.4% on Rosling. The early
conclusion/reference disagreement on Marshall remains; Rosling had no changes
outside coarse section expectations. Marshall's old alignment was 97.4%, so
lower delay did not improve every matching measure. These are development
references, not independent editorial or visual-quality scores.

The recognizer rejected three Marshall outputs and six Rosling outputs; one of
the latter was skipped before entering the simulated worker. Two Marshall and
four Rosling decodes reached the token budget. Jev made 10 and 81 calls, with no
failures in these runs. These counts do not establish general reliability.

Later coarse sections first received a matching visual after roughly 0–3.4
seconds on Marshall and 0–5.1 seconds on Rosling with optional Jev. A visual can
already be displayed when a section begins. Chunk-end processing latency does
not measure the time needed to hear enough words to identify the speaker's idea.

Hash-bound metrics and all ablations are in
[`data/bounded_audio_pilot_v1.json`](data/bounded_audio_pilot_v1.json). Original
results in `data/prepared_reflex_pilot_v1.json` are preserved. There is no new
microphone-to-projector measurement or empirical corpus/policy promotion here.

## Reproduce

Use the acquired, reviewed and approved experiment folders described in
[RECORDED_TALKS.md](RECORDED_TALKS.md). Run recognition for one talk at a time to
avoid competing for the measured CPU:

```bash
.venv-asr/bin/python -m presenter.recording transcribe \
  artifacts/recorded_talks/rosling/audio.wav \
  --out artifacts/recorded_talks/rosling/asr-bounded-1s-4s.json \
  --chunk-s 1 --window-s 4 --bounded --max-tokens 48
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr-bounded-1s-4s.json \
  --mode local --reflex --fresh
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr-bounded-1s-4s.json \
  --mode jev --reflex --fresh
python3 -m presenter.recording report \
  --folder artifacts/recorded_talks/rosling --reflex --fresh
```

Repeat for `marshall`. The report is `comparison-reflex-fresh.html`; older
`comparison-reflex.html` and recognition traces remain unchanged. The player
shows maximum delay, skipped windows and rejected outputs alongside the existing
alignment and latency measurements. Its layout and media synchronization remain
unverified because browser access was previously declined.

For an ablation, omit `--fresh` and supply a distinct `--out` replay filename.
Conversely, pass the old `asr-1s-4s.json` trace with `--fresh` and a distinct output
filename to isolate scheduling on the original measured recognition costs.
Never overwrite the original baseline results while running an ablation.
