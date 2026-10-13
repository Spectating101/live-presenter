#!/usr/bin/env python3
"""Claim/evidence ledger for Live Presenter v7.

The stage should know which proposition a visible object represents and what
loaded evidence supports it. This module deliberately distinguishes grounding
from truth: a claim can be well-grounded in the presentation corpus without
being independently verified by the runtime.
"""
from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def _hash(s: str, n: int = 12) -> str:
    return hashlib.sha1(_norm(s).lower().encode("utf-8")).hexdigest()[:n]


def _sentences(text: str) -> List[str]:
    out=[]
    for s in re.split(r"(?<=[.!?])\s+", _norm(text)):
        s=s.strip()
        if 5 <= len(s.split()) <= 55:
            out.append(s)
    return out


@dataclass
class EvidenceRecord:
    id: str
    source: str
    chunk_id: str
    text: str
    retrieval_score: float

    def to_dict(self):
        return asdict(self)


@dataclass
class ClaimRecord:
    id: str
    concept_id: str
    text: str
    primary: bool = False
    evidence_ids: List[str] = field(default_factory=list)
    corpus_support: float = 0.0
    status: str = "presentation_assertion"

    def to_dict(self):
        return asdict(self)


class ClaimLedger:
    """Stable claims + loaded evidence for a presentation corpus."""

    def __init__(self, presentation, memory):
        self.presentation = presentation
        self.memory = memory
        self.claims: Dict[str, ClaimRecord] = {}
        self.evidence: Dict[str, EvidenceRecord] = {}
        self.by_concept: Dict[str, List[str]] = {}
        self._compile()

    @staticmethod
    def _status(score: float, has_evidence: bool) -> str:
        if not has_evidence:
            return "presentation_assertion"
        if score >= .18:
            return "corpus_supported"
        if score >= .07:
            return "corpus_partial"
        return "presentation_assertion"

    def _compile(self):
        for cid, node in self.presentation.nodes.items():
            ss=_sentences(node.semantic_text) or [_norm(node.semantic_text)]
            self.by_concept[cid]=[]
            for i, text in enumerate(ss[:4]):
                claim_id=f"claim:{cid}:{_hash(text)}"
                hits=self.memory.retrieve(text,k=4)
                evidence_ids=[]
                top=0.0
                for h in hits:
                    score=float(getattr(h,"score",0.0) or 0.0)
                    if score < .035:
                        continue
                    source=str(getattr(h,"source","") or "")
                    chunk=str(getattr(h,"chunk_id","") or "")
                    raw=str(getattr(h,"text","") or "")
                    eid=f"ev:{_hash(source+'|'+chunk)}"
                    if eid not in self.evidence:
                        self.evidence[eid]=EvidenceRecord(eid,source,chunk,raw,round(score,4))
                    evidence_ids.append(eid); top=max(top,score)
                rec=ClaimRecord(
                    id=claim_id, concept_id=cid, text=text, primary=(i==0),
                    evidence_ids=evidence_ids, corpus_support=round(top,4),
                    status=self._status(top,bool(evidence_ids)),
                )
                self.claims[claim_id]=rec
                self.by_concept[cid].append(claim_id)

    def claims_for(self, concept_id: str) -> List[ClaimRecord]:
        return [self.claims[x] for x in self.by_concept.get(concept_id,[]) if x in self.claims]

    def primary_claim(self, concept_id: str) -> Optional[ClaimRecord]:
        xs=self.claims_for(concept_id)
        return next((x for x in xs if x.primary), xs[0] if xs else None)

    def evidence_for_claim(self, claim_id: str, k: int = 4) -> List[EvidenceRecord]:
        c=self.claims.get(claim_id)
        if not c: return []
        return [self.evidence[e] for e in c.evidence_ids[:k] if e in self.evidence]

    def evidence_scene(self, concept_id: str) -> Optional[Dict[str,Any]]:
        claim=self.primary_claim(concept_id)
        if not claim: return None
        ev=self.evidence_for_claim(claim.id,6)
        if not ev: return None
        return {
            "kind":"evidence",
            "kicker":self.presentation.nodes[concept_id].title,
            "headline":"What supports this claim?",
            "items":[{"title":x.chunk_id,"text":x.text.split("\n")[0][:220],"source":x.source,"_evidence_id":x.id} for x in ev],
            "sources":list(dict.fromkeys(x.source for x in ev)),
            "grounding":"corpus",
            "epistemic":claim.status,
            "_claim_ids":[claim.id],
        }

    def bind_scene(self, scene: Dict[str,Any], concept_id: str) -> Dict[str,Any]:
        """Attach stable claim/evidence metadata to an already object-bound scene."""
        s=copy.deepcopy(scene)
        claim_ids=list(s.get("_claim_ids",[]) or [])
        if not claim_ids:
            pc=self.primary_claim(concept_id)
            if pc: claim_ids=[pc.id]
        claims=[self.claims[c] for c in claim_ids if c in self.claims]
        source_refs=[]
        for c in claims:
            for e in self.evidence_for_claim(c.id):
                if e.source and e.source not in source_refs: source_refs.append(e.source)
        stage=s.setdefault("_stage",{})
        stage["claim_ids"]=claim_ids
        stage["epistemic"]={
            "status": (claims[0].status if claims else s.get("epistemic") or "unbound"),
            "corpus_support": (claims[0].corpus_support if claims else 0.0),
            "claim_count":len(claims),
        }
        for obj in stage.get("objects",[]) or []:
            if obj.get("role") in {"concept","statement","causal_step","data_series","comparison_target"}:
                obj["claim_ids"]=claim_ids
                obj["epistemic_status"]=stage["epistemic"]["status"]
                if source_refs:
                    obj["sources"]=list(dict.fromkeys((obj.get("sources") or [])+source_refs))
        for item in s.get("items",[]) or []:
            eid=item.get("_evidence_id")
            if eid and eid in self.evidence:
                item["_claim_ids"]=claim_ids
        stage["source_refs"]=list(dict.fromkeys((stage.get("source_refs") or [])+source_refs))
        s["sources"]=list(dict.fromkeys((s.get("sources") or [])+source_refs))
        return s

    def snapshot(self) -> Dict[str,Any]:
        counts={}
        for c in self.claims.values(): counts[c.status]=counts.get(c.status,0)+1
        return {
            "claim_count":len(self.claims),
            "evidence_count":len(self.evidence),
            "status_counts":counts,
            "claims":[self.claims[k].to_dict() for k in sorted(self.claims)],
        }
