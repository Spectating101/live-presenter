#!/usr/bin/env python3
"""Evidence gate for promoting an oracle-distilled policy beyond shadow mode."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional
import argparse, json, math
from pathlib import Path
from research_evidence_v10 import verify_artifacts

@dataclass(frozen=True)
class GateResult:
    requested_mode:str
    eligible:bool
    failures:list[str]
    checks:Dict[str,Any]
    def to_dict(self):return asdict(self)

THRESHOLDS={
    'shadow': {'talk_count': 0, 'example_count': 0, 'eval_examples': 0, 'coverage': 0.0, 'selective_accuracy': 0.0},
    'canary': {'talk_count': 30, 'example_count': 150, 'eval_examples': 40, 'coverage': .65, 'selective_accuracy': .75},
    'active': {'talk_count': 100, 'example_count': 500, 'eval_examples': 100, 'coverage': .80, 'selective_accuracy': .82},
}

def assess(dataset_stats:Mapping[str,Any], evaluation:Mapping[str,Any], *, requested_mode='canary', non_fixture_talks:Optional[int]=None, browser_rehearsal_ok:bool=False)->GateResult:
    if requested_mode not in THRESHOLDS:raise ValueError(f'unknown mode: {requested_mode}')
    t=THRESHOLDS[requested_mode];fail=[]
    checks={'talk_count':int(dataset_stats.get('talk_count',0)),'example_count':int(dataset_stats.get('example_count',0)),
            'eval_examples':int(evaluation.get('examples',0)),'coverage':float(evaluation.get('coverage',0) or 0),
            'selective_accuracy':float(evaluation.get('selective_accuracy',0) or 0),'non_fixture_talks':non_fixture_talks,
            'browser_rehearsal_ok':browser_rehearsal_ok is True}
    for key in ('talk_count','example_count','eval_examples','coverage','selective_accuracy'):
        value=checks[key]
        if not math.isfinite(value) or value < 0 or (key in {'coverage','selective_accuracy'} and value > 1):
            fail.append(f'{key} is not a valid finite measurement')
        elif value < t[key]:fail.append(f'{key} {value} < required {t[key]}')
    if requested_mode in {'canary','active'}:
        if dataset_stats.get('pipeline_only'):
            fail.append('pipeline-only dataset cannot earn promotion')
        eligible=int(dataset_stats.get('empirical_eligible_talks',0))
        if eligible < t['talk_count']:
            fail.append(f'empirical_eligible_talks {eligible} < required {t["talk_count"]}')
        if non_fixture_talks is None or non_fixture_talks < t['talk_count']:fail.append(f'non_fixture_talks {non_fixture_talks} < required {t["talk_count"]}')
        if browser_rehearsal_ok is not True:fail.append('browser rehearsal evidence missing or failed')
    if requested_mode=='active' and dataset_stats.get('warnings'):fail.append('dataset warnings must be cleared before active mode')
    if requested_mode in {'canary','active'} and dataset_stats.get('split_group_count',0) < 2:
        fail.append('at least two isolated source groups are required')
    if requested_mode in {'canary','active'} and dataset_stats.get('min_consensus_votes',0) < 2:
        fail.append('empirical examples require at least two editor votes')
    return GateResult(requested_mode,not fail,fail,checks)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--evaluation',required=True);ap.add_argument('--mode',choices=sorted(THRESHOLDS),default='canary');ap.add_argument('--non-fixture-talks',type=int);ap.add_argument('--browser-rehearsal-ok',action='store_true');args=ap.parse_args()
    d=json.loads(Path(args.dataset).read_text())
    e=json.loads(Path(args.evaluation).read_text())
    failures=verify_artifacts(d,e,base_dir=Path(args.dataset).resolve().parent)
    recorded=d['stats'].get('non_fixture_talks',0)
    if args.non_fixture_talks is not None and args.non_fixture_talks != recorded:
        failures.append('declared non-fixture count differs from source-bound dataset')
    r=assess(d['stats'],e,requested_mode=args.mode,non_fixture_talks=recorded,browser_rehearsal_ok=args.browser_rehearsal_ok)
    result=r.to_dict()
    result['failures'].extend(failures)
    result['eligible']=r.eligible and not failures
    result['checks']['artifact_binding_ok']=not failures
    print(json.dumps(result,indent=2))
    if not result['eligible']:raise SystemExit(2)
if __name__=='__main__':main()
