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
can update the shared live state, but this increment does not add a native
microphone capture adapter or finish headless intake/preparation. The previous
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

The next quality target is visual direction across different explanation types:
choose a useful representation, reveal a relationship, handle a genuine detour,
and integrate checked new material without requiring the audience to operate an
app. Evaluate engagement alongside comprehension and correctness, as specified
in `EXPLANATION_DESIGN.md`. A scripted motion sample cannot establish those
audience or autonomous-agent outcomes.
