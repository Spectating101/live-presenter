#!/usr/bin/env python3
"""Utterance-by-utterance (strictly causal) System-1 evaluation against an editor trace.

For each caption segment the assessor sees ONLY text up to and including that segment, never anything later.
Decisions become events where the assessor is confident, did not abstain, and rates urgency >= threshold;
consecutive segments with the same representation merge.  The result is scored against the oracle trace
with compare_traces_v10.compare().

  python eval_system1_v10.py --backend mock                      # plumbing check, no key, no network
  JEV_API_KEY=... python eval_system1_v10.py --backend jev       # the real causal comparison
"""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from compare_traces_v10 import compare
from representation_policy_v10 import OracleRepresentationPolicy
from system1_v10 import Assessment, JevBackend, MockBackend, System1Assessor

DEFAULT_BUNDLE = Path(__file__).parent / "data" / "nasa_stgermain_cop26" / "bundle.json"
DEFAULT_ORACLE = Path(__file__).parent / "data" / "nasa_stgermain_cop26" / "trace_llm_oracle.json"


def events_from_assessments(segments: Sequence[Mapping[str, Any]], assessments: Sequence[Assessment], *,
                            urgency_threshold: float = 2.0, merge_gap_s: float = 2.0, min_event_s: float = 2.0) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for seg, a in zip(segments, assessments):
        if a.abstain or not a.representation or a.urgency is None or a.urgency < urgency_threshold: continue
        row = {"start_s": float(seg["start_s"]), "end_s": float(seg["end_s"]), "function": a.act or "continue",
               "representation": a.representation, "confidence": a.representation_confidence}
        last = events[-1] if events else None
        if last and last["representation"] == row["representation"] and row["start_s"] - last["end_s"] <= merge_gap_s:
            last["end_s"] = max(last["end_s"], row["end_s"])
        else:
            events.append(row)
    return [e for e in events if e["end_s"] - e["start_s"] >= min_event_s]


async def assess_causally(segments: Sequence[Mapping[str, Any]], context: Mapping[str, Any], assessor: System1Assessor, *,
                          concurrency: int = 8) -> List[Assessment]:
    sem = asyncio.Semaphore(concurrency)
    async def one(i: int) -> Assessment:
        past = " ".join(s["text"] for s in segments[:i + 1])        # nothing after segment i
        async with sem:
            return await assessor.assess(past, context=context)
    return list(await asyncio.gather(*(one(i) for i in range(len(segments)))))


async def evaluate(bundle: Mapping[str, Any], oracle: Sequence[Mapping[str, Any]], assessor: System1Assessor, **kw) -> Dict[str, Any]:
    seg, ctx = bundle["transcript"], bundle["context"]
    assessments = await assess_causally(seg, ctx, assessor)
    events = events_from_assessments(seg, assessments, **{k: v for k, v in kw.items() if k in ("urgency_threshold", "merge_gap_s", "min_event_s")})
    return {"talk": bundle["talk_id"], "strictly_causal": True, "segments": len(seg),
            "assessor": assessor.summary(), "events": events,
            "vs_oracle": compare(oracle, events, talk_s=seg[-1]["end_s"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["mock", "jev"], default="mock")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE)); ap.add_argument("--oracle", default=str(DEFAULT_ORACLE))
    ap.add_argument("--policy", help="count-table policy JSON used as fallback and for agreement stats")
    ap.add_argument("--urgency-threshold", type=float, default=2.0); ap.add_argument("--out")
    a = ap.parse_args()
    bundle = json.loads(Path(a.bundle).read_text(encoding="utf-8")); oracle = json.loads(Path(a.oracle).read_text(encoding="utf-8"))
    policy = OracleRepresentationPolicy.load(a.policy) if a.policy else None
    backend = JevBackend() if a.backend == "jev" else MockBackend()
    res = asyncio.run(evaluate(bundle, oracle, System1Assessor(backend, fallback=policy), urgency_threshold=a.urgency_threshold))
    res["backend"] = a.backend
    text = json.dumps(res, indent=2)
    if a.out: Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    main()
