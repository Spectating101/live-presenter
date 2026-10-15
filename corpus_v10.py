#!/usr/bin/env python3
"""Acquire NASA caption candidates, prepare independent editor jobs, and audit evidence.

Network acquisition is explicit. Downloads and editor prompts stay in ignored
artifacts/. A downloaded transcript is not automatically rights-reviewed or
eligible training evidence. No editor trace is fabricated by this tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from editor_trace_tools_v10 import build_prompt, validate_editor_rows
from transcript_io_v10 import load_transcript

SVS = "https://svs.gsfc.nasa.gov"
RIGHTS_URL = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
CONTEXT_KEYS = ("has_dataset", "has_images", "has_sources", "graph_ready", "has_map_data", "has_timeline_data")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def transcript_digest(segments) -> str:
    text = " ".join(s["text"] for s in segments)
    return digest(re.sub(r"\W+", " ", text.lower()).strip().encode())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def fetch(url: str, *, retries=2) -> bytes:
    parsed = urlparse(url)
    if parsed.hostname != "svs.gsfc.nasa.gov" or parsed.scheme not in {"http", "https"}:
        raise ValueError("acquisition only downloads from svs.gsfc.nasa.gov")
    url = quote(url.replace("http://", "https://", 1), safe=":/?&=%+#")
    for attempt in range(retries + 1):
        try:
            with urlopen(Request(url, headers={"User-Agent": "LivePresenterResearch/10"}), timeout=30) as r:
                data = r.read(5_000_001)
            if len(data) > 5_000_000:
                raise ValueError("metadata/caption response exceeds 5 MB limit")
            return data
        except OSError:
            if attempt == retries:
                raise
            time.sleep(attempt + 1)
    raise AssertionError("unreachable")


def captions(node):
    if isinstance(node, dict):
        if node.get("media_type") == "Captions" and urlparse(node.get("url", "")).path.endswith(".srt"):
            yield node
        for value in node.values():
            yield from captions(value)
    elif isinstance(node, list):
        for value in node:
            yield from captions(value)


def normalize_captions(raw):
    clean, rejected = [], []
    for i, s in enumerate(raw):
        start, end = float(s.get("start_s", s.get("start"))), float(s.get("end_s", s.get("end")))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or not s["text"].strip():
            rejected.append({"index": i, "reason": "empty text or invalid caption interval"})
            continue
        if clean and start < clean[-1]["end_s"]:
            raise ValueError("overlapping or unordered source captions require manual review")
        clean.append({"start_s": start, "end_s": end, "text": s["text"]})
    return clean, rejected


def acquire(out: Path, *, limit=30, min_seconds=180, max_seconds=3600, seed_path: Path | None = None, max_per_page=3) -> dict:
    if limit <= 0 or min_seconds < 0 or max_seconds <= min_seconds:
        raise ValueError("invalid acquisition count or duration range")
    out.mkdir(parents=True, exist_ok=True)
    records, failures, seen_text, seen_urls, page_counts = [], [], set(), set(), {}
    now = datetime.now(timezone.utc).isoformat()
    if seed_path:
        seeds = json.loads(seed_path.read_text())["records"]
        candidates = [(r["page_id"], r["caption_url"], r) for r in seeds]
    else:
        ids = [31168, 31138, 11668]
        for query in ("hyperwall presentations", "lecture", "presentation", "science live", "talk"):
            data = json.loads(fetch(SVS + "/api/search/?" + urlencode({"search": query, "limit": 60})))
            ids.extend(r["id"] for r in data["results"] if r.get("result_type") != "Gallery")
        candidates = [(ident, None, None) for ident in dict.fromkeys(ids)]
    for ident, pinned_url, pinned in candidates:
        if len(records) >= limit:
            break
        try:
            page_path = out / "pages" / f"{ident}.json"
            if not page_path.exists():
                write_json(page_path, json.loads(fetch(f"{SVS}/api/{ident}/")))
            page = json.loads(page_path.read_text())
            items = list(captions(page.get("media_groups", [])))
            for cap in items:
                if not pinned_url and page_counts.get(ident, 0) >= max_per_page:
                    break
                url = cap["url"].replace("http://", "https://", 1)
                if not urlparse(url).path.lower().endswith(".en_us.srt"):
                    continue  # This tranche explicitly uses English locale-tagged captions only.
                if pinned_url and url != pinned_url:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                talk_id = f"nasa_{ident}_{digest(url.encode())[:10]}"
                folder = out / talk_id
                folder.mkdir(parents=True, exist_ok=True)
                raw_path = folder / "transcript.srt"
                if not raw_path.exists():
                    raw_path.write_bytes(fetch(url))
                raw = raw_path.read_bytes()
                if pinned and digest(raw) != pinned["caption_sha256"]:
                    raise ValueError(f"source changed for {talk_id}; review before replacing the pinned hash")
                segments, rejected = normalize_captions(load_transcript(raw_path))
                if not segments:
                    continue
                duration = segments[-1]["end_s"]
                if not min_seconds <= duration <= max_seconds:
                    continue
                word_count = sum(len(s['text'].split()) for s in segments)
                if word_count < 400 or word_count / (duration / 60) < 40:
                    continue  # Exclude sparse data-label captions, e.g. silent moon animations.
                text_hash = transcript_digest(segments)
                if text_hash in seen_text:
                    continue
                seen_text.add(text_hash)
                source = f"{SVS}/{ident}/"
                record = {"talk_id": talk_id, "page_id": ident, "source_uri": source,
                          "title": page["title"], "caption_filename": Path(urlparse(url).path).name,
                          "caption_url": url, "caption_sha256": digest(raw), "transcript_sha256": text_hash,
                          "duration_s": duration, "segments": len(segments), "acquired_at": now,
                          "word_count": word_count, "omitted_caption_cues": rejected,
                          "rights_status": "pending_source_review", "rights_policy_uri": RIGHTS_URL,
                          "split_group": f"nasa_page_{ident}", "domain": "science_engineering"}
                records.append(record)
                page_counts[ident] = page_counts.get(ident, 0) + 1
                bundle_path = folder / "bundle.json"
                if not bundle_path.exists():
                    write_json(bundle_path, {"talk_id": talk_id, "transcript": segments, "editors": [],
                        "context": {k: False for k in CONTEXT_KEYS},
                        "metadata": {**record, "fixture": False, "language": "en", "pilot": True,
                                     "independent_editors": False, "context_reviewed": False,
                                     "rights_basis": "NASA-hosted captions acquired for research; source-specific rights review pending."}})
                write_json(out / "acquisition_progress.json", {"records": records, "failures": failures})
                print(f"acquired {len(records)}/{limit}: {talk_id} ({duration:.0f}s)", flush=True)
                if len(records) >= limit:
                    break
        except (OSError, ValueError, KeyError) as e:
            failures.append({"page_id": ident, "error": str(e)})
    result = {"schema": "live_presenter.corpus_sources.v1", "created_at": now,
              "target": limit, "acquired": len(records), "records": records, "failures": failures,
              "selection": {"min_seconds": min_seconds, "max_seconds": max_seconds, "max_per_page": max_per_page,
                            "min_words": 400, "min_words_per_minute": 40},
              "limitations": ["NASA science tranche only; broader domain strata remain uncollected.",
                              "Acquisition does not establish rights clearance or editor independence.",
                              "Combined broadcasts may overlap individual talks; review source groups before splitting."]}
    write_json(out / "sources.json", result)
    return result


def audit(paths: list[Path]) -> dict:
    rows, ids, hashes, errors, non_fixture = [], set(), {}, [], 0
    for path in paths:
        b = json.loads(path.read_text())
        talk_id, transcript = b["talk_id"], b["transcript"]
        issues = []
        if talk_id in ids:
            errors.append(f"duplicate talk_id: {talk_id}")
        ids.add(talk_id)
        text_hash = transcript_digest(transcript)
        if text_hash in hashes:
            errors.append(f"duplicate transcript: {talk_id} and {hashes[text_hash]}")
        hashes[text_hash] = talk_id
        from eval_system1_v10 import validate_segments
        try:
            validate_segments(transcript)
        except (ValueError, KeyError, TypeError) as e:
            errors.append(f"{talk_id}: {e}")
            issues.append("invalid transcript timing")
        meta = b.get("metadata", {})
        non_fixture += not bool(meta.get("fixture"))
        if not meta.get("source_uri"):
            issues.append("source URI missing")
        if meta.get("rights_status") != "reviewed" or not (meta.get("license") or meta.get("rights_basis")):
            issues.append("source-specific rights review pending")
        if meta.get("context_reviewed") is not True:
            issues.append("asset context review pending")
        editors = b.get("editors", [])
        trace_hashes = [e["trace_sha256"] for e in editors if e.get("trace_sha256")]
        if len(trace_hashes) != len(set(trace_hashes)):
            issues.append("duplicate imported editor trace; independence review required")
        names = [e.get("name") for e in editors]
        if len(names) != len(set(names)):
            issues.append("editor identities must be distinct")
        families = {e.get("family") for e in editors if e.get("family") and e.get("version") and e.get("mode") == "oracle"}
        if len(families) < 2 or meta.get("independent_editors") is not True:
            issues.append("two independent, versioned oracle editors required")
        for editor in editors:
            clean, problems = validate_editor_rows(editor.get("events", []), transcript, b.get("context", {}))
            if problems or not clean:
                issues.append(f"invalid or empty editor trace: {editor.get('name')}")
        rows.append({"talk_id": talk_id, "path": str(path), "editors": len(editors),
                     "families": sorted(families), "eligible": not issues and not meta.get("fixture", False),
                     "issues": issues, "segments": len(transcript), "transcript_sha256": text_hash,
                     "split_group": meta.get("split_group", talk_id)})
    return {"schema": "live_presenter.corpus_audit.v1", "talks": len(rows),
            "non_fixture_talks": non_fixture,
            "eligible_talks": sum(r["eligible"] for r in rows) if not errors else 0, "errors": errors, "rows": rows}


def prepare_jobs(paths: list[Path], out: Path, families: list[str]) -> int:
    if len(set(families)) < 2:
        raise ValueError("at least two distinct editor families are required")
    count = 0
    for path in paths:
        b = json.loads(path.read_text())
        brief = "Use only supplied transcript and asset availability. No video, datasets or images are loaded."
        prompt = build_prompt(b["transcript"], b.get("context", {}), brief=brief)
        for family in families:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", family):
                raise ValueError("editor family must be a simple identifier")
            folder = out / b["talk_id"] / family
            folder.mkdir(parents=True, exist_ok=True)
            old_job = folder / "job.json"
            if old_job.exists() and json.loads(old_job.read_text()).get("status") == "complete":
                continue
            (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
            job = {"talk_id": b["talk_id"], "family": family, "mode": "oracle", "status": "pending",
                   "prompt_sha256": digest(prompt.encode()), "bundle_sha256": digest(path.read_bytes()),
                   "transcript_sha256": transcript_digest(b["transcript"]), "context": b.get("context", {}),
                   "instructions": "Use a fresh model/session. Do not show other editor traces. Record exact model version and return JSON rows."}
            write_json(folder / "job.json", job)
            count += 1
    return count


def attach_editor(bundle_path: Path, trace_path: Path, job_path: Path, *, name: str, version: str) -> dict:
    """Import a completed job without replacing an existing editor or changing source text."""
    b, job = json.loads(bundle_path.read_text()), json.loads(job_path.read_text())
    if not name.strip() or not version.strip():
        raise ValueError("editor name and exact version are required")
    if job["talk_id"] != b["talk_id"] or job.get("mode") != "oracle":
        raise ValueError("job must be an oracle job for this talk")
    if job.get("transcript_sha256") != transcript_digest(b["transcript"]) or job.get("context") != b.get("context", {}):
        raise ValueError("transcript/context changed since this job was prepared; regenerate the prompt")
    prompt_path = job_path.with_name("prompt.txt")
    if digest(prompt_path.read_bytes()) != job["prompt_sha256"]:
        raise ValueError("editor prompt hash changed")
    raw = json.loads(trace_path.read_text())
    if not isinstance(raw, list):
        raise ValueError("editor trace must be a JSON array")
    clean, problems = validate_editor_rows(raw, b["transcript"], b.get("context", {}))
    if problems or not clean:
        raise ValueError("invalid or empty trace: " + "; ".join(problems))
    editors = b.setdefault("editors", [])
    if any(e["name"] == name for e in editors):
        raise ValueError("editor name already exists; use a new versioned identity")
    editor = {"name": name, "shape": "generic", "family": job["family"], "version": version,
              "mode": "oracle", "prompt_sha256": job["prompt_sha256"],
              "trace_sha256": digest(trace_path.read_bytes()), "events": clean}
    editors.append(editor)
    # Distinct families are recorded as a candidate ensemble, not automatically
    # certified independent: a reviewer must set independent_editors explicitly.
    write_json(bundle_path, b)
    write_json(job_path, {**job, "status": "complete", "editor_name": name, "version": version,
                          "trace_sha256": editor["trace_sha256"]})
    return editor


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    ac = sub.add_parser("acquire-nasa")
    ac.add_argument("--out-dir", type=Path, default=Path("artifacts/corpus"))
    ac.add_argument("--limit", type=int, default=30)
    ac.add_argument("--sources", type=Path, help="replay a pinned sources.json instead of searching")
    for command in ("audit", "prepare-jobs"):
        p = sub.add_parser(command)
        p.add_argument("bundles", nargs="*", type=Path)
        p.add_argument("--corpus-dir", type=Path, help="use exactly the records selected in this directory's sources.json")
        p.add_argument("--out", type=Path, default=Path("artifacts/corpus_audit.json") if command == "audit" else Path("artifacts/editor_jobs"))
        if command == "prepare-jobs":
            p.add_argument("--families", nargs="+", default=["human", "independent_model"])
    at = sub.add_parser("attach-editor")
    at.add_argument("--bundle", required=True, type=Path)
    at.add_argument("--trace", required=True, type=Path)
    at.add_argument("--job", required=True, type=Path)
    at.add_argument("--name", required=True)
    at.add_argument("--version", required=True)
    args = ap.parse_args()
    if args.command in {"audit", "prepare-jobs"} and args.corpus_dir:
        selected = json.loads((args.corpus_dir / "sources.json").read_text())["records"]
        args.bundles = [args.corpus_dir / r["talk_id"] / "bundle.json" for r in selected]
    if args.command in {"audit", "prepare-jobs"} and not args.bundles:
        ap.error("supply bundles or --corpus-dir with a completed sources.json")
    if args.command == "acquire-nasa":
        r = acquire(args.out_dir, limit=args.limit, seed_path=args.sources)
        print(json.dumps({"acquired": r["acquired"], "target": r["target"], "failures": len(r["failures"])}, indent=2))
        if r["acquired"] < r["target"]:
            raise SystemExit(2)
    elif args.command == "audit":
        r = audit(args.bundles)
        write_json(args.out, r)
        print(json.dumps({k: v for k, v in r.items() if k != "rows"}, indent=2))
        if r["errors"]:
            raise SystemExit(2)
    elif args.command == "prepare-jobs":
        print(json.dumps({"jobs": prepare_jobs(args.bundles, args.out, args.families), "out": str(args.out)}))
    else:
        e = attach_editor(args.bundle, args.trace, args.job, name=args.name, version=args.version)
        print(json.dumps({"editor": e["name"], "events": len(e["events"])}))


if __name__ == "__main__":
    main()
