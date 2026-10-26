#!/usr/bin/env python3
"""System-1 backends for Live Presenter: fast, typed, probabilistic decisions.

A System-1 model (TypeSafe Jev) answers bounded questions -- discourse act,
topic shift, representation family, warm-now, urgency -- in one batched call.
Open-ended reasoning stays with a generative model elsewhere.

Authority: everything here is ADVISORY.  Output may rank and warm; it never
escalates HOLD/WITHHOLD to SHOW and never replaces the grounding ledger,
visual grammar, or intervention policy.  Any backend failure degrades to the
count-table policy (representation only) or to abstention.

API: https://api.typesafe.ai/openapi.json (POST /v1/systemone, GET /v1/models,
Bearer auth).  Key is read from JEV_API_KEY / TYPESAFE_API_KEY, never stored.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence

from representation_policy_v10 import (
    REPRESENTATIONS, OracleRepresentationPolicy, representation_available,
)

JEV_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"

# Provisional: align with the broker's act vocabulary once the v9 checkpoint lands.
DEFAULT_ACTS = {
    "define": "Introduces or defines a term or concept.",
    "explain": "Explains how or why something works.",
    "relate": "Connects the current idea to another idea or earlier point.",
    "compare": "Contrasts two or more things.",
    "quantify": "Gives numbers, magnitudes, or trends.",
    "substantiate": "Cites evidence, sources, or support for a claim.",
    "exemplify": "Gives a concrete example or case.",
    "summarize": "Wraps up or recaps.",
    "continue": "Continues the same point with no new structure.",
}
REPRESENTATION_HINTS = {
    "chart": "Numbers or a trend are being discussed and a dataset is available.",
    "flow": "A causal chain, process, or mechanism is being described.",
    "timeline": "Events are ordered in time.",
    "map": "Places or spatial relationships matter.",
    "evidence": "A claim is being supported by a source or quote.",
    "media": "A concrete visual or image would help.",
    "comparison": "Two or more options are being contrasted side by side.",
    "metric": "One key number is the point.",
    "visual": "A single hero visual or definition card suffices.",
}
URGENCY_LEVELS = [
    "ignore: nothing to prepare",
    "backstage: prepare quietly, do not show",
    "likely-needed: the audience will probably need this soon",
    "immediate: the speaker is relying on it right now",
]


class System1Error(RuntimeError):
    pass


@dataclass(frozen=True)
class Answer:
    type: str                      # noul | choice | score
    value: Any                     # float (noul/score) or str (choice)
    confidence: float              # choice/score confidence; |2p-1| for noul
    probabilities: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class System1Response:
    backend: str
    model: str
    answers: Dict[str, Answer]
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0


class System1Backend(Protocol):
    name: str
    async def ask(self, state: Any, questions: Mapping[str, Mapping[str, Any]]) -> System1Response: ...


def parse_answers(raw: Mapping[str, Mapping[str, Any]]) -> Dict[str, Answer]:
    try:
        out = _parse_answers(raw)
        for a in out.values():
            if not math.isfinite(a.confidence) or not 0 <= a.confidence <= 1:
                raise ValueError("confidence outside 0..1")
            if a.type in {"noul", "score"} and not math.isfinite(a.value):
                raise ValueError("non-finite answer")
            if a.type == "noul" and not 0 <= a.value <= 1:
                raise ValueError("noul outside 0..1")
            if any(not math.isfinite(p) or not 0 <= p <= 1 for p in a.probabilities.values()):
                raise ValueError("probability outside 0..1")
        return out
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as e:
        raise System1Error(f"invalid backend answers: {e}") from None


def _parse_answers(raw: Mapping[str, Mapping[str, Any]]) -> Dict[str, Answer]:
    out: Dict[str, Answer] = {}
    for name, a in raw.items():
        kind = a.get("type")
        if kind == "noul":
            p = float(a["noul"])
            out[name] = Answer("noul", p, round(abs(2 * p - 1), 4), {"true": p, "false": 1 - p})
        elif kind == "choice":
            out[name] = Answer("choice", str(a["choice"]), float(a["confidence"]),
                               {k: float(v) for k, v in a["probabilities"].items()})
        elif kind == "score":
            out[name] = Answer("score", float(a["score"]), float(a["confidence"]),
                               {k: float(v) for k, v in a["probabilities"].items()})
        else:
            raise System1Error(f"unknown answer type for {name!r}: {kind!r}")
    return out


class JevBackend:
    """Real TypeSafe client.  stdlib only; blocking I/O runs in a worker thread."""
    name = "jev"

    def __init__(self, api_key: Optional[str] = None, *, model: str = DEFAULT_MODEL,
                 base_url: str = JEV_BASE_URL, timeout_s: float = 2.0):
        self.api_key = api_key or os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise System1Error("no Jev API key: set JEV_API_KEY (or TYPESAFE_API_KEY)")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        self.model, self.base_url, self.timeout_s = model, base_url.rstrip("/"), timeout_s

    def _call(self, method: str, path: str, body: Optional[dict]) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if body is not None and body.get("assets"):
            # Images are an experimental TypeSafe feature; it requires an explicit opt-in header.
            headers["TypeSafe-Danger-Zone-Images"] = "true"
        req = urllib.request.Request(
            self.base_url + path, method=method,
            data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                data = json.loads(r.read(1_000_001))
                if not isinstance(data, dict):
                    raise System1Error("jev returned non-object JSON")
                return data
        except urllib.error.HTTPError as e:
            # Response bodies can echo request data; never put them in artifacts.
            raise System1Error(f"jev http {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise System1Error(f"jev unreachable: {e}") from None

    async def models(self) -> List[dict]:
        return (await asyncio.to_thread(self._call, "GET", "/v1/models", None)).get("models", [])

    async def ask(self, state, questions, assets: Optional[Mapping[str, Mapping[str, str]]] = None) -> System1Response:
        t0 = time.perf_counter()
        body = {"state": state, "model": self.model, "questions": dict(questions)}
        if assets:
            body["assets"] = dict(assets)
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(self._call, "POST", "/v1/systemone", body), self.timeout_s)
        except TimeoutError:
            raise System1Error("jev request deadline exceeded") from None
        ms = (time.perf_counter() - t0) * 1000
        try:
            usage = raw.get("usage") or {}
            answers = parse_answers(raw["answers"])
            for name, q in questions.items():
                if name not in answers or answers[name].type != q["type"]:
                    raise System1Error(f"missing or mismatched answer: {name}")
                a = answers[name]
                if a.type == "choice" and a.value not in q["criteria"]:
                    raise System1Error(f"unknown choice for {name}")
                if a.type == "score" and not 0 <= a.value <= len(q["criteria"]) - 1:
                    raise System1Error(f"score outside rubric for {name}")
            return System1Response(self.name, raw.get("model", self.model), answers, ms,
                                   int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise System1Error(f"invalid Jev response: {type(e).__name__}") from None


class MockBackend:
    """Deterministic backend for tests/offline runs.  `script` maps question name -> raw answer dict."""
    name = "mock"

    def __init__(self, script: Optional[Mapping[str, Mapping[str, Any]]] = None, *, fail: bool = False, delay_s: float = 0.0):
        self.script, self.fail, self.delay_s, self.calls = dict(script or {}), fail, delay_s, []

    async def ask(self, state, questions) -> System1Response:
        self.calls.append((state, dict(questions)))
        if self.delay_s: await asyncio.sleep(self.delay_s)
        if self.fail: raise System1Error("mock failure")
        raw = {}
        for name, q in questions.items():
            if name in self.script:
                raw[name] = self.script[name]
            elif q["type"] == "noul":
                raw[name] = {"type": "noul", "noul": .5}
            elif q["type"] == "choice":
                keys = list(q["criteria"]); raw[name] = {"type": "choice", "choice": keys[0], "confidence": 1 / len(keys),
                                                         "probabilities": {k: 1 / len(keys) for k in keys}}
            else:
                n = len(q["criteria"]); raw[name] = {"type": "score", "score": 0.0, "confidence": 1 / n,
                                                     "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                                                     "probabilities": {str(i): 1 / n for i in range(n)}}
        return System1Response(self.name, "mock", parse_answers(raw), self.delay_s * 1000)


@dataclass(frozen=True)
class Assessment:
    """One batched System-1 reading of the live moment.  Advisory only."""
    source: str                          # jev | mock | count_table | none
    act: Optional[str]
    act_confidence: float
    topic_shift: Optional[float]         # P(speaker moved to a different topic)
    representation: Optional[str]
    representation_confidence: float
    warm_now: Optional[float]            # P(worth preparing backstage)
    urgency: Optional[float]             # expected level 0..3
    abstain: bool
    reasons: List[str]
    latency_ms: float
    error: Optional[str] = None
    authority: str = "advisory_only"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_questions(context: Mapping[str, Any], *, acts: Mapping[str, str] = DEFAULT_ACTS) -> Dict[str, Dict[str, Any]]:
    reps = {r: REPRESENTATION_HINTS[r] for r in REPRESENTATIONS if representation_available(r, context)}
    return {
        "discourse_act": {"type": "choice", "instructions": "What is the speaker doing in the latest utterance?",
                          "criteria": dict(acts)},
        "topic_shift": {"type": "noul",
                        "instructions": "Has the speaker moved to a different topic than current_topic?",
                        "criteria": {"true": "The latest utterance is about a different subject than current_topic.",
                                     "false": "It continues, elaborates, or illustrates current_topic."}},
        "representation_family": {"type": "choice",
                                  "instructions": "Which visual representation would best support the latest utterance?",
                                  "criteria": reps},
        "warm_now": {"type": "noul",
                     "instructions": "Is it worth preparing a visual backstage for what the speaker is likely to need next?"},
        "intervention_urgency": {"type": "score",
                                 "instructions": "How soon does the audience need a visual change?",
                                 "criteria": URGENCY_LEVELS},
    }


class System1Assessor:
    """Batches the five fast decisions into one call, with fallback and telemetry."""

    def __init__(self, backend: System1Backend, *, fallback: Optional[OracleRepresentationPolicy] = None,
                 min_choice_confidence: float = .55, min_noul_confidence: float = .30, window_chars: int = 1200):
        self.backend, self.fallback = backend, fallback
        self.min_choice_confidence, self.min_noul_confidence = min_choice_confidence, min_noul_confidence
        self.window_chars = window_chars
        self.history: List[Dict[str, Any]] = []
        self.models: set[str] = set()
        self.input_tokens = self.output_tokens = 0

    def _state(self, transcript: str, current_topic: str, topics: Sequence[str], context: Mapping[str, Any], recent_context: str = "") -> Dict[str, Any]:
        return {"latest_utterance": transcript[-self.window_chars:], "current_topic": current_topic,
                "recent_context": recent_context[-self.window_chars:],
                "known_topics": list(topics)[:40], "available_assets": {k: bool(v) for k, v in context.items()}}

    async def assess(self, transcript: str, *, current_topic: str = "", topics: Sequence[str] = (),
                     context: Optional[Mapping[str, Any]] = None, recent_context: str = "") -> Assessment:
        ctx = dict(context or {})
        questions = build_questions(ctx)
        reasons: List[str] = []
        t0 = time.perf_counter()
        try:
            r = await self.backend.ask(self._state(transcript, current_topic, topics, ctx, recent_context), questions)
        except System1Error as e:
            a = self._fallback(ctx, str(e))
            a = Assessment(**{**a.to_dict(), "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
            self._record(a, None)
            return a
        ans = r.answers
        self.models.add(r.model)
        self.input_tokens += r.input_tokens
        self.output_tokens += r.output_tokens
        act, rep, shift, warm, urg = (ans.get(k) for k in
                                      ("discourse_act", "representation_family", "topic_shift", "warm_now", "intervention_urgency"))
        abstain = not act or not rep
        if not act or not rep:
            reasons.append("missing discourse act or representation")
        if act and act.value not in DEFAULT_ACTS:
            abstain = True; reasons.append("unknown discourse act")
        if act and act.confidence < self.min_choice_confidence:
            abstain = True; reasons.append(f"act confidence {act.confidence:.2f} < {self.min_choice_confidence:.2f}")
        if rep and rep.confidence < self.min_choice_confidence:
            abstain = True; reasons.append(f"representation confidence {rep.confidence:.2f} < {self.min_choice_confidence:.2f}")
        if rep and not representation_available(rep.value, ctx):   # model picked something we can't render
            abstain = True; reasons.append(f"{rep.value} unavailable in context")
        a = Assessment(source=r.backend, act=act.value if act else None, act_confidence=act.confidence if act else 0.0,
                       topic_shift=shift.value if shift else None,
                       representation=rep.value if rep else None, representation_confidence=rep.confidence if rep else 0.0,
                       warm_now=warm.value if warm else None, urgency=urg.value if urg else None,
                       abstain=abstain, reasons=reasons or ["system-1 assessment"], latency_ms=round(r.latency_ms, 1))
        self._record(a, ctx)
        return a

    def _fallback(self, ctx: Mapping[str, Any], error: str) -> Assessment:
        if self.fallback is None:
            return Assessment("none", None, 0.0, None, None, 0.0, None, None, True,
                              ["backend failed; no fallback policy"], 0.0, error)
        p = self.fallback.predict("explain", ctx)
        return Assessment("count_table", None, 0.0, None, p.representation, p.confidence, None, None,
                          True, ["backend failed; count-table representation only, act unknown"] + p.reason.split("; "),
                          0.0, error)

    def _record(self, a: Assessment, ctx: Optional[Mapping[str, Any]]) -> None:
        row = {"source": a.source, "latency_ms": a.latency_ms, "abstain": a.abstain, "error": a.error,
               "representation": a.representation, "act": a.act, "table_representation": None}
        if self.fallback is not None and ctx is not None and a.act:
            row["table_representation"] = self.fallback.predict(a.act, ctx).representation
        self.history.append(row)

    def summary(self) -> Dict[str, Any]:
        ok = [h for h in self.history if h["source"] not in ("count_table", "none")]
        lat = sorted(h["latency_ms"] for h in ok)
        both = [h for h in ok if h["table_representation"] and h["representation"]]
        pct = lambda q: round(lat[min(len(lat) - 1, int(q * len(lat)))], 1) if lat else None
        return {"calls": len(self.history), "backend_failures": len(self.history) - len(ok),
                "models": sorted(self.models), "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "abstain_rate": round(sum(h["abstain"] for h in ok) / len(ok), 3) if ok else None,
                "latency_ms_p50": pct(.5), "latency_ms_p95": pct(.95),
                "agreement_with_count_table": round(sum(h["representation"] == h["table_representation"] for h in both) / len(both), 3) if both else None}
