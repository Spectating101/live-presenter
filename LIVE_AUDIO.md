# Continuous local speech input

The studio now has an **opt-in local English microphone path** alongside browser
speech recognition. It sends one-second PCM updates to an actual local ASR worker
and the approved-scene controller. It does not wait for browser sentence
endpointing. This implements the connection; physical microphone-to-projector
performance has not been measured.

## Use it on this machine

The optional `.venv-asr` environment and cached `tiny.en` model are already
available here. Other machines need the optional recognition setup in
`RECORDED_TALKS.md`; the normal studio and offline Python tests do not import or
require Torch/Whisper.

```bash
make studio-local
```

Open the private studio URL printed in that terminal, select a project, review
its prepared content and approve it. Open its projector, start rehearsal, and
enable **React to prepared cues · experimental**. Choose **Local English ·
experimental** under Speech input, then click **Enable microphone** and grant
browser microphone permission. Listening begins after model warmup. Jev advice
is optional and starts off.

The browser supplies mono 16 kHz audio through an AudioWorklet. It keeps up to
four seconds of past context and emits once per second. The requested audio
context rate is checked; unsupported capture or denied access produces an error
and releases the microphone. Browser speech recognition and typed rehearsal
remain available. Native capture still needs validation in the target browser.

Stop the microphone to keep the current visual without listening. Manual stage
controls or changing following switches cancel local capture and its pending
results; enable the microphone again to continue. **Stop rehearsal** returns the
projector to standby. A suspended/closed tab or stopped audio connection expires
the server capture after five seconds without audio updates.

## What keeps it current

- The audio worklet, browser uploader and server each retain a bounded pending
  slot. New audio replaces older pending windows. Worklet acknowledgements avoid
  accumulating messages while the browser main thread is paused.
- The recognizer runs in a separate, keyless child process. It generates at most
  48 tokens in one pass. A two-second process deadline covers job transfer and
  decoding; an overrun kills that owned child and restarts recognition. Restart
  has a warmup cost and can lose several seconds of speech.
- Audio has a two-second freshness budget, reduced by its reported capture age.
  Stale queued or decoded input is discarded. Approval, generation, monotonic
  audio sequence, hold and minimum display time remain authoritative.
- Stopping a microphone invalidates in-flight work without changing the selected
  visual. The engine checks expiry both before matching and before committing.
  Optional advice has a bounded wait of at most 1.2 seconds or the remaining
  budget. At most one guarded audio-path advisory call may remain outstanding. A late
  result cannot change the stage or grow an advisory queue.

The bounds control application work and stale-result authority. They are not a
wall-time SLA on a shared or suspended computer. Silence/repetition heuristics
are unchanged from `BOUNDED_AUDIO.md`; this is not a native streaming ASR model
or a guarantee against recognition errors. Local recognition is English only.

## Measured running pipeline

Two excerpts ran at normal wall-clock speed with optional Jev enabled, using the
same final code and approved packages. Startup was measured separately at about
2.8–2.9 seconds.

| Source excerpt | Updates | Median / p95 processing | Maximum | Skips / decoder timeouts | Observed visual changes |
|---|---:|---:|---:|---:|---:|
| Marshall, 40–130 s | 90 | 0.28 / 0.57 s | 0.70 s | 0 / 0 | 3 |
| Rosling, 280–420 s | 140 | 0.34 / 0.64 s | 1.44 s | 0 / 0 | 6 |

All 230 updates were processed; one Rosling output was rejected by the recognition
filter. Neither final run had expired input or a stage observer error. Across
both, processing median was 0.30 seconds and p95 was 0.60 seconds. These times
begin at server receipt and exclude up to one second of audio collection.

The **nine actual visual switches** were observed through the separate read-only
stage API **0.22–0.90 seconds after the corresponding audio chunk ended**. This
includes actual recognition, matching and stage HTTP observation; it does not
include browser capture or paint. Each excerpt displayed four distinct prepared
ideas, including its preselected opening. Rosling switched between comparison
and numeric views within one idea, so change count is not a topic-accuracy score.

An earlier diagnostic run exposed two decoder restarts and an advisory call that
took 5.56 seconds to finish. Stale authority checks prevented its late switch;
the outer advisory wait was added afterward. Fault-injection tests now exercise
late advice, decode timeouts, coalescing, capture cancellation and recovery. The
final clean samples do not establish how often failures occur; machine workloads
were shared and differed between runs.

Versioned evidence is in [`data/live_audio_pilot_v1.json`](data/live_audio_pilot_v1.json).
Detailed recognized text and observations remain in the ignored experiment
folders. Verification passes 108 offline Python tests and six Node capture
unit tests. The browser implementation is ready for manual validation, with
permission/resampling/physical-display behavior still unverified.

## Reproduce the running pipeline measurement

This feeds previously acquired audio to the **actual HTTP API and worker at
normal wall-clock pace** and observes the read-only stage API through long
polling. It uses no stored inference costs or virtual replay clock. The approved
project is copied to a temporary workspace; the original is left untouched.

```bash
python3 -m presenter.live_probe \
  --folder artifacts/recorded_talks/marshall \
  --asr-python .venv-asr/bin/python --offset-s 40 --duration-s 90 --jev \
  --out artifacts/recorded_talks/marshall/live-audio-probe.json
python3 -m presenter.live_probe \
  --folder artifacts/recorded_talks/rosling \
  --asr-python .venv-asr/bin/python --offset-s 280 --duration-s 140 --jev \
  --out artifacts/recorded_talks/rosling/live-audio-probe.json
```

Omit `--jev` to use prepared matching alone. Reproduction requires the existing
approved recording folder; preparation is documented in `RECORDED_TALKS.md`.
The probe reports startup separately, actual worker delays, dropped/expired
windows, restarts, observed visual changes and chunk-end-to-stage-API times.
Audio collection adds up to one second, and identifying an idea can require
several words beyond its coarse section boundary.

Browser access was previously declined, so no browser automation was retried.
AudioWorklet numeric/framing tests and client cancellation tests run in Node;
they are unit tests, not evidence of real browser capture or playback. W3C
references for the implementation are [Web Audio](https://www.w3.org/TR/webaudio/)
and [Media Capture](https://www.w3.org/TR/mediacapture-streams/).

The projector records `presenter-stage-dom` and
`presenter-stage-frame-opportunity` in the browser Performance timeline. The
second is two animation-frame callbacks after receipt; neither measurement proves
physical paint or projector latency. These hooks await browser validation.

## Privacy and remaining work

Live microphone PCM stays in bounded memory; the application does not save it.
Recognized rehearsal text is retained in the existing private project transcript.
Operator authentication and loopback/origin checks apply to every audio route;
the read-only projector capability cannot inspect or submit audio. Enabling Jev
can send recognized text and approved context to that existing service.

Next verify browser microphone permission, input resampling, stop/restart,
background-tab behavior and display timing on presentation hardware. Broader
noise/accent/language tests, independent editorial review and the reserved talks
remain necessary. None of these implementation checks promotes the separate
editorial corpus or establishes audience usefulness.
