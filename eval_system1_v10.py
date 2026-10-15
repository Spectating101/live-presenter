#!/usr/bin/env python3
"""Replay complete captions with causal inputs and latency-adjusted advisory events.

Caption text is available at its END, never its start. Completion times simulate
a serial assessor using measured request latency. This is an offline replay,
not a microphone, stage, or end-to-end presentation benchmark.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from compare_traces_v10 import compare
from jev_credentials_v10 import load_jev_env
from representation_policy_v10 import OracleRepresentationPolicy
from system1_v10 import Assessment, JevBackend, MockBackend, System1Assessor, System1Error

DEFAULT_BUNDLE = Path(__file__).parent / "data" / "nasa_stgermain_cop26" / "bundle.json"
DEFAULT_ORACLE = DEFAULT_BUNDLE.with_name("trace_llm_oracle.json")


def validate_segments(segments: Sequence[Mapping[str, Any]]) -> None:
    if not segments:
        raise ValueError("transcript must contain at least one segment")
    last_end = 0.0
    for i, s in enumerate(segments):
        start, end = float(s["start_s"]), float(s["end_s"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError(f"segment {i}: invalid start/end")
        if start < last_end:
            raise ValueError(f"segment {i}: overlapping or unordered captions")
        if not isinstance(s["text"], str):
            raise ValueError(f"segment {i}: text must be a string")
        last_end = end


def decision_times(segments: Sequence[Mapping[str, Any]], assessments: Sequence[Assessment]) -> List[float]:
    if len(segments) != len(assessments):
        raise ValueError("one assessment is required per caption")
    ready, previous = [], 0.0
    for seg, a in zip(segments, assessments):
        if not math.isfinite(a.latency_ms) or a.latency_ms < 0:
            raise ValueError("latency must be finite and nonnegative")
        previous = max(float(seg["end_s"]), previous) + a.latency_ms / 1000
        ready.append(previous)
    return ready


def events_from_assessments(segments: Sequence[Mapping[str, Any]], assessments: Sequence[Assessment], *,
                            urgency_threshold: float = 2.0, merge_gap_s: float = 0.0,
                            min_event_s: float = 0.0) -> List[Dict[str, Any]]:
    """Hold each candidate from completion until the next decision, clipped to talk end.

    Abstention ends the candidate interval. Optional duration/gap filters are
    retrospective scoring transforms; the default applies neither.
    """
    validate_segments(segments)
    if not math.isfinite(urgency_threshold) or not 0 <= urgency_threshold <= 3:
        raise ValueError("urgency_threshold must be in 0..3")
    if any(not math.isfinite(v) or v < 0 for v in (merge_gap_s, min_event_s)):
        raise ValueError("duration/gap filters must be finite and nonnegative")
    ready = decision_times(segments, assessments)
    talk_end = float(segments[-1]["end_s"])
    events: List[Dict[str, Any]] = []
    for i, a in enumerate(assessments):
        start = ready[i]
        end = min(ready[i + 1] if i + 1 < len(ready) else talk_end, talk_end)
        if start >= end or a.abstain or not a.representation or a.urgency is None or a.urgency < urgency_threshold:
            continue
        row = {"start_s": start, "end_s": end, "function": a.act or "continue",
               "representation": a.representation, "confidence": a.representation_confidence}
        last = events[-1] if events else None
        if (last and last["representation"] == row["representation"]
                and last["function"] == row["function"] and start - last["end_s"] <= merge_gap_s + 1e-9):
            last["end_s"] = end
        else:
            events.append(row)
    return [e for e in events if e["end_s"] - e["start_s"] >= min_event_s]


async def assess_causally(segments: Sequence[Mapping[str, Any]], context: Mapping[str, Any], assessor: System1Assessor, *,
                          concurrency: int = 1) -> List[Assessment]:
    validate_segments(segments)
    if concurrency != 1:
        raise ValueError("serial causal replay requires concurrency=1; use bench for request latency")
    assessments, past = [], ""
    for seg in segments:
        assessments.append(await assessor.assess(seg["text"], context=context, recent_context=past))
        past = (past + " " + seg["text"]).strip()[-assessor.window_chars:]
    return assessments


async def evaluate(bundle: Mapping[str, Any], oracle: Sequence[Mapping[str, Any]], assessor: System1Assessor, **kw) -> Dict[str, Any]:
    seg, ctx = bundle["transcript"], bundle["context"]
    assessments = await assess_causally(seg, ctx, assessor, concurrency=kw.get("concurrency", 1))
    events = events_from_assessments(seg, assessments, **{k: v for k, v in kw.items()
                                                       if k in ("urgency_threshold", "merge_gap_s", "min_event_s")})
    ready = decision_times(seg, assessments)
    summary = assessor.summary()
    return {"schema": "live_presenter.causal_eval.v2", "talk": bundle["talk_id"], "strictly_causal": True,
            "timing_model": "caption_end_plus_serial_request_latency", "authority": "advisory_only",
            "limitations": ["Offline caption replay; excludes STT, rendering and physical stage latency.",
                            "Asset context is supplied by the bundle, not measured from a stage.",
                            "Editor agreement is not a measure of human editorial quality."],
            "segments": len(seg), "assessor": summary,
            "status": "backend_failed" if summary["backend_failures"] == summary["calls"] else
                      "degraded" if summary["backend_failures"] else "ok",
            "decisions": [{"input_available_s": s["end_s"], "ready_s": t, **a.to_dict()}
                          for s, t, a in zip(seg, ready, assessments)],
            "events": events, "vs_oracle": compare(oracle, events, talk_s=seg[-1]["end_s"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", choices=["mock", "jev"], default="mock")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--oracle", default=str(DEFAULT_ORACLE))
    ap.add_argument("--policy", help="count-table policy JSON used as fallback and for agreement stats")
    ap.add_argument("--timeout-s", type=float, default=5.0)
    ap.add_argument("--env-file", help="Jev credentials file; or set JEV_ENV_FILE (default: optional .env)")
    ap.add_argument("--urgency-threshold", type=float, default=2.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        bundle = json.loads(Path(a.bundle).read_text(encoding="utf-8"))
        oracle = json.loads(Path(a.oracle).read_text(encoding="utf-8"))
        policy = OracleRepresentationPolicy.load(a.policy) if a.policy else None
        if a.backend == "jev":
            load_jev_env(a.env_file)
        backend = JevBackend(timeout_s=a.timeout_s) if a.backend == "jev" else MockBackend()
        res = asyncio.run(evaluate(bundle, oracle, System1Assessor(backend, fallback=policy),
                                   urgency_threshold=a.urgency_threshold))
    except (System1Error, ValueError, KeyError, OSError) as e:
        ap.exit(2, f"evaluation failed: {e}\n")
    res["backend"] = a.backend
    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in {"events", "decisions"}}, indent=2))
    if res["status"] != "ok":
        ap.exit(2, "backend failures recorded; evaluation is incomplete (see artifact decisions)\n")


if __name__ == "__main__":
    main()
