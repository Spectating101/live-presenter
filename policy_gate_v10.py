#!/usr/bin/env python3
"""Evidence gate for promoting an oracle-distilled policy beyond shadow mode."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional
import argparse, json
from pathlib import Path

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
            'browser_rehearsal_ok':bool(browser_rehearsal_ok)}
    for key in ('talk_count','example_count','eval_examples','coverage','selective_accuracy'):
        if checks[key] < t[key]:fail.append(f'{key} {checks[key]} < required {t[key]}')
    if requested_mode in {'canary','active'}:
        if non_fixture_talks is None or non_fixture_talks < t['talk_count']:fail.append(f'non_fixture_talks {non_fixture_talks} < required {t["talk_count"]}')
        if not browser_rehearsal_ok:fail.append('browser rehearsal evidence missing or failed')
    if requested_mode=='active' and dataset_stats.get('warnings'):fail.append('dataset warnings must be cleared before active mode')
    return GateResult(requested_mode,not fail,fail,checks)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--evaluation',required=True);ap.add_argument('--mode',choices=sorted(THRESHOLDS),default='canary');ap.add_argument('--non-fixture-talks',type=int);ap.add_argument('--browser-rehearsal-ok',action='store_true');args=ap.parse_args()
    d=json.loads(Path(args.dataset).read_text());e=json.loads(Path(args.evaluation).read_text());r=assess(d['stats'],e,requested_mode=args.mode,non_fixture_talks=args.non_fixture_talks,browser_rehearsal_ok=args.browser_rehearsal_ok);print(json.dumps(r.to_dict(),indent=2))
if __name__=='__main__':main()
