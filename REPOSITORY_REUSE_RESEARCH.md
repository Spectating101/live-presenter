# Repository reuse survey — 20 October 2026

Several public projects are close to live speech-driven illustration. The best
reuse opportunities are visual routing, streaming speech stabilization,
asynchronous tool calls, source-figure extraction and richer native animation.
This is a targeted survey, not an exhaustive GitHub inventory. Candidates were
inspected through public source files and repository metadata, without running
their code, downloading models or opening a visible interface. Performance
claims below belong to the upstream authors and have not been reproduced here.

The public metadata and inspected-file hashes are recorded in
[the survey record](data/repository_reuse_survey_20261020.json). Retrieved source
snapshots remain in the ignored `artifacts/repo_research_20261020` directory.

## Closest systems

| Repository | Relevant implementation | Reuse judgment |
| --- | --- | --- |
| [timegravity/live-visuals](https://github.com/timegravity/live-visuals) | Local speech recognition feeds structured visual routing; renderers return PNG or MP4. Chart, diagram, image, photo and skip branches exist. | Closest functional reference. MIT. Study routing and stale-work handling; feed assets into our native output. Its complete GPU stack is unsuitable for this machine as specified. |
| [ramsrigouthamg/zeroprep](https://github.com/ramsrigouthamg/zeroprep) | Realtime audio directs hold, replace, focus and merge actions; uploaded assets and asynchronous generated imagery are supported. | Useful director/tool-call reference, MIT. Its React cards, slide layouts and PPT export are outside our output design. Adapt the director contract rather than adopting its frontend. |
| [jlia0/RealityTalk](https://github.com/jlia0/RealityTalk) | Published speech-driven augmented storytelling prototype; inspected spaCy/TextRank keyword extraction and Socket.IO search handoff. | Relevant research precedent for improvisational visual assistance. AGPL-3.0; old implementation, last push 2023. Reference rather than our new runtime foundation. |
| [Betakontext/slAIdshow](https://github.com/Betakontext/slAIdshow) | Speech transcription, prompt refinement and ComfyUI/cloud image generation connected through an asynchronous application. | Useful competing workflow to compare. README describes 6–10 second image updates despite its zero-latency wording. GitHub did not identify a license; resolve reuse permission before copying. |
| [ACADEE/Voice-to-Diagram](https://github.com/ACADEE/Voice-to-Diagram) | Voice-to-architecture-diagram example using a realtime model, Dagre and tldraw. | Narrow graph example. No license identified by GitHub at inspection; deprioritize copying. Its latency claim was not verified. |

`live-visuals` is more informative than a generic AI slide generator: its actual
Python implementation includes speech endpointing, speculative transcription,
partial-sentence handling, accumulated dictated measurements and visual-mode
selection. But `render_diagram` currently makes up to six horizontally arranged
boxes and connecting arrows. That alone would not deliver the mechanism
illustrations we want. Its photo retrieval takes an Unsplash result; it does not
establish pixel-level explanatory fit or source-verified factual grounding.
Our approved-data and image-review checks should remain authoritative.

Its reported 2–3 second still generation was tuned on a 48 GB NVIDIA GPU; the
README estimates roughly 20 GB for a smaller still-only stack. Local PCI
inventory shows Intel UHD Graphics 630 and no NVIDIA adapter. Those timings
cannot be transferred to this machine. The repository is also a small, young
project, with four commits visible at review. Treat it as an implementation to
evaluate, not a proven product replacement.

ZeroPrep's `app/api/realtime/route.ts` defines a structured `stage_visuals`
function. This is useful evidence that semantic direction can be separated from
rendering. Its directive to change the display on every meaningful turn should
not be imported unquestioningly: our evaluation must include distraction,
unnecessary changes and preservation of context. Read model names as the
project's configured dependencies, not as independently validated availability.

## Components worth evaluating

| Repository | Specific opportunity | Boundary |
| --- | --- | --- |
| [KoljaB/RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) | MIT streaming speech pipeline, voice activity detection, manual PCM input and a detailed text stabilizer with stable deltas and unstable previews. | Directly addresses our repeated rolling-window tails. Benchmark the CPU engines and finalization behavior against the existing recognizer; model licenses vary. |
| [moonshine-ai/moonshine](https://github.com/moonshine-ai/moonshine) | Streaming speech/intent runtime aimed at processing audio while the person is speaking. | Alternative ASR benchmark. LICENSE says source and streaming ASR models are MIT, with exceptions for listed legacy non-streaming non-English models. Select the exact model explicitly. |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | BSD-2-Clause Python voice/multimodal framework; inspected examples of asynchronous model tool calls that allow conversation to continue during slow work. | Useful for an unattended provider-backed research worker. It supplies orchestration, not useful image selection or a latency guarantee. A functioning model and procurement tools are still required. |
| [docling-project/docling](https://github.com/docling-project/docling) | MIT document conversion with an actual figure/table image-export example. | Automates the figure extraction we performed manually on a NASA PDF. Preserve source URL, page and bounding-box provenance. Full parsing can be expensive; test page-limited conversion. |
| [illuin-tech/colpali](https://github.com/illuin-tech/colpali) | Visual document retrieval that can search page images containing diagrams, charts and text. | Useful for finding a visual in supplied or newly fetched documents. Repository code is MIT; model terms are separate. Retrieval similarity does not establish factual correctness or explanatory fit. |
| [academa-labs/manimgx](https://github.com/academa-labs/manimgx) | Python animation API backed by Rust/wgpu, native MP4 output, mathematical diagrams and 3D scenes. Linux wheels include CPU Vulkan fallback. | Strong candidate for richer explanatory motion. Very new; test our machine. Own code is MIT, but README says native wheels as a whole are GPL-3.0-or-later because of x264. Reported M4 Pro rendering speed is not speech-to-visual latency. |
| [searxng/searxng](https://github.com/searxng/searxng) | Search service with HTTP API, result categories and JSON output when enabled. | Backstage candidate discovery, including image search. Public instances often disable JSON; use a controlled instance or existing provider. Search results still need source and pixel review. AGPL repository. |

## Recommended application to this project

1. **Extend visual direction.** Evaluate the structured router from
   `live-visuals` and the director actions in ZeroPrep against the same recorded
   speech. Translate accepted results into our visual commands. Keep native
   output, package integrity, Hold/Stop and source-based numeric calculations.
   Measure wrong representation choices and unnecessary changes as well as speed.
2. **Remove the active-operator research dependency.** Evaluate a provider-backed
   asynchronous worker using Pipecat's tool-call patterns, our existing search
   backend or SearXNG, and Docling figure extraction. Give an actual vision model
   candidate pixels plus the spoken question before granting display authority.
   Pipecat and Docling alone do not solve this judgment step. Measure from the
   first detour, retaining all retries and failures.
3. **Broaden useful native visuals.** Benchmark ManimGX headlessly for a small
   source-grounded mechanism or mathematical explanation. First prove native
   playback/render integration and local timing. A prewritten animation's render
   speed does not include generating, checking and directing a new explanation.
4. **Replace speech heuristics only after comparison.** Run RealtimeSTT and
   Moonshine on the existing PCM traces with a stable-text contract. Compare
   missed concepts, duplicate instructions, partial-word errors and cue-to-pixel
   latency. Keep the current recognizer available during that evaluation.

The immediate next experiment should be the unattended procurement worker:
find several candidate diagrams, extract only the relevant figure, inspect it
with a working vision provider, then display it if the topic is still current.
This targets the 64.77-second failure directly. No inspected repository has yet
been verified here to provide our complete preparation, factual grounding,
native direction and fast fresh-visual loop as a ready replacement.

## Implementation references

- [live-visuals routing and pipeline](https://github.com/timegravity/live-visuals/blob/main/web_app.py),
  [renderers](https://github.com/timegravity/live-visuals/blob/main/renderers.py).
- [ZeroPrep director contract](https://github.com/ramsrigouthamg/zeroprep/blob/main/app/api/realtime/route.ts).
- [RealtimeSTT stabilizer](https://github.com/KoljaB/RealtimeSTT/blob/master/RealtimeSTT/core/realtime_text_stabilizer.py).
- [Pipecat asynchronous tool example](https://github.com/pipecat-ai/pipecat/blob/main/examples/realtime/realtime-gemini-live-async-tool.py).
- [Docling figure export](https://github.com/docling-project/docling/blob/main/docs/examples/export_figures.py).
- [SearXNG API and JSON configuration](https://docs.searxng.org/dev/search_api.html).
- [ManimGX native rendering and packaging notes](https://github.com/academa-labs/manimgx#license).
