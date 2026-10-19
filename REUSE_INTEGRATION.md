# Upstream integrations and measured results

Two contained integrations now connect to the existing native explanation path:
Docling figure extraction and the MIT text stabilizer from RealtimeSTT. The
repository survey should have preceded some of our custom plumbing. These
components can save work without discarding the source/approval model, native
renderer, speech follower or cue-to-pixel measurements already implemented.

No visible window, browser tab, media playback or desktop capture was used.
The compact [experiment record](data/reuse_integration_experiments.json)
preserves both successful and failed attempts.

## Docling: integrated for draft material

`presenter.pdf_figures.DoclingFigures` runs the optional Docling dependency in a
separate Python process. It extracts figure candidates from up to three selected
PDF pages, retaining the original document hash, page number, bounding box,
caption, figure reference and extractor version. Pixel and output-byte limits,
cancellation and a process deadline bound the work. No provider credentials are
forwarded to the extraction process; models run locally on one CPU thread.

The same extractor can be supplied to `make_server(..., figure_extractor=...)`.
Authenticated project creation and source addition accept this source shape:

```json
{
  "name": "source.pdf",
  "base64": "PDF_BYTES_AS_BASE64",
  "extract_figures": {"pages": [14, 14]}
}
```

The original document and extracted images become draft source material. Normal
review and approval remain required. Extraction does not establish that a
candidate explains the question. In the NASA test, Docling extracted both the
mechanism diagram and a small logo. Neither receives automatic pixel-review
authority. The source-byte/page-bound cache also returns unreviewed candidates;
changed document bytes cannot inherit a cached extraction.

The optional server flag is `--figure-python .venv-research/bin/python`. This is
a backstage API capability; no new product interface was added. A headless
client requesting extraction should allow more than the normal 20-second
request timeout, up to the configured extraction deadline plus overhead.

For an isolated installation with CPU Torch:

```bash
python3 -m venv .venv-research
.venv-research/bin/python -m pip install torch==2.9.1 torchvision==0.24.1 \
  --index-url https://download.pytorch.org/whl/cpu
.venv-research/bin/python -m pip install -r requirements-research.txt
python3 -m presenter.pdf_figures --pdf SOURCE.pdf \
  --first-page 14 --last-page 14 --out-dir artifacts/new_figure_attempt
```

The development installation reused the machine's existing Torch libraries in
an ignored environment; system packages were not changed. Upstream Docling is
MIT licensed; models retain their own terms. Figure export uses the API shown
in [Docling's example](https://github.com/docling-project/docling/blob/main/docs/examples/export_figures.py).

Measured on the same NASA document used in the detour:

| Attempt | Result | Extraction wall time |
| --- | --- | --- |
| `docling_nasa_v1` | Two source-linked candidates | 18.68 s |
| `docling_nasa_v2` | Two source-linked candidates, separate process with model files available | 8.69 s |
| `docling_native_import_v1` | Extracted diagram imported, explicitly approved as a developer fixture, and rendered by Qt offscreen | 9.47 s |
| Same extractor's exact-source memory cache | Same unreviewed candidates | 5.66 ms lookup |

The first extraction overlapped a speech probe; these are development
observations, not a controlled latency benchmark. Model cache state was not
reset. Cache lookup excludes internet search, document download and semantic
visual inspection. The native fixture's candidate choice and approval were
explicit developer actions. This is not unattended visual selection.

## RealtimeSTT: experimental adapter, disabled by default

Only the upstream pure-Python text stabilizer is vendored, with its unmodified
source, MIT license, copyright, source blob hash and file hash in
`presenter/vendor/realtimestt`. The full recorder and ASR engines were not
installed. Its adapter operates inside our existing past-only PCM worker.
Unstable text stays diagnostic; accepted stable text can drive the follower.

Enable it explicitly with `make_server(..., stabilize_text=True)`, the server's
`--stabilize-text`, or this entirely headless experiment:

```bash
.venv-native/bin/python -m presenter.native_speech_probe \
  --out-dir artifacts/new_stabilizer_attempt --stabilize-text
```

The first run used upstream defaults: four space/punctuation confirmations were
too conservative for our one-second updates and short rolling windows. It
processed all audio but missed all four requested changes. The adjusted adapter
requires two such confirmations. It recovered all four changes, with no dropped
windows or ASR timeouts, but changed pixels appeared **0.97–2.25 seconds after
phrase completion**. Our prior default path measured 0.019–0.336 seconds on the
same authored cue fixture. This is a slower optional experiment, not a promoted
replacement or proof of improved accuracy. Continuous speech without acoustic
gaps, microphone noise and independent speakers remain unvalidated. The simple
acoustic segment detector is not a complete VAD model.

## Remaining work

Pipecat's async tool patterns, the `live-visuals` router and ManimGX are still
evaluation candidates, not installed integrations. Adding all three would not
by itself solve semantic visual selection or certify latency.

An unattended research worker still needs a functioning vision provider to
inspect candidate pixels against the current spoken question. Both configured
Google credential candidates were rejected with HTTP 400; no key values were
printed or persisted in experiment records. We have not bypassed this step by
calling metadata relevance a pixel review. Docling reduces manual figure work;
it does not by itself close the 64.77-second unprepared-topic loop.

Verification: offline suite 208 tests, three optional Qt skips; the separate
native suite ran 14 checks successfully. The existing historical preflight
still reports missing `runtime_v9` files; this increment does not restore that
old runtime or claim overall stage readiness.
