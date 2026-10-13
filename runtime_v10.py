#!/usr/bin/env python3
"""Live Presenter v10: oracle-distilled representation policy in shadow mode.

The learned policy may rank/warm representations, but it cannot bypass the
existing semantic broker, grounding ledger, visual grammar, or intervention
policy.  This is the deliberate first promotion stage for learned behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from runtime_v9 import RuntimeV9
from representation_policy_v10 import OracleRepresentationPolicy, representation_for_kind


class RuntimeV10(RuntimeV9):
    def __init__(self, *args, oracle_policy: Optional[OracleRepresentationPolicy | Path | str] = None,
                 oracle_shadow: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(oracle_policy, (str, Path)):
            oracle_policy = OracleRepresentationPolicy.load(oracle_policy)
        self.oracle_policy = oracle_policy
        self.oracle_shadow = bool(oracle_shadow)
        self.last_oracle_prediction = None
        self.oracle_history = []
        self.oracle_provider_warms = []
        self.oracle_disagreements = []

    def _oracle_context(self) -> Dict[str, bool]:
        has_dataset = False
        if getattr(self, "datasets", None):
            try: has_dataset = bool(self.datasets.for_topic(self.current))
            except Exception: has_dataset = False
        has_images = False
        try:
            has_images = (self._asset_scene() or {}).get("kind") == "image_grid"
        except Exception:
            pass
        has_sources = bool(getattr(self, "memory_hits", None))
        health = self.providers.health() if getattr(self, "providers", None) else {}
        graph_ready = any((v or {}).get("nodes", 0) for v in health.values() if isinstance(v, Mapping))
        return {
            "has_dataset": has_dataset,
            "has_images": has_images,
            "has_sources": has_sources,
            "graph_ready": graph_ready,
            "has_map_data": False,
            "has_timeline_data": False,
        }

    def _predict_oracle(self, beliefs):
        if not self.oracle_policy or not beliefs:
            self.last_oracle_prediction = None
            return None
        pred = self.oracle_policy.predict(beliefs[0].act, self._oracle_context())
        self.last_oracle_prediction = pred.to_dict()
        return pred

    def _broker_scene(self, text: str):
        scene, beliefs = super()._broker_scene(text)
        pred = self._predict_oracle(beliefs)
        if pred and scene and not pred.abstain:
            actual = representation_for_kind(scene.get("kind"))
            if actual and actual != pred.representation:
                self.last_oracle_prediction["disagrees_with_broker"] = True
                self.last_oracle_prediction["broker_representation"] = actual
                self.last_oracle_prediction["broker_kind"] = scene.get("kind")
        return scene, beliefs

    async def _shadow_warm_provider(self, text: str, beliefs) -> Optional[Dict[str, Any]]:
        pred = self._predict_oracle(beliefs)
        if not pred or pred.abstain or pred.confidence < .60:
            return None
        act = beliefs[0].act if beliefs else "continue"
        if act not in {"relate", "explain"}:
            return None
        ctx = {
            "current_concept": self.current,
            "current": self.current,
            "title": self.p.nodes[self.current].title,
            "oracle_representation": pred.representation,
            "oracle_confidence": pred.confidence,
        }
        result = await self.providers.prepare_best(ctx, act, min_support=.25, timeout=1.0)
        row = {
            "revision": self.revision, "node": self.current, "act": act,
            "recommendation": pred.to_dict(), "provider": result.provider,
            "provider_status": result.status, "provider_confidence": result.confidence,
        }
        if result.status == "ready" and result.scene:
            scene = self.visual_grammar.coerce(result.scene)
            errors = self.visual_grammar.validate(scene, claim_bearing=False)
            if not errors:
                self.representation_cache[(self.current, act)] = scene
                row["warmed_kind"] = scene.get("kind")
                row["status"] = "warmed"
            else:
                row["status"] = "withheld"
                row["errors"] = errors
        else:
            row["status"] = result.status
            row["reason"] = result.reason
        self.oracle_provider_warms.append(row)
        self.em.emit("oracle_policy.provider_warm", **row)
        return row

    async def preview(self, text: str, *, seq=None):
        state = await super().preview(text, seq=seq)
        if self.oracle_shadow and self.oracle_policy:
            beliefs = self.broker.beliefs(text)
            await self._shadow_warm_provider(text, beliefs)
            self.write()
        return self.snapshot()

    async def commit(self, text: str, *, seq=None):
        state = await super().commit(text, seq=seq)
        if not self.oracle_policy:
            return state
        beliefs = self.broker.beliefs(text)
        pred = self._predict_oracle(beliefs)
        if pred:
            row = {
                "revision": self.revision,
                "node": self.current,
                "act": beliefs[0].act if beliefs else None,
                "prediction": pred.to_dict(),
                "intervention": dict(self.last_intervention or {}),
                "actual_kind": (self.representation_scene or {}).get("kind") if self.representation_scene else None,
            }
            actual_rep = representation_for_kind(row["actual_kind"])
            row["actual_representation"] = actual_rep
            if actual_rep and not pred.abstain and actual_rep != pred.representation:
                disagreement = dict(row)
                disagreement["reason"] = "oracle recommendation differs from safe broker output; broker retained"
                self.oracle_disagreements.append(disagreement)
                self.em.emit("oracle_policy.disagreement", **disagreement)
            self.oracle_history.append(row)
            self.em.emit("oracle_policy.recommendation", **row)
            if self.oracle_shadow and (self.last_intervention or {}).get("action") != "SHOW":
                await self._shadow_warm_provider(text, beliefs)
            self.write()
        return self.snapshot()

    def snapshot(self):
        s = super().snapshot()
        s["v10"] = {
            "mode": "shadow" if self.oracle_shadow else "observe_only",
            "policy": None if not self.oracle_policy else self.oracle_policy.snapshot(),
            "last_prediction": self.last_oracle_prediction,
            "history": self.oracle_history[-12:],
            "provider_warms": self.oracle_provider_warms[-12:],
            "disagreements": self.oracle_disagreements[-12:],
            "authority": "advisory_only",
        }
        return s
