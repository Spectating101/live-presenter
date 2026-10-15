#!/usr/bin/env python3
"""Compare two editor traces over one talk: how much of an oracle (full-future) edit survives a causal one.

Self-contained stand-in for the v9 oracle_benchmark until that module is in this repo.
Events match greedily when they overlap by >= `min_overlap` of the shorter event, or start within `onset_tol_s`.
"""
from __future__ import annotations
from statistics import median
import math
from typing import Any, Dict, List, Mapping, Sequence


def _overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    return max(0.0, min(a["end_s"], b["end_s"]) - max(a["start_s"], b["start_s"]))


def match_events(ref: Sequence[Mapping[str, Any]], cand: Sequence[Mapping[str, Any]], *, min_overlap: float = .5,
                 onset_tol_s: float = 3.0) -> List[tuple]:
    pairs, used = [], set()
    for i, r in enumerate(ref):
        best, best_score = None, -1.0
        for j, c in enumerate(cand):
            if j in used: continue
            shorter = max(1e-9, min(r["end_s"] - r["start_s"], c["end_s"] - c["start_s"]))
            ov = _overlap(r, c) / shorter
            if ov >= min_overlap or abs(r["start_s"] - c["start_s"]) <= onset_tol_s:
                score = ov - abs(r["start_s"] - c["start_s"]) / 1000
                if score > best_score: best, best_score = j, score
        if best is not None: used.add(best); pairs.append((i, best))
    return pairs


def compare(ref: Sequence[Mapping[str, Any]], cand: Sequence[Mapping[str, Any]], *, talk_s: float, **kw) -> Dict[str, Any]:
    if not math.isfinite(talk_s) or talk_s <= 0:
        raise ValueError("talk_s must be finite and positive")
    for trace in (ref, cand):
        for e in trace:
            if not (math.isfinite(e["start_s"]) and math.isfinite(e["end_s"]) and 0 <= e["start_s"] < e["end_s"]):
                raise ValueError("event times must be finite, nonnegative and increasing")
    pairs = match_events(ref, cand, **kw)
    n = len(pairs)
    fn = sum(ref[i]["function"] == cand[j]["function"] for i, j in pairs)
    rep = sum(ref[i]["representation"] == cand[j]["representation"] for i, j in pairs)
    lags = [cand[j]["start_s"] - ref[i]["start_s"] for i, j in pairs]
    def cov(trace):
        total, until = 0.0, 0.0
        for e in sorted(trace, key=lambda e: e["start_s"]):
            start, end = max(e["start_s"], until), min(e["end_s"], talk_s)
            total += max(0.0, end - start)
            until = max(until, end)
        return round(total / talk_s, 3)
    return {"ref_events": len(ref), "cand_events": len(cand), "matched": n,
            "recall": round(n / len(ref), 3) if ref else None, "precision": round(n / len(cand), 3) if cand else None,
            "function_agreement": round(fn / n, 3) if n else None, "representation_agreement": round(rep / n, 3) if n else None,
            "both_agree_of_ref": round(sum(ref[i]["representation"] == cand[j]["representation"] and ref[i]["function"] == cand[j]["function"] for i, j in pairs) / len(ref), 3) if ref else None,
            "median_onset_lag_s": round(median(lags), 2) if lags else None,
            "ref_screen_coverage": cov(ref), "cand_screen_coverage": cov(cand)}


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Score a candidate editor trace against a reference trace.")
    ap.add_argument("ref"); ap.add_argument("cand"); ap.add_argument("--talk-s", type=float, required=True)
    a = ap.parse_args()
    print(json.dumps(compare(json.load(open(a.ref)), json.load(open(a.cand)), talk_s=a.talk_s), indent=2))
