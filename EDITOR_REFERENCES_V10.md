# Editor references: what the Claude video-editing demos teach us

Public demos show Claude editing and generating video from prompts (effects, illustrations, transitions, B-roll, captions).
They are **design references**, not training data: they are third-party creator posts, the raw videos and most prompts are not
published, and the claims are unverified. Nothing here may enter a training corpus without a per-item rights check
(`oracle_manifest_v10.py --strict-rights`).

## What carries over

| Demo pattern | Live Presenter equivalent |
|---|---|
| Editing runs in stages: intake, rough cut, graphics, second pass, captions + B-roll, export | intake = pre-brief and source compile (v8); rough cut = topic frontier; graphics = representation choice; second pass = intervention policy (prune); captions/B-roll = evidence/media; export = Chromium stage |
| "One recurring visual element transforms between scenes so it feels continuous" | v6 object continuity and morphing (stable semantic object IDs) |
| Scenes written as a pure function of time `t`, rendered via Playwright + ffmpeg | deterministic Chromium stage; replayable rehearsals |
| Low-resolution preview before the full render | backstage warming before public intervention |
| A pre-brief of assets and intent before editing | the pre-loaded context the live system gets before the talk |

## The one real difference: causality

An offline editor sees the whole recording. The live system sees only the past plus the pre-brief.
`editor_trace_tools_v10.py` therefore builds prompts in two modes: `oracle` (full future) and `causal` (transcript up to `t`).
Run the same editor in both on the same talk; the agreement gap is the price of causality, and the causal trace is the
fairest target for a live policy.

## How to use an editor (human, API model, or an in-session assistant)

1. `build_prompt(segments, context, brief=..., mode="oracle")` and send it to the editor.
2. `extract_json_rows(reply)` then `validate_editor_rows(rows, segments, context)`; fix or drop rejected rows, never auto-repair.
3. Put the clean rows into `assemble_oracle_bundle_v10.py` as one `--editor name:generic:path`, with at least two genuinely
   independent editors per talk (different models and a human; the same model with different temperatures is not independent).

## Sources (unverified creator material; rights belong to each creator)

- [awesome-claude-5-5-videos](https://github.com/athemeroy/awesome-claude-5-5-videos): index of demos; no raw MP4s redistributed
- [How to Make Videos with Claude Opus 5.5: A Deterministic Render Pipeline](https://huggingface.co/blog/karmen-beatapi/how-to-make-videos-with-claude-opus-5-5)
- [How to Use Claude Opus 5.5 to Make Videos with Code](https://magiccreator.ai/posts/how-to-use-claude-opus-5-5-to-make-videos)
- [Opus 5.5 Video: 30 Creator Examples, Demos, and Prompts](https://www.ai.joaoqueiros.com/blog/opus-5-5-video-motion-examples-prompts)
