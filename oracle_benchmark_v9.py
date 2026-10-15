#!/usr/bin/env python3
"""Offline-editor oracle benchmark for causal Live Presenter traces."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import List,Dict,Any,Sequence,Optional
import statistics
from editorial_trace_v9 import EditorialEvent

@dataclass
class Match:
    oracle_editor:str
    oracle_start_s:float
    live_start_s:Optional[float]
    lag_s:Optional[float]
    function_match:bool=False
    representation_match:bool=False
    matched:bool=False
    causal_available:Optional[bool]=None
    prefetched:Optional[bool]=None
    oracle_function:str=""
    live_function:str=""
    oracle_representation:str=""
    live_representation:str=""


def _overlap(a:EditorialEvent,b:EditorialEvent,tol:float)->bool:
    return not (a.end_s+tol < b.start_s or b.end_s+tol < a.start_s) or abs(a.start_s-b.start_s)<=tol


def match_trace(oracle:Sequence[EditorialEvent], live:Sequence[EditorialEvent], *, tolerance_s:float=2.0) -> List[Match]:
    unused=set(range(len(live))); out=[]
    for o in oracle:
        best=None; best_cost=10**9
        for i in unused:
            l=live[i]
            if not _overlap(o,l,tolerance_s):continue
            semantic_pen=(0 if o.function==l.function else .7)+(0 if o.representation==l.representation else .5)
            cost=abs(l.start_s-o.start_s)+semantic_pen
            if cost<best_cost:best_cost=cost;best=i
        if best is None:
            out.append(Match(o.editor or "oracle",o.start_s,None,None,oracle_function=o.function,oracle_representation=o.representation))
            continue
        unused.remove(best); l=live[best]
        out.append(Match(o.editor or "oracle",o.start_s,l.start_s,l.start_s-o.start_s,o.function==l.function,o.representation==l.representation,True,
            causal_available=l.metadata.get("causal_available") if l.metadata else None,
            prefetched=l.metadata.get("prefetched") if l.metadata else None,
            oracle_function=o.function,live_function=l.function,oracle_representation=o.representation,live_representation=l.representation))
    return out


def metrics(oracle:Sequence[EditorialEvent], live:Sequence[EditorialEvent], *, tolerance_s:float=2.0) -> Dict[str,Any]:
    ms=match_trace(oracle,live,tolerance_s=tolerance_s); matched=[m for m in ms if m.matched]
    live_match=0
    for l in live:
        if any(_overlap(o,l,tolerance_s) for o in oracle):live_match+=1
    lags=[m.lag_s for m in matched if m.lag_s is not None]
    recall=(len(matched)/len(oracle) if oracle else 1.0)
    func=(sum(m.function_match for m in matched)/len(matched) if matched else 0.0)
    rep=(sum(m.representation_match for m in matched)/len(matched) if matched else 0.0)
    med_abs=(statistics.median(abs(x) for x in lags) if lags else None)
    timing=(max(0.0,1.0-(med_abs/max(.001,tolerance_s))) if med_abs is not None else 0.0)
    return {
        "oracle_events":len(oracle),"live_events":len(live),"matched":len(matched),
        "recall":round(recall,4),
        "precision":round(live_match/len(live),4) if live else 1.0,
        "function_agreement":round(func,4),
        "representation_agreement":round(rep,4),
        "median_lag_s":round(statistics.median(lags),4) if lags else None,
        "median_abs_lag_s":round(med_abs,4) if med_abs is not None else None,
        "p95_abs_lag_s":round(sorted(abs(x) for x in lags)[max(0,int(.95*len(lags))-1)],4) if lags else None,
        "timing_quality":round(timing,4),
        "prefetch_hit_rate":round(sum(bool(m.prefetched) for m in matched if m.prefetched is not None)/sum(m.prefetched is not None for m in matched),4) if any(m.prefetched is not None for m in matched) else None,
        "causal_availability_rate":round(sum(bool(m.causal_available) for m in matched if m.causal_available is not None)/sum(m.causal_available is not None for m in matched),4) if any(m.causal_available is not None for m in matched) else None,
        "oracle_gap":round(1-(.35*recall+.25*func+.20*rep+.20*timing),4),
        "matches":[asdict(m) for m in ms],
    }


def consensus_trace(traces:Sequence[Sequence[EditorialEvent]], *, tolerance_s:float=2.0, min_votes:Optional[int]=None) -> List[EditorialEvent]:
    """Build a simple temporal/semantic consensus across human/offline-AI editors."""
    all_events=[]
    for ti,tr in enumerate(traces):
        for e in tr:all_events.append((ti,e))
    all_events.sort(key=lambda x:x[1].start_s)
    used=set(); out=[]; min_votes=min_votes or max(1,(len(traces)+1)//2)
    for idx,(ti,e) in enumerate(all_events):
        if idx in used:continue
        cluster=[(idx,ti,e)]; editors={ti}
        for j,(tj,x) in enumerate(all_events[idx+1:],start=idx+1):
            if j in used or tj in editors:continue
            if abs(x.start_s-e.start_s)<=tolerance_s and (x.function==e.function or x.representation==e.representation):
                cluster.append((j,tj,x));editors.add(tj)
        if len(editors)<min_votes:continue
        for j,_,_ in cluster:used.add(j)
        ev=[x for _,_,x in cluster]
        funcs={v:sum(x.function==v for x in ev) for v in {x.function for x in ev}}
        reps={v:sum(x.representation==v for x in ev) for v in {x.representation for x in ev}}
        function=max(funcs,key=lambda k:(funcs[k],k)); representation=max(reps,key=lambda k:(reps[k],k))
        start=statistics.median(x.start_s for x in ev); end=statistics.median(x.end_s for x in ev)
        out.append(EditorialEvent(start,end,function,representation,placement=max((x.placement for x in ev),key=lambda p:sum(y.placement==p for y in ev)),
            query=next((x.query for x in ev if x.query),""),rationale="editor consensus",source_text=next((x.source_text for x in ev if x.source_text),""),
            alternatives=[],asset_uri=None,provenance="multi-editor consensus",editor="consensus",confidence=len(editors)/max(1,len(traces)),
            metadata={"votes":len(editors),"editors":sorted({x.editor or str(t) for _,t,x in cluster})}))
    return sorted(out,key=lambda x:x.start_s)


def warm_waste(prefetch_events:Sequence[EditorialEvent], live_events:Sequence[EditorialEvent], *, tolerance_s=4.0)->Dict[str,Any]:
    used=0
    for p in prefetch_events:
        if any(abs(l.start_s-p.start_s)<=tolerance_s and (l.function==p.function or l.representation==p.representation) for l in live_events):used+=1
    return {"prefetched":len(prefetch_events),"used":used,"wasted":len(prefetch_events)-used,
        "waste_rate":round((len(prefetch_events)-used)/len(prefetch_events),4) if prefetch_events else 0.0}
