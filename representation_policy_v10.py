#!/usr/bin/env python3
"""Transparent oracle-distilled representation policy for Live Presenter v10.

The model is intentionally inspectable: confidence-weighted categorical counts
with hierarchical backoff and availability filtering.  It is a shadow adviser,
not an authority over grounding, visual grammar, or intervention safety.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from math import log
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
import json

REP_TO_KIND = {
    "chart": "chart", "flow": "flow", "timeline": "timeline", "map": "map",
    "evidence": "evidence", "media": "image_grid", "comparison": "comparison",
    "metric": "metric", "visual": "hero",
}
KIND_TO_REP = {
    "bar_chart": "chart", "line_chart": "chart", "chart": "chart",
    "flow": "flow", "concept_map": "flow", "timeline": "timeline", "map": "map",
    "evidence": "evidence", "source_card": "evidence", "quote": "evidence",
    "image_grid": "media", "comparison": "comparison", "metric": "metric",
    "definition": "visual", "hero": "visual",
}
REPRESENTATIONS = tuple(sorted(REP_TO_KIND))

def context_signature(context: Optional[Mapping[str, Any]]) -> str:
    c = dict(context or {})
    keys = ("has_dataset", "has_images", "has_sources", "graph_ready", "has_map_data", "has_timeline_data")
    return ";".join(f"{k}={1 if bool(c.get(k)) else 0}" for k in keys)

def representation_available(rep: str, context: Optional[Mapping[str, Any]]) -> bool:
    c = dict(context or {})
    if rep == "chart": return bool(c.get("has_dataset"))
    if rep == "media": return bool(c.get("has_images"))
    if rep == "evidence": return bool(c.get("has_sources"))
    if rep == "map": return bool(c.get("has_map_data"))
    if rep == "timeline": return bool(c.get("has_timeline_data"))
    return True

@dataclass(frozen=True)
class PolicyPrediction:
    function: str
    representation: Optional[str]
    scene_kind: Optional[str]
    confidence: float
    support: float
    coverage_source: str
    distribution: Dict[str, float]
    abstain: bool
    reason: str
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class OracleRepresentationPolicy:
    def __init__(self, artifact: Mapping[str, Any]):
        self.artifact = dict(artifact)
        self.global_counts = {k: float(v) for k, v in artifact.get("global_counts", {}).items()}
        self.by_function = {k: {r: float(v) for r, v in row.items()} for k, row in artifact.get("by_function", {}).items()}
        self.by_context = {k: {r: float(v) for r, v in row.items()} for k, row in artifact.get("by_context", {}).items()}
        cfg = artifact.get("config", {})
        self.smoothing = float(cfg.get("smoothing", .5))
        self.min_support = float(cfg.get("min_support", 2.0))
        self.min_confidence = float(cfg.get("min_confidence", .52))
        self.min_context_support = float(cfg.get("min_context_support", 3.0))
        self.max_entropy = float(cfg.get("max_entropy", .88))

    @classmethod
    def fit(cls, examples: Sequence[Mapping[str, Any]], *, smoothing=.5, min_support=2.0,
            min_confidence=.52, min_context_support=3.0, max_entropy=.88):
        global_counts = defaultdict(float)
        by_function = defaultdict(lambda: defaultdict(float))
        by_context = defaultdict(lambda: defaultdict(float))
        for ex in examples:
            fn = str(ex.get("function") or "augment")
            rep = str(ex.get("representation") or "visual")
            if rep not in REPRESENTATIONS: rep = "visual"
            raw_conf = ex.get("confidence")
            w = max(.20, 1.0 if raw_conf is None else float(raw_conf))
            global_counts[rep] += w
            by_function[fn][rep] += w
            by_context[f"{fn}|{context_signature(ex.get('context'))}"][rep] += w
        return cls({
            "version": 10,
            "schema": "live_presenter.oracle_representation_policy.v1",
            "config": {"smoothing": smoothing, "min_support": min_support,
                       "min_confidence": min_confidence, "min_context_support": min_context_support,
                       "max_entropy": max_entropy},
            "global_counts": dict(global_counts),
            "by_function": {k: dict(v) for k, v in by_function.items()},
            "by_context": {k: dict(v) for k, v in by_context.items()},
            "training_examples": len(examples),
        })

    @classmethod
    def load(cls, path: Path | str):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: Path | str) -> Path:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def _row(self, function: str, context: Mapping[str, Any]) -> Tuple[Dict[str, float], str]:
        contextual = self.by_context.get(f"{function}|{context_signature(context)}", {})
        if sum(contextual.values()) >= self.min_context_support: return contextual, "function+context"
        functional = self.by_function.get(function, {})
        if functional: return functional, "function"
        return self.global_counts, "global"

    def predict(self, function: str, context: Optional[Mapping[str, Any]] = None) -> PolicyPrediction:
        context = dict(context or {})
        row, source = self._row(function, context)
        support = float(sum(row.values()))
        prior_total = max(1e-9, sum(self.global_counts.values()))
        scores = {}
        for rep in REPRESENTATIONS:
            if not representation_available(rep, context): continue
            prior = self.global_counts.get(rep, 0.0) / prior_total
            scores[rep] = row.get(rep, 0.0) + self.smoothing * max(.05, prior)
        if not scores:
            return PolicyPrediction(function, None, None, 0.0, support, source, {}, True, "no feasible representation")
        total = sum(scores.values())
        dist = {k: v / total for k, v in scores.items()}
        rep = max(dist, key=lambda k: (dist[k], k))
        confidence = dist[rep]
        entropy = 0.0 if len(dist) <= 1 else -sum(p * log(max(p, 1e-12)) for p in dist.values()) / log(len(dist))
        abstain = False; reasons = []
        if support < self.min_support: abstain = True; reasons.append(f"support {support:.2f} < {self.min_support:.2f}")
        if confidence < self.min_confidence: abstain = True; reasons.append(f"confidence {confidence:.2f} < {self.min_confidence:.2f}")
        if entropy > self.max_entropy: abstain = True; reasons.append(f"entropy {entropy:.2f} > {self.max_entropy:.2f}")
        return PolicyPrediction(
            function=function, representation=rep, scene_kind=REP_TO_KIND.get(rep),
            confidence=round(confidence,4), support=round(support,3), coverage_source=source,
            distribution={k: round(v,4) for k,v in sorted(dist.items(), key=lambda x:x[1], reverse=True)},
            abstain=abstain, reason="; ".join(reasons) if reasons else "oracle policy recommendation"
        )

    def snapshot(self):
        return {"training_examples": self.artifact.get("training_examples",0),
                "functions": sorted(self.by_function), "config": dict(self.artifact.get("config",{}))}

def evaluate_policy(policy: OracleRepresentationPolicy, examples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total=len(examples); correct=covered=covered_correct=0; log_loss=0.0; rows=[]
    for ex in examples:
        pred=policy.predict(str(ex.get("function") or "augment"), ex.get("context") or {})
        target=str(ex.get("representation") or "visual")
        p=max(1e-9,pred.distribution.get(target,1e-9)); log_loss += -log(p)
        hit=pred.representation==target; correct += int(hit)
        if not pred.abstain: covered += 1; covered_correct += int(hit)
        rows.append({"example_id":ex.get("example_id"),"function":ex.get("function"),"target":target,
                     "prediction":pred.representation,"abstain":pred.abstain,"confidence":pred.confidence,
                     "support":pred.support,"hit":hit})
    return {"examples":total,"top1_accuracy":round(correct/total,4) if total else 0.0,
            "coverage":round(covered/total,4) if total else 0.0,
            "selective_accuracy":round(covered_correct/covered,4) if covered else None,
            "mean_log_loss":round(log_loss/total,4) if total else 0.0,"rows":rows}

def representation_for_kind(kind: Optional[str]) -> Optional[str]:
    return KIND_TO_REP.get(str(kind or ""))
