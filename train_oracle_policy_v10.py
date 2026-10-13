#!/usr/bin/env python3
"""CLI: bundles -> leak-resistant dataset -> oracle representation policy."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from oracle_dataset_v10 import build_dataset_from_paths, write_dataset
from representation_policy_v10 import OracleRepresentationPolicy, evaluate_policy

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("bundles",nargs="+",help="JSON trace bundles")
    ap.add_argument("--out-dir",default="artifacts/v10"); ap.add_argument("--eval-fraction",type=float,default=.25); ap.add_argument("--tolerance",type=float,default=2.0)
    args=ap.parse_args(); out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)
    dataset=build_dataset_from_paths(args.bundles,eval_fraction=args.eval_fraction,tolerance_s=args.tolerance)
    write_dataset(dataset,out/"oracle_dataset_v10.json")
    policy=OracleRepresentationPolicy.fit(dataset["splits"]["train"]); policy.save(out/"oracle_policy_v10.json")
    evaluation=evaluate_policy(policy,dataset["splits"]["eval"])
    (out/"oracle_policy_eval_v10.json").write_text(json.dumps(evaluation,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"dataset":dataset["stats"],"evaluation":{k:v for k,v in evaluation.items() if k!="rows"},"policy":policy.snapshot()},indent=2))
if __name__=="__main__":main()
