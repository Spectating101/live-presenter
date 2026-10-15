#!/usr/bin/env python3
"""Argument coverage and audience-facing obligations for Live Presenter v7."""
from __future__ import annotations
from typing import Any, Dict, List, Set


class ArgumentCoverage:
    def __init__(self, ledger, presentation):
        self.ledger=ledger; self.presentation=presentation
        self.introduced:Set[str]=set()
        self.substantiated:Set[str]=set()
        self.source_inspected:Set[str]=set()
        self.history:List[Dict[str,Any]]=[]

    def observe(self, scene:Dict[str,Any], revision:int):
        st=scene.get("_stage") or {}
        claims=list(st.get("claim_ids") or [])
        kind=scene.get("kind")
        for cid in claims: self.introduced.add(cid)
        if kind=="evidence":
            for cid in claims: self.substantiated.add(cid)
        if scene.get("_source_overlay"):
            for cid in claims: self.source_inspected.add(cid)
        row={"revision":revision,"kind":kind,"claims":claims,"introduced":len(self.introduced),"substantiated":len(self.substantiated)}
        self.history.append(row)
        return row

    def concept_coverage(self, concept_id:str)->Dict[str,Any]:
        ids=[c.id for c in self.ledger.claims_for(concept_id)]
        if not ids:return {"concept_id":concept_id,"claims":0,"introduced":0,"substantiated":0,"coverage":1.0}
        intro=sum(1 for x in ids if x in self.introduced)
        subst=sum(1 for x in ids if x in self.substantiated)
        return {"concept_id":concept_id,"claims":len(ids),"introduced":intro,"substantiated":subst,"coverage":round(intro/len(ids),3)}

    def next_obligations(self,current:str,k:int=5)->List[Dict[str,Any]]:
        order=[]
        if current in self.presentation.nodes: order.append(current)
        if current in self.presentation.route:
            i=self.presentation.route.index(current)
            order += self.presentation.route[i+1:]
        else: order += self.presentation.route
        out=[]; seen=set()
        for concept in order:
            for claim in self.ledger.claims_for(concept):
                if claim.id in seen: continue
                seen.add(claim.id)
                if claim.id not in self.introduced:
                    state="introduce"
                elif claim.id not in self.substantiated and claim.evidence_ids:
                    state="substantiate"
                else:
                    continue
                out.append({"claim_id":claim.id,"concept_id":concept,"state":state,"text":claim.text,"support":claim.corpus_support})
                if len(out)>=k:return out
        return out

    def snapshot(self,current:str)->Dict[str,Any]:
        total=max(1,len(self.ledger.claims))
        return {
            "introduced":len(self.introduced),
            "substantiated":len(self.substantiated),
            "source_inspected":len(self.source_inspected),
            "introduction_coverage":round(len(self.introduced)/total,3),
            "current_concept":self.concept_coverage(current),
            "next_obligations":self.next_obligations(current),
            "history":self.history[-15:],
        }
