# Visual-only native output

The audience output is the chart or illustration itself. No webpage, sidebar,
cards, controls, presentation frame or generic slide heading appears around it.
Qt [paints the output directly](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainter.html);
this path does not load a browser engine. Data
labels, axes and an explicitly requested comparison are part of the explanation.

Automated work must remain headless so the user's screen remains available.
This rule is also in `AGENTS.md`. Exported video and images are inspected as
files; do not open a player, browser tab or fullscreen window automatically.

## Run headlessly

The native dependency is optional and separate from the stdlib backend:

```bash
python3 -m venv .venv-native
.venv-native/bin/python -m pip install -r requirements-native.txt
make native-preview
make native-test
```

`make native-preview` writes `artifacts/native_motion_v1/explanation-motion.mp4`
and `report.json` using Qt's offscreen platform. The file is 14 seconds,
1280×720 at 24 fps, encoded as H.264. It has no audio. Cue times are scripted,
and the existing engine processes the text at those times. The report identifies
the input, source values, decisions, arithmetic and missing evaluation layers.

For static frames or reduced motion:

```bash
.venv-native/bin/python -m presenter.native --demo --export artifacts/native_frames
.venv-native/bin/python -m presenter.native --demo --reduced-motion --export-motion artifacts/native_reduced_motion
```

The offscreen path does not require an X11 session, desktop screenshot or browser.
It explicitly sets `QT_QPA_PLATFORM=offscreen` before constructing QApplication.
Optional fullscreen product use is available through `presenter.native --demo`
or read-only `--store PATH --project ID`; do not run those visible modes during
automated work unless the user specifically asks. The Linux visible Qt backend
also needs the normal X11 runtime libraries; this machine lacked
`libxcb-cursor.so.0`, which was unpacked into the ignored native environment
rather than changing system packages. This does not affect offscreen exports.

## What is dynamic now

- Chart geometry and numerical labels are correct from the first frame. An
  earlier staggered entrance distorted relative bar lengths during the reveal;
  that effect was removed. Movement is reserved for emphasis and relationships.
- A prepared category cue shifts emphasis within the same chart. Categories,
  values and their positions remain available for comparison.
- An explicit two-category comparison computes the difference and, when valid,
  the ratio from the approved values. A connecting bracket grows between the
  selected rows. Spoken numerical claims are not used as the calculation.
- Moving to another measured quantity updates the axes and data. Each view uses
  its own correct units and zero-inclusive scale. Different physical quantities
  are not treated as a continuous interpolation of the same measurement.
- Source-image annotations reuse decoded pixels. Motion traces a leader to the
  referenced part; the short label appears beside it. Reduced motion applies the
  final state immediately. There are no perpetual decorative loops.

These are initial rendering behaviors, not the full visual repertoire or proof
of sophisticated autonomous direction. The exported sample uses illustrative
measurements: flow 12/18/24 L/min and electrical power 90/145/230 W. Therefore,
Low→High is +12 L/min and 2× for flow, but +140 W and approximately 2.56× for
power. Heat removal was not measured; no efficiency claim follows.

## Backend connection and boundaries

`VisualOutput` reads the same approved package and live state as the existing
speech follower. The native reader can attach directly to a local project store;
it requires neither an HTTP display page nor operator credentials. It checks the
approval integrity, clears on Stop/revocation, and keeps the last valid visual
when an unsupported text template is requested. A new approval cannot inherit
an old package's visual. Images, annotated images, charts and single measured
values are supported. Arbitrary footage playback and newly generated mechanism
illustrations are not implemented here.

The demo's terminal text is a rehearsal input. Existing ASR and research workers
update the shared live state. The headless speech probe below exercises that
connection with real paced audio. It does not add a physical native microphone
capture adapter or finish headless intake/preparation. The previous
web studio remains a legacy diagnostic/operator tool; it is not the target
audience output or the intended presentation experience.

## Verification scope

Offscreen checks cover actual Qt rendering, source integrity, same-visual focus,
computed comparisons, Hold, Stop and reduced motion. The output widget has no
child UI widgets. Export audit files record that no visible window was opened
and no desktop was captured. Those records describe the explicit offscreen code
path, not a physical projector measurement.

