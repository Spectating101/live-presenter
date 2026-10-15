#!/usr/bin/env python3
"""Measure real Jev latency/behaviour from THIS machine.  Needs JEV_API_KEY.

Usage: python bench_system1_v10.py [--n 20] [--srt talk.srt] [--policy artifacts/v10/oracle_policy_v10.json]
Prints p50/p95 latency, abstain rate, agreement with the count-table policy.
Run it from the machine that will present (e.g. Taiwan); vendor latency figures are not yours.
"""
import argparse, asyncio, json
from datetime import datetime, timezone
from pathlib import Path
from jev_credentials_v10 import load_jev_env
from transcript_io_v10 import parse_srt
from representation_policy_v10 import OracleRepresentationPolicy
from system1_v10 import JevBackend, System1Assessor

SAMPLE = ["Sales doubled between 2019 and 2023.", "That works because the pump pushes water uphill.",
          "Compare that to the older design, which was far slower.", "The study by Kim et al. supports this claim.",
          "Now let's talk about something different: funding."]

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=20); ap.add_argument("--srt"); ap.add_argument("--policy")
    ap.add_argument("--out"); ap.add_argument("--timeout-s", type=float, default=5.0)
    ap.add_argument("--env-file", help="Jev credentials file; or set JEV_ENV_FILE")
    a = ap.parse_args()
    if a.n <= 0: ap.error("--n must be positive")
    lines = [s["text"] for s in parse_srt(a.srt)] if a.srt else SAMPLE
    policy = OracleRepresentationPolicy.load(a.policy) if a.policy else None
    if not lines: ap.error("transcript contains no captions")
    load_jev_env(a.env_file)
    backend = JevBackend(timeout_s=a.timeout_s); print("models:", [m["name"] for m in await backend.models()])
    s = System1Assessor(backend, fallback=policy); ctx = {"has_dataset": True, "has_sources": True, "has_images": True}
    rows = []
    for i in range(a.n):
        r = await s.assess(lines[i % len(lines)], current_topic="demo", context=ctx)
        rows.append(r.to_dict())
        print(f"{r.latency_ms:7.1f} ms  {r.source:11} act={r.act} rep={r.representation} abstain={r.abstain} {r.error or ''}")
    summary = s.summary()
    if a.out:
        p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema":"live_presenter.jev_bench.v1", "created_at":datetime.now(timezone.utc).isoformat(),
                                "timeout_s":a.timeout_s, "context":ctx, "summary":summary,"assessments":rows},indent=2)+"\n")
    print(json.dumps(summary, indent=2))
    if summary["backend_failures"]: raise SystemExit(2)
if __name__ == "__main__": asyncio.run(main())
