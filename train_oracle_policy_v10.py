#!/usr/bin/env python3
"""CLI: bundles -> leak-resistant dataset -> oracle representation policy."""
from __future__ import annotations
import argparse, json, os
from hashlib import sha256
from pathlib import Path
from oracle_dataset_v10 import build_dataset_from_paths, write_dataset
from representation_policy_v10 import OracleRepresentationPolicy, evaluate_policy
from corpus_v10 import audit
from research_evidence_v10 import json_hash

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("bundles",nargs="+",help="JSON trace bundles")
    ap.add_argument("--out-dir",default="artifacts/v10"); ap.add_argument("--eval-fraction",type=float,default=.25); ap.add_argument("--tolerance",type=float,default=2.0)
    ap.add_argument("--pipeline-only",action="store_true",help="allow pilot/synthetic plumbing; never empirical evidence")
    args=ap.parse_args(); out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)
    quality=audit([Path(p) for p in args.bundles])
    if quality['errors']:ap.error('; '.join(quality['errors']))
    if not args.pipeline_only and quality['eligible_talks'] != len(args.bundles):
        ap.error('corpus has unresolved rights/context/editor checks; inspect corpus_v10.py audit or use --pipeline-only')
    dataset=build_dataset_from_paths(args.bundles,eval_fraction=args.eval_fraction,tolerance_s=args.tolerance,
                                     min_votes=None if args.pipeline_only else 2)
    if not args.pipeline_only and (not dataset['splits']['train'] or not dataset['splits']['eval']):
        ap.error('training and evaluation both need nonempty, isolated source groups')
    dataset['stats']['empirical_eligible_talks']=quality['eligible_talks']
    dataset['stats']['pipeline_only']=args.pipeline_only
    dataset['stats']['non_fixture_talks']=quality['non_fixture_talks']
    dataset['source_bundles']=[{'path':os.path.relpath(Path(p).resolve(),out.resolve()),
                               'sha256':sha256(Path(p).read_bytes()).hexdigest()} for p in args.bundles]
    dataset['dataset_sha256']=json_hash(dataset)
    write_dataset(dataset,out/"oracle_dataset_v10.json")
    policy=OracleRepresentationPolicy.fit(dataset["splits"]["train"]); policy.save(out/"oracle_policy_v10.json")
    evaluation=evaluate_policy(policy,dataset["splits"]["eval"])
    evaluation['dataset_sha256']=dataset['dataset_sha256']
    evaluation['policy_sha256']=json_hash(policy.artifact)
    (out/"oracle_policy_eval_v10.json").write_text(json.dumps(evaluation,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"dataset":dataset["stats"],"evaluation":{k:v for k,v in evaluation.items() if k!="rows"},"policy":policy.snapshot()},indent=2))
if __name__=="__main__":main()
