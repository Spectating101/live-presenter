#!/usr/bin/env python3
"""Read-only readiness report. Offline research readiness does not imply stage readiness."""
import argparse
import importlib
import json
from pathlib import Path
import platform

from corpus_v10 import audit, write_json
from jev_credentials_v10 import load_jev_env

ROOT = Path(__file__).resolve().parent


def report(root=ROOT):
    required = ("editorial_trace_v9", "oracle_benchmark_v9", "oracle_dataset_v10",
                "representation_policy_v10", "system1_v10", "eval_system1_v10")
    imports = {}
    for name in (*required, "runtime_v10"):
        try:
            importlib.import_module(name)
            imports[name] = "ok"
        except ImportError as e:
            imports[name] = str(e)
    missing = []
    manifest = root / "SOURCE_MANIFEST_V10.txt"
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            _, name = line.split(maxsplit=1)
            if not (root / name).is_file():
                missing.append(name.removeprefix("./"))
    source_file = root / "artifacts/corpus_tranche1/sources.json"
    if source_file.exists():
        sources = json.loads(source_file.read_text())["records"]
        bundles = [source_file.parent / r["talk_id"] / "bundle.json" for r in sources]
    else:
        bundles = sorted((root / "artifacts/corpus_tranche1").glob("*/bundle.json"))
    corpus = audit(bundles)
    return {"schema": "live_presenter.readiness.v1", "python": platform.python_version(),
            "offline_modules_ready": all(imports[n] == "ok" for n in required),
            "stage_ready": imports["runtime_v10"] == "ok" and not any(
                n.startswith(("stage", "rehearsal")) for n in missing),
            "jev_key_available": load_jev_env(), "imports": imports,
            "missing_checkpoint_files": missing,
            "corpus": {k: v for k, v in corpus.items() if k != "rows"},
            "policy_authority": "advisory_only",
            "next_requirements": ["Recover missing frozen runtime/stage/test source using SOURCE_MANIFEST_V10.txt.",
                                  "Review corpus source rights and asset context; add independent versioned editors.",
                                  "Train/evaluate by held-out source group and clear empirical promotion gates.",
                                  "Rehearse on Chromium and measure STT-to-stage latency on presentation hardware."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--require-stage", action="store_true")
    ap.add_argument("--require-jev", action="store_true")
    args = ap.parse_args()
    r = report()
    if args.out:
        write_json(args.out, r)
    print(json.dumps(r, indent=2))
    if not r["offline_modules_ready"] or (args.require_stage and not r["stage_ready"]) or (args.require_jev and not r["jev_key_available"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
