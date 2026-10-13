# Pilot bundle: NASA "What NASA Knows from Decades of Earth System Observations"

- Talk: Karen St. Germain (NASA Director of Earth Science), COP26, about 13.6 minutes, 106 caption segments.
- Source: https://svs.gsfc.nasa.gov/31168 (caption file `transcript_StGermain.en_US.srt`, unmodified in `transcript.srt`).
- Rights: NASA content is generally not subject to copyright in the US; attribute NASA; do not imply NASA endorses this project
  (https://www.nasa.gov/nasa-brand-center/images-and-media/). Captions only; no video or third-party media is included.
  The SVS page states no separate usage notice, so re-check before any redistribution beyond research use.
- `trace_llm_oracle.json`: one LLM editor, **oracle mode** (saw the whole transcript), 32 events. `bundle.json` packages it.

## What this is, and is not

- **Is:** a worked pilot showing the ingestion path (SRT -> editor trace -> validated bundle) on a real talk.
- **Is not:** training evidence. One editor means no consensus and no independence; the context flags are *assumed* from what
  the talk visibly shows (data visualisations, maps), not measured from a runtime. The trace is also denser than the
  "edit sparingly" rule intends (visuals cover about 58% of the talk), so treat it as one editor's opinion.
- To make it count: add at least one genuinely independent editor (a human, or a different model family), and a **causal-mode**
  trace produced from a fresh context that has not seen the later transcript (see `editor_trace_tools_v10.py`).
