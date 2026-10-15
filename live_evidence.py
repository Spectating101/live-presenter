#!/usr/bin/env python3
"""Session-scoped external evidence for v8.

External/web facts never silently become corpus facts. They remain separate,
carry freshness/confidence, and can be attached to an existing claim or tangent.
"""
from __future__ import annotations
import hashlib, time
from dataclasses import dataclass, asdict
from typing import Dict, List

@dataclass
class LiveEvidence:
    id:str; claim_id:str; text:str; source:str; confidence:float
    status:str='external_unverified'; fetched_at_ms:int=0; label:str='LIVE'
    def to_dict(self):return asdict(self)

class LiveEvidenceStore:
    def __init__(self):self.records:Dict[str,LiveEvidence]={};self.by_claim:Dict[str,List[str]]={}
    def ingest(self,claim_id:str,text:str,source:str,*,confidence:float=.5,status='external_unverified',label='LIVE'):
        key=hashlib.sha1((claim_id+'|'+source+'|'+text).encode()).hexdigest()[:12]
        eid='live:'+key
        rec=LiveEvidence(eid,claim_id,str(text)[:900],str(source)[:300],max(0,min(1,float(confidence))),status,int(time.time()*1000),label)
        self.records[eid]=rec; self.by_claim.setdefault(claim_id,[])
        if eid not in self.by_claim[claim_id]:self.by_claim[claim_id].append(eid)
        return rec
    def for_claim(self,claim_id:str,k=4):return [self.records[x] for x in self.by_claim.get(claim_id,[])[:k] if x in self.records]
    def scene_items(self,claim_id:str,k=4):
        return [{'title':f'{x.label} · {x.status.replace("_"," ")}', 'text':x.text, 'source':x.source, '_live_evidence_id':x.id,
                 'confidence':x.confidence} for x in self.for_claim(claim_id,k)]
    def snapshot(self):return {'count':len(self.records),'records':[self.records[k].to_dict() for k in sorted(self.records)]}
