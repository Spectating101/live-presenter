#!/usr/bin/env python3
"""Build leak-resistant oracle datasets from normalized offline-editor traces.

V10 treats external editors and human edits as *supervision producers*, not
runtime dependencies.  A bundle contains one talk, its timed transcript, and
one or more editor traces.  Events are normalized with v9 adapters, reconciled
into a transparent consensus, and split by talk_id so neighboring events from
the same talk never leak across train/eval.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import json
from urllib.parse import urlparse

from editorial_trace_v9 import EditorialEvent, from_autobroll, from_generic, from_video_alchemy
from oracle_benchmark_v9 import consensus_trace

SUPPORTED_SHAPES = {"generic", "autobroll", "video_alchemy"}


def _b(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_context(raw: Optional[Mapping[str, Any]]) -> Dict[str, bool]:
    raw = dict(raw or {})
    aliases = {
        "has_dataset": ("has_dataset", "dataset", "data_available"),
        "has_images": ("has_images", "images", "assets_available", "media_available"),
        "has_sources": ("has_sources", "sources", "evidence_available"),
        "graph_ready": ("graph_ready", "has_graph", "concept_graph"),
        "has_map_data": ("has_map_data", "map_data", "locations_available"),
        "has_timeline_data": ("has_timeline_data", "timeline_data", "dated_events_available"),
    }
    out = {}
    for canonical, names in aliases.items():
        out[canonical] = any(_b(raw.get(name)) for name in names if name in raw)
    return out


@dataclass(frozen=True)
class TranscriptSegment:
    start_s: float
    end_s: float
    text: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "TranscriptSegment":
        start = float(d.get("start_s", d.get("start", 0)) or 0)
        end = float(d.get("end_s", d.get("end", start)) or start)
        return cls(start, max(start, end), str(d.get("text") or "").strip())


@dataclass
class TraceBundle:
    talk_id: str
    transcript: List[TranscriptSegment]
    traces: List[List[EditorialEvent]]
    editor_names: List[str]
    context: Dict[str, bool] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OracleExample:
    example_id: str
    talk_id: str
    start_s: float
    end_s: float
    function: str
    representation: str
    confidence: float
    votes: int
    editor_count: int
    transcript_text: str
    context: Dict[str, bool]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _adapt_editor(editor: Mapping[str, Any]) -> Tuple[str, List[EditorialEvent]]:
    name = str(editor.get("name") or editor.get("editor") or "editor").strip()
    shape = str(editor.get("shape") or "generic").strip().lower()
    if shape not in SUPPORTED_SHAPES:
        raise ValueError(f"unsupported editor shape: {shape}")
    rows = editor.get("events") or editor.get("rows") or []
    if not isinstance(rows, list):
        raise ValueError(f"editor {name!r} events must be a list")
    if shape == "autobroll":
        trace = from_autobroll(rows, editor=name)
    elif shape == "video_alchemy":
        trace = from_video_alchemy(rows, editor=name)
    else:
        trace = from_generic(rows, editor=name)
    return name, trace


def load_bundle(path: Path | str) -> TraceBundle:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    talk_id = str(raw.get("talk_id") or path.stem).strip()
    if not talk_id:
        raise ValueError("talk_id is required")
    transcript = [TranscriptSegment.from_dict(x) for x in (raw.get("transcript") or [])]
    from eval_system1_v10 import validate_segments
    validate_segments([asdict(s) for s in transcript])
    metadata = dict(raw.get("metadata") or {})
    source = urlparse(str(metadata.get("source_uri") or ""))
    if source.hostname == "svs.gsfc.nasa.gov" and source.path.strip("/").isdigit():
        expected_group = "nasa_page_" + source.path.strip("/")
        if metadata.get("split_group") and metadata["split_group"] != expected_group:
            raise ValueError("NASA source group conflicts with source URI")
        metadata["split_group"] = expected_group
    names, traces = [], []
    for editor in raw.get("editors") or []:
        name, trace = _adapt_editor(editor)
        names.append(name)
        traces.append(trace)
    if not traces:
        raise ValueError(f"bundle {talk_id!r} has no editor traces")
    return TraceBundle(
        talk_id=talk_id,
        transcript=transcript,
        traces=traces,
        editor_names=names,
        context=_normalize_context(raw.get("context")),
        metadata=metadata,
    )


def transcript_for_event(segments: Sequence[TranscriptSegment], event: EditorialEvent, *, pad_s: float = 1.0) -> str:
    hits = []
    for seg in segments:
        if seg.end_s + pad_s < event.start_s or event.end_s + pad_s < seg.start_s:
            continue
        if seg.text:
            hits.append(seg.text)
    return " ".join(hits).strip()


def examples_from_bundle(bundle: TraceBundle, *, tolerance_s: float = 2.0, min_votes: Optional[int] = None) -> List[OracleExample]:
    consensus = consensus_trace(bundle.traces, tolerance_s=tolerance_s, min_votes=min_votes)
    out = []
    for i, event in enumerate(consensus):
        md = dict(event.metadata or {})
        votes = int(md.get("votes", 1) or 1)
        example_id = f"{bundle.talk_id}:{i:04d}:{event.function}:{event.representation}"
        out.append(OracleExample(
            example_id=example_id,
            talk_id=bundle.talk_id,
            start_s=event.start_s,
            end_s=event.end_s,
            function=event.function,
            representation=event.representation,
            confidence=float(event.confidence if event.confidence is not None else votes / max(1, len(bundle.traces))),
            votes=votes,
            editor_count=len(bundle.traces),
            transcript_text=transcript_for_event(bundle.transcript, event),
            context=dict(bundle.context),
            metadata={"editors": md.get("editors", bundle.editor_names), "bundle_metadata": dict(bundle.metadata)},
        ))
    return out


def _split_for_talk(talk_id: str, eval_fraction: float) -> str:
    n = int.from_bytes(sha256(talk_id.encode("utf-8")).digest()[:8], "big") / 2**64
    return "eval" if n < eval_fraction else "train"


def build_dataset(bundles: Sequence[TraceBundle], *, eval_fraction: float = 0.25, tolerance_s: float = 2.0, min_votes: Optional[int] = None) -> Dict[str, Any]:
    if not 0 <= eval_fraction < 1:
        raise ValueError("eval_fraction must be in [0, 1)")
    examples: List[OracleExample] = []
    bundle_rows = []
    talk_seen, text_seen = set(), set()
    for bundle in bundles:
        if bundle.talk_id in talk_seen:
            raise ValueError(f"duplicate talk_id: {bundle.talk_id}")
        talk_seen.add(bundle.talk_id)
        text = " ".join(" ".join(s.text.lower().split()) for s in bundle.transcript)
        text_hash = sha256(text.encode()).hexdigest()
        if text and text_hash in text_seen:
            raise ValueError("duplicate transcript under different talk IDs")
        text_seen.add(text_hash)
        rows = examples_from_bundle(bundle, tolerance_s=tolerance_s, min_votes=min_votes)
        examples.extend(rows)
        bundle_rows.append({"talk_id": bundle.talk_id, "editors": list(bundle.editor_names), "editor_count": len(bundle.traces), "consensus_examples": len(rows), "context": dict(bundle.context)})

    splits = {"train": [], "eval": []}
    group_for = lambda ex: str(ex.metadata["bundle_metadata"].get("split_group") or ex.talk_id)
    for ex in examples:
        splits[_split_for_talk(group_for(ex), eval_fraction)].append(ex.to_dict())

    talk_ids = sorted({x.talk_id for x in examples})
    group_ids = sorted({group_for(ex) for ex in examples})
    if eval_fraction > 0 and len(group_ids) >= 2 and (not splits["train"] or not splits["eval"]):
        eval_group = group_ids[-1]
        splits = {"train": [], "eval": []}
        for ex in examples:
            splits["eval" if group_for(ex) == eval_group else "train"].append(ex.to_dict())

    function_counts = Counter(x.function for x in examples)
    representation_counts = Counter(x.representation for x in examples)
    pair_counts = Counter((x.function, x.representation) for x in examples)
    warnings = []
    if not splits["train"] or not splits["eval"]:
        warnings.append("empty train or eval split: no held-out quality claim is possible")
    if len(talk_ids) < 4:
        warnings.append("fewer than 4 talks: evaluation is only a pipeline check")
    if any(x.editor_count < 2 for x in examples):
        warnings.append("some consensus examples have fewer than 2 editor traces")
    if examples and sum(x.confidence for x in examples) / len(examples) < .67:
        warnings.append("mean consensus confidence is below 0.67")
    train_talks = {x["talk_id"] for x in splits["train"]}
    eval_talks = {x["talk_id"] for x in splits["eval"]}
    assert not (train_talks & eval_talks), "talk leakage across train/eval"

    return {
        "version": 10,
        "schema": "live_presenter.oracle_dataset.v1",
        "parameters": {"eval_fraction": eval_fraction, "consensus_tolerance_s": tolerance_s, "min_votes": min_votes},
        "bundles": bundle_rows,
        "splits": splits,
        "stats": {
            "talk_count": len(talk_ids),
            "example_count": len(examples),
            "train_examples": len(splits["train"]),
            "eval_examples": len(splits["eval"]),
            "train_talks": sorted(train_talks),
            "eval_talks": sorted(eval_talks),
            "split_group_count": len(group_ids),
            "min_consensus_votes": min((x.votes for x in examples), default=0),
            "function_counts": dict(sorted(function_counts.items())),
            "representation_counts": dict(sorted(representation_counts.items())),
            "function_representation_counts": {f"{a}:{b}": n for (a, b), n in sorted(pair_counts.items())},
            "mean_consensus_confidence": round(sum(x.confidence for x in examples) / len(examples), 4) if examples else 0.0,
            "warnings": warnings,
        },
    }


def build_dataset_from_paths(paths: Iterable[Path | str], **kwargs) -> Dict[str, Any]:
    return build_dataset([load_bundle(p) for p in paths], **kwargs)


def write_dataset(dataset: Mapping[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
