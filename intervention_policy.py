#!/usr/bin/env python3
"""Conservative mixed-initiative policy for audience-visible stage changes."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

SAFE_GROUNDING={
    'corpus','dataset','retrieved_assets','presentation_model','presentation_model+corpus',
    'synthesis+corpus','presentation_state','corpus+live_external'
}

@dataclass
class InterventionDecision:
    action:str
    confidence:float
    reason:str
    kind:Optional[str]=None
    grounding:Optional[str]=None

    def to_dict(self): return asdict(self)

class InterventionPolicy:
    """Make aggressive backstage preparation compatible with conservative stage use.

    SHOW: audience-visible now.
    WARM: keep ready backstage; not confident enough to change the stage.
    HOLD: no useful new representation signal.
    WITHHOLD: useful intent exists, but scene is unsafe/incomplete.
    """
    def __init__(self, *, show_threshold=.84, warm_threshold=.58):
        self.show_threshold=show_threshold; self.warm_threshold=warm_threshold

    def decide(self, scene:Optional[Dict[str,Any]], beliefs, *, broker_note=None, stage_locked=False):
        conf=float(beliefs[0].score) if beliefs else 0.0
        act=beliefs[0].act if beliefs else 'continue'
        if stage_locked:
            return InterventionDecision('WARM' if scene else 'HOLD',conf,'stage is explicitly held',scene.get('kind') if scene else None,scene.get('grounding') if scene else None)
        if act=='continue':
            return InterventionDecision('HOLD',conf,'no presentation-function change inferred')
        if scene is None:
            return InterventionDecision('WITHHOLD',conf,broker_note or 'representation is not ready or not grounded')
        grounding=scene.get('grounding')
        if grounding and grounding not in SAFE_GROUNDING:
            return InterventionDecision('WITHHOLD',conf,'scene grounding is not stage-safe',scene.get('kind'),grounding)
        if conf>=self.show_threshold:
            return InterventionDecision('SHOW',conf,'high-confidence presentation intent with bounded scene',scene.get('kind'),grounding)
        if conf>=self.warm_threshold:
            return InterventionDecision('WARM',conf,'plausible presentation intent; prepare without interrupting',scene.get('kind'),grounding)
        return InterventionDecision('HOLD',conf,'insufficient confidence for intervention',scene.get('kind'),grounding)
