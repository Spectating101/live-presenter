#!/usr/bin/env python3
"""Small audience-state accumulator for future adaptive presentation policies.

No camera inference is bundled here.  The runtime accepts normalized signals so
real gaze/posture/question estimators can be plugged in later without coupling
that sensing stack to presentation logic.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class AudienceState:
    confusion: float = 0.0
    engagement: float = 0.5
    familiarity: float = 0.5
    last_question: Optional[str] = None
    revision: int = 0

    def update(self, *, confusion=None, engagement=None, familiarity=None, question=None):
        def blend(old, new):
            if new is None: return old
            new=max(0.0,min(1.0,float(new)))
            return round(old*.25 + new*.75, 4)
        self.confusion=blend(self.confusion, confusion)
        self.engagement=blend(self.engagement, engagement)
        self.familiarity=blend(self.familiarity, familiarity)
        if question: self.last_question=str(question).strip()[:400]
        self.revision += 1
        return asdict(self)

    @property
    def preferred_depth(self):
        if self.confusion >= .68: return 'explain'
        if self.familiarity <= .28: return 'define'
        if self.engagement <= .25: return 'focus'
        return 'normal'
