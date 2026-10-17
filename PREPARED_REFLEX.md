# Prepared reflex experiment

Establish meaning before rehearsal, then react to prepared cues during speech.
This adds an **experimental, opt-in** cue path to the existing controller. It
does not establish instantaneous voice-to-screen performance.

## What changed

- Rehearsal start compiles a finite lexical index from approved concepts,
  aliases, quotations and linked source passages. It is cached by approved
  package/source hashes, so it can recognize source language omitted from a short
  summary without doing generative work during speech.
- Clear, distinctive cues take a local path with no adviser request. Ambiguous
  locally supported ideas can use optional Jev advice, supplied with the current
  idea and up to eight seconds of recent past. Off-topic speech holds.
- Repeated phrases are checked across the whole supplied material. Repetition
  alone cannot turn an ambiguous fragment into a reflex. An early version jumped
  to the conclusion on “loaded the laundry” during the opening; this motivated
  the general ambiguity check and its regression test.
- The projector waits for version changes through an authenticated long poll,
  replacing half-second polling. Reflex mode omits decorative transitions.
- Approval, presenter hold, manual navigation, minimum dwell, sequence checks and
  stale-result rejection remain authoritative. The feature starts off.

Enable **React to prepared cues · experimental** in rehearsal. Jev advice is a
separate switch. Cue scores are lexical heuristics, not calibrated probabilities.

## Measured reaction and recorded audio

The warm-index, clear-title HTTP test used 40 eligible cues on this machine:
**11.9 ms median, 24.7 ms p95, 26.0 ms maximum**, without a network adviser.
It measures recognized cue submission through the read-only stage API response.
The normal 2.5-second display dwell was satisfied with an injected rehearsal
clock, never disabled. Exact prepared titles are a best-case test. ASR, browser
paint, display hardware and ambiguous intent are excluded.

```bash
python3 -m presenter.latency --folder artifacts/recorded_talks/rosling \
  --samples 40 --out artifacts/prepared_cue_latency.json
```

The faster audio experiment updates **once per second**, recognizing at most the
latest **four seconds of already-heard audio**. Overlapping windows provide
context without waiting six seconds for every update. No future audio or official
caption timing is supplied to recognition or the follower. Whisper is repeatedly
invoked on bounded windows; it is not a native streaming recognizer here. See the
[upstream maintainer's streaming explanation](https://github.com/openai/whisper/discussions/2).

Two real recordings used the same final cue rules:

| Recording | Prepared ideas reached | First matching visuals for later sections |
|---|---|---|
| Hans Rosling, *The magic washing machine* | 7 of 7 | about 0–9 seconds with optional Jev |
| Melissa Marshall, *Talk nerdy to me* | 5 of 5 | about 0–5 seconds |

The opening is excluded from those onset ranges. Zero means the prepared idea
was already displayed when the coarse section began, not that it was inferred
before hearing it. The local-only Rosling run also waited about thirteen seconds
on the efficiency/green-energy section. The complete spoken response therefore
remains slower than the low-level cue reaction.

These are **development recordings**, with complete untimed talk transcripts
supplied as advance preparation. Marshall was not used to tune the rules before
its first replay; neither reference is independently authored. The references use
approximate intro offsets and coarse sections. One reference disagreement remains
in each recording: returning to the historical energy idea during the projection,
and an early conclusion during a recap before the communication equation. These
are inspectable disagreements, not proof that every change is right or wrong.

Hash-bound measurements are in `data/prepared_reflex_pilot_v1.json`. Older
six-second results remain in `data/recorded_talk_pilot_v1.json`. The newer test
changes both recognition cadence and controller behavior; it does not isolate
either change's effect. Coarse alignment is not visual quality or audience
usefulness. Preselected openings and boundary exclusions affect that score.

The recognizer also exposed a serious tail-latency failure. On intro audio it
generated repetitive text: a Rosling window took about four seconds, and a
Marshall window took about 9.5 seconds. Serial queued processing then produced
about **12.3 seconds p95 chunk-end-to-decision delay** in the Marshall replay,
despite much lower typical processing times. It was not an actual new thought by
the presentation agent. The current replay preserves this backlog rather than
hiding it. Bounded decoder work, non-speech handling and explicit stale-window
dropping need validation before this recognizer configuration is suitable live.
The subsequent [bounded recognition experiment](BOUNDED_AUDIO.md) tests those
changes while preserving the original results described here.

## Reproduce

Acquire, prepare, review and approve material as in `RECORDED_TALKS.md`, then use
the optional recognition environment:

```bash
.venv-asr/bin/python -m presenter.recording transcribe \
  artifacts/recorded_talks/rosling/audio.wav \
  --out artifacts/recorded_talks/rosling/asr-1s-4s.json \
  --model tiny.en --chunk-s 1 --window-s 4
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr-1s-4s.json --mode local --reflex
python3 -m presenter.recording run --folder artifacts/recorded_talks/rosling \
  --asr artifacts/recorded_talks/rosling/asr-1s-4s.json --mode jev --reflex
python3 -m presenter.recording report --folder artifacts/recorded_talks/rosling --reflex
```

This writes `comparison-reflex.html`, preserving the old comparison. Recognized
text is labeled with its full past window. Source, ASR, package, controller,
cue-index, lexical-helper and runner hashes are retained. Media, transcripts,
detailed traces and local credentials remain git-ignored.

## Remaining latency limits

The browser microphone still acts on **final recognition results**. Interim words
stay backstage. One-second rolling audio is currently a recorded-file experiment,
not a replacement for the browser microphone path. Browser endpointing can add
delay before a cue reaches the fast controller.

Browser access was previously declined. The long-poll contract is verified through
HTTP, but browser layout, playback synchronization, paint, microphone and physical
projector behavior remain unverified. The 12–25 ms processing result must not be
presented as measured microphone-to-projector latency.

Next, measure actual microphone endpointing and display paint, then assess stable
incremental recognition. Reducing waiting must not introduce more wrong visual
changes. Reserved new talks and independent review remain necessary before general
accuracy or release claims.