Earlier static text-to-paint callback probes ranged from about 4–29 ms across
the small local runs, with variation from initialization and machine load. These
exclude microphone capture, ASR, internet procurement, animation settling and
physical display. The old seconds-long retrieval measurements remain relevant
to unprepared material. Removing the webpage does not remove those delays.

## Speech to visuals and a fresh detour

```bash
make native-speech SPEECH_OUT=artifacts/native_speech_new_attempt
# With an active connected web-capable agent, in a separate fresh directory:
.venv-native/bin/python -m presenter.native_speech_probe \
  --out-dir artifacts/native_speech_detour_new_attempt --unprepared
```

Both commands force Qt offscreen. They synthesize local speech with FFmpeg's
libflite, then deliver **actual PCM at one-second intervals**, with only the
available past four seconds passed to local tiny.en recognition. Future speech
and captions are never passed to preparation or the follower. The prepared CSV
contains two measurements and no heat-pipe material. The harness records native
pixels during the replay and muxes the input audio into `speech-visual.mp4`.
It does not play it. `report.json` binds cue times, ASR rows, visual state,
changed-pixel captures, source hashes and code fingerprints. Newly captured
pixels enter the video at the next frame boundary; missed frame intervals retain
the previous pixels rather than backdating a new illustration.

The already-visible starting chart is excluded from responsive successes.
Recognized suffixes of a recently committed transcript are suppressed for the
four-second overlap window. This prevents the tail of “compare low and high”
from becoming a separate “high” focus instruction. Later repetitions and new
modifiers remain actionable. This is conservative deduplication, not complete
word-level speech alignment; rapid intentional repetitions can be withheld.

`--unprepared` adds a repeated heat-pipe mechanism question at 42 seconds. It
starts the authenticated research bridge and writes connection details to a
private ignored `connection.json`. **An active agent must read the current
`/api/research/job`, browse, inspect a useful visual, and return it through
`/api/research/result`.** The probe itself does not run an autonomous vision
provider. Without the agent, requests expire and the current visual stays.
Never print connection credentials or open its web interface for this test.

An image's `visual_review` must carry its exact SHA-256, method
`connected_agent_pixel_inspection`, reviewer, the exact pending utterance,
observed pixel content and explanatory fit. Review is bound to both the image
bytes and the pending request. Metadata-only images remain backstage. A review
is an **authenticated agent attestation**, not independent app verification;
creator, license and source attribution remain attached. Stop, Hold, approval
and freshness checks still apply. This handoff is implemented and tested; a
working unattended visual research provider is still needed for product use.

The first cold detour attempt (`artifacts/native_speech_unprepared_v1`) did
procure and display an inspected NASA mechanism figure absent from preparation,
then returned to the prepared flow chart. However, it took **64.77 seconds from
the first question** (60.69 seconds after that phrase ended), including a
55-second agent timeout. The successful retry took 6.13 seconds at the backend.
That retry is not the cold latency. Repeated questions are one episode in the
scoring, so a late answer cannot reset the clock. The agent's search, download,
figure extraction and pixel inspection occurred during the running replay.
The diagram is static; it is not newly generated animated mechanism content.

The same cold run handled all 126 audio windows without a drop or ASR timeout;
that does not compensate for slow research. Its prepared changes appeared
between 45 ms before and 336 ms after phrase completion. These are four
development-authored cues, not a latency distribution or a real-speaker study.
Subsequent prepared-only runs verify the overlap fix; the cold detour was not
rerun after that fix. These measurements exclude physical capture and display,
and the fixture uses zero editorial dwell. Complete run details and shortcomings
are in [the compact experiment record](data/native_speech_experiments.json).

The final prepared-only run (`artifacts/native_speech_v3`) used unchanged code:
all four changes appeared 0.019–0.336 seconds after phrase completion,
1.625–2.701 seconds after phrase onset. All 40 windows were processed without
drops or timeouts; ASR startup took 3.19 seconds before replay. The comparison
remained visible until the next quantity. This records useful local progress,
not a claim that arbitrary speech or arbitrary fresh visual requests are solved.

The next quality target is visual direction across different explanation types:
choose a useful representation, reveal a relationship, handle a genuine detour,
and integrate checked new material without requiring the audience to operate an
app. Evaluate engagement alongside comprehension and correctness, as specified
in `EXPLANATION_DESIGN.md`. A scripted motion sample cannot establish those
audience or autonomous-agent outcomes.
