#!/usr/bin/env python3
"""Prompt builder + validator for LLM/human *editor* traces (oracle supervision).

An "editor" watches a talk transcript and decides, event by event, which
representation should appear and when.  Two modes mirror the benchmark in
ORACLE_BENCHMARK_V9.md:

  oracle  - the editor sees the WHOLE transcript (full future), like an offline video edit.
  causal  - the editor sees only transcript up to time t plus a pre-brief, like the live system.

The gap between the two is the price of causality.  Editors never run in the live
path; their output enters training only after validate_editor_rows() and the rights manifest.

Row keys (compatible with editorial_trace_v9.from_generic):
  start_s, end_s, function, representation, confidence, rationale, query
"""
from __future__ import annotations
import json
import math
from typing import Any, Dict, Iterator, List, Mapping, Sequence, Tuple

from representation_policy_v10 import REPRESENTATIONS, representation_available
from system1_v10 import DEFAULT_ACTS, REPRESENTATION_HINTS

ROW_SCHEMA = {"start_s": "float seconds", "end_s": "float seconds, >= start_s", "function": f"one of {sorted(DEFAULT_ACTS)}",
              "representation": f"one of {list(REPRESENTATIONS)}", "confidence": "0..1 how sure you are",
              "rationale": "one sentence: why this visual, here", "query": "what to look up/render (short)"}

_RULES = """You are an editor adding visuals to an explanatory talk. Each event is one moment where a visual
should APPEAR or CHANGE.  Rules:
- Edit sparingly: only where a visual clearly helps the audience. Most of the talk needs none.
- Pick the representation by what the speaker is doing, not by topic words alone.
- Use ONLY representations marked available.
- Events must not overlap, must lie inside the transcript, and should last at least 2 seconds.
- Reply with a JSON array of rows and nothing else."""


def _fmt_transcript(segments: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(f"[{float(s.get('start_s', s.get('start', 0))):.1f}-{float(s.get('end_s', s.get('end', 0))):.1f}] {s.get('text', '')}"
                     for s in segments)


def build_prompt(segments: Sequence[Mapping[str, Any]], context: Mapping[str, Any], *, brief: str = "",
                 mode: str = "oracle", until_s: float | None = None, from_s: float | None = None) -> str:
    if mode not in {"oracle", "causal"}: raise ValueError(f"mode must be oracle|causal, got {mode!r}")
    if mode == "causal":
        if until_s is None: raise ValueError("causal mode needs until_s")
        if not math.isfinite(until_s) or until_s < 0:
            raise ValueError("until_s must be finite and nonnegative")
        segments = [s for s in segments if float(s.get("end_s", s.get("end", 0))) <= until_s]
        scope = f"You can only see the transcript up to {until_s:.1f}s. Do not assume anything later."
        if from_s is not None:
            scope += (f" Earlier text is context only: emit events that START at or after {from_s:.1f}s and END by {until_s:.1f}s."
                      " Do not emit events for text before that window.")
    else:
        scope = "You can see the whole transcript, including what is said later."
    reps = "\n".join(f"- {r}: {REPRESENTATION_HINTS[r]}" + ("" if representation_available(r, context) else " (NOT available)")
                     for r in REPRESENTATIONS)
    acts = "\n".join(f"- {k}: {v}" for k, v in DEFAULT_ACTS.items())
    return (f"{_RULES}\n\n{scope}\n\nSpeaker's pre-brief (what the talk is about, sources on hand):\n{brief or '(none)'}\n\n"
            f"Discourse functions:\n{acts}\n\nRepresentations:\n{reps}\n\nRow schema: {json.dumps(ROW_SCHEMA)}\n\n"
            f"Transcript:\n{_fmt_transcript(segments)}\n")


def causal_checkpoints(segments: Sequence[Mapping[str, Any]], step_s: float = 30.0) -> Iterator[float]:
    if not math.isfinite(step_s) or step_s <= 0:
        raise ValueError("step_s must be finite and positive")
    end = max((float(s.get("end_s", s.get("end", 0))) for s in segments), default=0.0)
    t = step_s
    while t < end + step_s:
        yield min(t, end); t += step_s


def causal_windows(segments: Sequence[Mapping[str, Any]], step_s: float = 90.0) -> List[Tuple[float, float]]:
    """Consecutive (from_s, until_s) windows covering the talk; the last one is clipped to the talk's end."""
    if not math.isfinite(step_s) or step_s <= 0:
        raise ValueError("step_s must be finite and positive")
    end = max((float(s.get("end_s", s.get("end", 0))) for s in segments), default=0.0)
    out, a = [], 0.0
    while a < end - 1e-6:
        b = a + step_s
        if end - b < step_s / 3: b = end          # fold a tiny tail into the last window
        out.append((a, min(b, end))); a = b
    return out


def extract_json_rows(text: str) -> List[Dict[str, Any]]:
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < a: raise ValueError("no JSON array in editor reply")
    rows = json.loads(text[a:b + 1])
    if not isinstance(rows, list): raise ValueError("editor reply is not a list")
    return rows


def validate_editor_rows(rows: Sequence[Mapping[str, Any]], segments: Sequence[Mapping[str, Any]], context: Mapping[str, Any],
                         *, min_duration_s: float = 2.0) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (clean_rows, problems).  Bad rows are dropped, never silently repaired."""
    end = max((float(s.get("end_s", s.get("end", 0))) for s in segments), default=0.0)
    clean: List[Dict[str, Any]] = []; problems: List[str] = []
    for i, r in enumerate(rows):
        try:
            s, e = float(r["start_s"]), float(r["end_s"]); fn, rep = str(r["function"]), str(r["representation"])
            conf = float(r.get("confidence", 1.0))
        except (KeyError, TypeError, ValueError) as ex:
            problems.append(f"row {i}: malformed ({ex})"); continue
        if fn not in DEFAULT_ACTS: problems.append(f"row {i}: unknown function {fn!r}"); continue
        if rep not in REPRESENTATIONS: problems.append(f"row {i}: unknown representation {rep!r}"); continue
        if not representation_available(rep, context): problems.append(f"row {i}: {rep} not available in context"); continue
        if not (0 <= s < e <= end + 1e-6): problems.append(f"row {i}: time {s}-{e} outside transcript (0-{end})"); continue
        if e - s < min_duration_s: problems.append(f"row {i}: shorter than {min_duration_s}s"); continue
        if not 0 <= conf <= 1: problems.append(f"row {i}: confidence {conf} outside 0..1"); continue
        if clean and s < clean[-1]["end_s"] - 1e-6: problems.append(f"row {i}: overlaps previous event"); continue
        clean.append({"start_s": s, "end_s": e, "function": fn, "representation": rep, "confidence": conf,
                      "rationale": str(r.get("rationale", "")), "query": str(r.get("query", ""))})
    return clean, problems
