# Supplied visual evidence and deliberate defaults

The studio can now prepare supplied PNG/JPEG images alongside documents and CSV
data. Each idea can have a presenter-selected default visual. The local follower
and optional Jev adviser respect that default; discussing research evidence no
longer automatically selects a quotation card. An explicit request such as
“show the source: historical evidence is compared with popularity” can still
select its prepared evidence view.

## Use it in a presentation

1. Attach notes, a CSV dataset and any static PNG/JPEG graphics. Describe each
   image's meaning and intended use by filename in the notes or discussion.
   Use a neutral filename when the audience is meant to guess its meaning: source
   filenames appear in the visual footer.
2. Discuss the audience, argument, missing context and visual relationships.
   Conversation mode receives extracted text and image descriptions, not image
   pixels. Inspect the supplied image yourself before approving its use.
3. Preview each idea's alternatives and choose **Use as default** below the
   visual that should normally accompany that idea.
4. Review and approve the new revision, then rehearse. Choosing a different
   default revokes the previous approval. Finish the rehearsal before editing.

PNG/JPEG images are limited to 512 KB each, 4096 pixels per side, eight million
pixels and about 1.5 MB combined per presentation. The existing eight-material
limit includes image files. Reduce large images before attaching them. Supplied
bytes are preserved inside the local source and approved package, so the
projector and standalone comparison reports do not depend on external image URLs.
The existing stage capability exposes approved scenes only; draft imagery remains
in the operator workspace. Image bytes and default selection are covered by the
approval hashes.

Image scenes preserve a supplied graphic. They do not extract its data, verify
its factual claims, generate new pixels or recreate animation, footage or
interactive filtering. CSV charts continue to use loaded numeric values. Give
historical values and counterfactual quantities explicit context in the dataset,
title and preparation discussion.

## Follow-up development experiment

`data/supplied_visual_plan_v1.json` fixes two conditions before their follower
outputs: the previous McCandless ten-idea package with the new view policy, and
an operator-curated twelve-idea package with five original frames, a two-row
historical emissions CSV and explicit defaults. Both reuse the exact previous
audio recognition trace. This repairs known development failures; it is not a new
holdout or independent editorial evaluation.

The supplied frames cover financial areas, media fears, the seasonal pattern,
the historical evidence map and the political diagram. The CSV transcribes only
the two values explicitly stated in the volcano passage: 150,000 tons emitted by
the volcano and 345,000 tons that grounded planes would have emitted **if flown**.
These are historical source claims, not current measurements. Splitting the soil
metaphor from the seasonal pattern, and the design conclusion from the volcano,
gives those worked examples their own ideas and defaults. This changes several
preparation factors; it cannot isolate the causal effect of images alone.

The additional-material manifest records every source digest, the approval's
source hash and package hash. Replay and the paced audio probe reject undeclared
or changed supplemental inputs. Each generated report identifies that original
frames were supplied in advance. The earlier transcript-only players and first
outputs remain intact.

First-pass observations:

| Condition | Ideas shown | Within-idea changes, local / Jev | Intended asset selected in fixed windows, local / Jev |
|---|---:|---:|---:|
| Previous ten-idea package, new view policy | 10/10 | 2 / 6 | 0% / 0% (assets absent) |
| Supplied-assets twelve-idea package | 12/12 | 2 / 2 | 99.10% / 94.59% |

The previous transcript-only policy made 10 / 17 within-idea changes on that
ten-idea package. The local follow-up selects all five supplied image scenes and
the historical emissions chart. It briefly changes the political diagram to a
text comparison around 965–969 seconds; the two view changes are preserved rather
than tuned away after seeing the result. The chart appears around 1020 seconds,
addressing the previous generic-definition hold.
The seasonal-pattern scene has a neutral title, but its source filename
`breakup-pattern.jpg` can hint at the answer before the spoken reveal. The frozen
package retains that editorial flaw; the asset-selection percentage does not
detect it.

The local full replay has 0.81-second p95 chunk-end processing. The Jev replay is
materially worse: 12 of 34 advisory calls were unavailable, with 4.99-second p95
and 25.47-second maximum chunk-end delay. Advisory wall time itself reached about
25 seconds. This accelerated runner queues stage decisions and does not apply
the live PCM worker's freshness deadline; network stalls can therefore accumulate
backlog. It does not establish cloud-assisted near-live reliability. No causality
violation occurred, and all first outputs are preserved.

A separate 90-second, playback-speed local-audio excerpt (730–820 seconds) passed
through the actual HTTP/ASR worker and read-only stage observer: all 90 updates
processed, no drops/rejections/timeouts, 0.31-second median, 0.71-second p95 and
0.92-second maximum processing latency. The supplied historical evidence image
was observed at the stage API. This excludes audio collection, browser rendering
and physical display latency; the opening is preselected before excerpt speech.
A second run of the same excerpt with Jev enabled also processed 90/90 updates
without drops or timeouts, at 0.82-second p95 and 1.51-second maximum. The probe
does not log advisory call counts, so enabled mode does not prove a remote call
occurred or reproduce the full-replay failures.

In addition to coarse topic matching, predetermined windows check whether the
specified image/chart is actually displayed. This measures availability and
selection of the intended prepared asset, not visual quality or audience learning.
Static source frames remain limited by the 854×480 recording. The visual-CV/senses
and relative-military sections still lack original graphics, and the living-image
section does not recreate interactive filtering. Independent editorial and
audience review remain pending. Browser automation was previously declined;
browser image rendering, player layout and physical display timing remain
unverified.

Detailed follow-up results are in `data/supplied_visual_results_v1.json`. The local
index is `artifacts/recorded_talks/supplied-visuals-index.html`; media, images,
transcripts and workspaces stay ignored. See [`VIDEO_COMPARISONS.md`](VIDEO_COMPARISONS.md)
for the preserved transcript-only tests.
`data/visual_review_template_v1.json` is an unfilled source-first review form for
an independent reviewer; its presence is not a completed review.
