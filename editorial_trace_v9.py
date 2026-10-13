#!/usr/bin/env python3
"""Normalized editorial traces for Live Presenter v9.

This module is intentionally small and dependency-free.  It provides adapters for
common *offline editor* output shapes so those editors can be treated as oracle
producers without becoming dependencies of the live runtime.

Schemas are clean-room normalized from publicly documented/open-source patterns:
- Video Alchemy style: {time, duration, src}
- AutoBroll style: {start, end, kind, placement, query, reason, source, altQueries}
- generic CSV/JSON human/editor traces.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
import csv
import json
import re


def _f(v: Any, default: float = 0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return float(default)


def _clean(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def normalize_representation(kind: str, query: str = "") -> str:
    s=(kind+" "+query).lower()
    if any(x in s for x in ("chart","graph","plot","bar","line")): return "chart"
    if any(x in s for x in ("diagram","flow","process","mechanism")): return "flow"
    if any(x in s for x in ("timeline","chronology")): return "timeline"
    if any(x in s for x in ("map","location","geograph")): return "map"
    if any(x in s for x in ("quote","citation","source","paper","evidence")): return "evidence"
    if any(x in s for x in ("image","photo","b-roll","broll","video","footage")): return "media"
    if any(x in s for x in ("compare","versus","split")): return "comparison"
    if any(x in s for x in ("number","metric","stat")): return "metric"
    return "visual"


def normalize_function(reason: str, query: str = "", representation: str = "") -> str:
    s=(reason+" "+query+" "+representation).lower()
    if any(x in s for x in ("example","illustrat","show what","concrete")): return "exemplify"
    if any(x in s for x in ("define","definition","meaning","introduce")): return "define"
    if any(x in s for x in ("why","mechanism","cause","process","explain")): return "explain"
    if any(x in s for x in ("compare","contrast","versus","difference")): return "compare"
    if any(x in s for x in ("evidence","source","support","prove","citation")): return "substantiate"
    if any(x in s for x in ("trend","number","quant","chart","plot","metric")): return "quantify"
    if any(x in s for x in ("summary","takeaway","emphasis","focus")): return "focus"
    return "augment"


@dataclass(frozen=True)
class EditorialEvent:
    start_s: float
    end_s: float
    function: str
    representation: str
    placement: str = "overlay"
    query: str = ""
    rationale: str = ""
    source_text: str = ""
    alternatives: List[str] = field(default_factory=list)
    asset_uri: Optional[str] = None
    provenance: Optional[str] = None
    editor: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s-self.start_s)

    @property
    def midpoint_s(self) -> float:
        return self.start_s + self.duration_s/2

    def to_dict(self) -> Dict[str, Any]:
        d=asdict(self); d["duration_s"]=self.duration_s; return d


def from_video_alchemy(rows: Iterable[Dict[str,Any]], *, editor="video-alchemy") -> List[EditorialEvent]:
    out=[]
    for r in rows:
        start=_f(r.get("time",r.get("start",0)))
        duration=max(0.0,_f(r.get("duration",r.get("duration_s",0))))
        src=_clean(r.get("src") or r.get("asset") or r.get("url"))
        q=_clean(r.get("query") or r.get("label") or Path(src).stem if src else "")
        rep=normalize_representation(_clean(r.get("kind") or "broll"),q)
        out.append(EditorialEvent(start,start+duration,normalize_function("",q,rep),rep,
            placement=_clean(r.get("placement") or "overlay"),query=q,asset_uri=src or None,
            provenance=_clean(r.get("provenance") or r.get("source")) or None,editor=editor,
            confidence=(None if r.get("confidence") is None else _f(r.get("confidence"))),metadata={"upstream_shape":"video_alchemy"}))
    return sorted(out,key=lambda x:(x.start_s,x.end_s))


def from_autobroll(rows: Iterable[Dict[str,Any]], *, editor="autobroll") -> List[EditorialEvent]:
    out=[]
    for r in rows:
        start=_f(r.get("start",r.get("time",0)))
        end=_f(r.get("end"), start+_f(r.get("durationTarget",r.get("duration",0))))
        if end < start: end=start
        query=_clean(r.get("query"))
        reason=_clean(r.get("reason") or r.get("rationale"))
        kind=_clean(r.get("kind") or "media")
        rep=normalize_representation(kind,query)
        alt=r.get("altQueries") or r.get("alternatives") or []
        if isinstance(alt,str): alt=[alt]
        src=r.get("source")
        source_text=_clean(src.get("text") if isinstance(src,dict) else src)
        out.append(EditorialEvent(start,end,normalize_function(reason,query,rep),rep,
            placement=_clean(r.get("placement") or "overlay"),query=query,rationale=reason,
            source_text=source_text,alternatives=[_clean(x) for x in alt if _clean(x)],
            asset_uri=_clean(r.get("url") or r.get("src")) or None,
            provenance=_clean(r.get("provenance")) or None,editor=editor,
            confidence=(None if r.get("confidence") is None else _f(r.get("confidence"))),metadata={"upstream_shape":"autobroll"}))
    return sorted(out,key=lambda x:(x.start_s,x.end_s))


def from_generic(rows: Iterable[Dict[str,Any]], *, editor="generic") -> List[EditorialEvent]:
    out=[]
    for r in rows:
        start=_f(r.get("start_s",r.get("start",r.get("time",0))))
        end=_f(r.get("end_s",r.get("end",start+_f(r.get("duration_s",r.get("duration",0))))))
        query=_clean(r.get("query")); reason=_clean(r.get("rationale") or r.get("reason"))
        rep=_clean(r.get("representation")) or normalize_representation(_clean(r.get("kind")),query)
        function=_clean(r.get("function")) or normalize_function(reason,query,rep)
        alts=r.get("alternatives") or []; alts=[alts] if isinstance(alts,str) else list(alts)
        out.append(EditorialEvent(start,max(start,end),function,rep,_clean(r.get("placement") or "overlay"),query,reason,
            _clean(r.get("source_text") or r.get("transcript")),[_clean(x) for x in alts if _clean(x)],
            _clean(r.get("asset_uri") or r.get("url") or r.get("src")) or None,
            _clean(r.get("provenance") or r.get("source")) or None,_clean(r.get("editor") or editor) or editor,
            None if r.get("confidence") in (None,"") else _f(r.get("confidence")),dict(r.get("metadata") or {})))
    return sorted(out,key=lambda x:(x.start_s,x.end_s))


def load_trace(path: Path, *, shape="generic", editor=None) -> List[EditorialEvent]:
    path=Path(path)
    if path.suffix.lower()==".csv":
        with path.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
    else:
        raw=json.loads(path.read_text(encoding="utf-8")); rows=raw if isinstance(raw,list) else raw.get("events",raw.get("broll",[]))
    if shape=="video_alchemy": return from_video_alchemy(rows,editor=editor or "video-alchemy")
    if shape=="autobroll": return from_autobroll(rows,editor=editor or "autobroll")
    return from_generic(rows,editor=editor or "generic")


def dump_trace(events: Sequence[EditorialEvent], path: Path) -> None:
    Path(path).write_text(json.dumps([x.to_dict() for x in events],indent=2,ensure_ascii=False),encoding="utf-8")

_KIND_TO_FUNCTION={
    "definition":"define","flow":"explain","concept_map":"relate","comparison":"compare",
    "evidence":"substantiate","source_card":"substantiate","chart":"quantify","line_chart":"quantify","bar_chart":"quantify",
    "image_grid":"exemplify","metric":"quantify","timeline":"relate","hero":"focus","quote":"substantiate","map":"relate",
}

def from_live_snapshot(snapshot: Dict[str,Any], *, editor="live-presenter", default_step_s:float=1.0) -> List[EditorialEvent]:
    """Convert a runtime snapshot's representation/stage history into oracle-comparable events.

    Uses real `at_ms` timestamps when representation history has them; otherwise
    falls back to deterministic ordinal timing so old fixtures remain comparable.
    """
    hist=list((snapshot.get("representation") or {}).get("history") or [])
    if not hist:return []
    base=min((int(x.get("at_ms")) for x in hist if x.get("at_ms") is not None),default=0)
    out=[]
    for i,x in enumerate(hist):
        start=((int(x.get("at_ms"))-base)/1000.0 if base and x.get("at_ms") is not None else i*default_step_s)
        kind=_clean(x.get("kind") or "visual"); act=_clean(x.get("act")) or _KIND_TO_FUNCTION.get(kind,"augment")
        out.append(EditorialEvent(start,start+default_step_s,act,kind,placement="stage",query="",rationale=_clean(x.get("source")),editor=editor,
            provenance=_clean(x.get("grounding")) or None,metadata={"revision":x.get("revision"),"node":x.get("node")}))
    return out
