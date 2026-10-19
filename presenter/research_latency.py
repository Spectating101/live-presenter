"""Serial paired backend latency probes from one frozen, past-only request.

No cache is shared between processes. External provider caches/network load
remain uncontrolled. This does not measure ASR, stage API or browser rendering.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from jev_credentials_v10 import load_jev_env
from .research import ResearchProcess
from .recording import file_hash, save


def run(folder,baseline_root,out_dir,repeats=3):
    folder,baseline_root,out_dir=Path(folder),Path(baseline_root).resolve(),Path(out_dir)
    out_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (out_dir/'result.json').exists():raise ValueError('Use a new output directory.')
    if not 1<=repeats<=5:raise ValueError('Choose one to five paired repetitions.')
    prior=json.loads((folder/'result.json').read_text());prepared=json.loads((folder/'prepared-project.json').read_text())
    history=next(row for row in prior['research_history'] if row['status']=='ready')
    context={'title':prepared['title'],'brief':prepared['brief'],
        'concepts':[{key:concept[key] for key in ('title','summary','aliases')} for concept in prepared['plan']['concepts']],
        'utterance':history['utterance'],'recent_past':history['recent_past']}
    save(out_dir/'context.json',context)
    load_jev_env()
    baseline_command=[sys.executable,'-c',
        'import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_module("presenter.web_research",run_name="__main__")',str(baseline_root)]
    baseline_sha=subprocess.check_output(['git','-C',str(baseline_root),'rev-parse','HEAD'],text=True).strip()
    result={'schema':'live_presenter.research_latency.v1','context_sha256':file_hash(out_dir/'context.json'),
        'source_recording_result_sha256':file_hash(folder/'result.json'),'baseline_commit':baseline_sha,
        'optimized_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'optimized_fingerprints':{name:file_hash(Path(__file__).with_name(name)) for name in ('research.py','web_research.py','research_sources.py')},
        'conditions':[],'limits':['Same known development question, alternating serial order; no independence/reliability estimate.',
            'Fresh child processes with no application result cache; external search/CDN caches remain uncontrolled.',
            'Measures backend result receipt, excluding ASR, scheduling, stage API and browser paint.',
            'First supported quotation can come from a different source than the baseline. Optional enrichment may take longer.']}
    save(out_dir/'result.json',result)
    for repetition in range(repeats):
        for mode in (['baseline','progressive'] if repetition%2==0 else ['progressive','baseline']):
            started=time.monotonic();first=[];partials=[]
            def publish(packet):
                if packet.get('status')=='ready' and packet.get('items'):
                    if not first:first.append(time.monotonic()-started)
                    partials.append(copy.deepcopy(packet))
            backend=ResearchProcess(command=baseline_command if mode=='baseline' else [sys.executable,'-m','presenter.web_research'])
            row={'repetition':repetition,'mode':mode}
            try:
                response=backend.run(context,threading.Event()) if mode=='baseline' else backend.run_progressive(context,threading.Event(),publish)
                final_elapsed=time.monotonic()-started
                if not first and response.get('status')=='ready' and response.get('items'):first.append(final_elapsed)
                raw=out_dir/f'{repetition}-{mode}.json';save(raw,{'result':response,'partials':partials})
                earliest=partials[0] if partials else response
                row.update(status=response['status'],first_supported_result_s=first[0] if first else None,
                    final_result_s=final_elapsed,cache_hit=response.get('cache_hit',False),
                    sources=[{'title':scene['title'],'kind':scene['kind'],'url':scene['web_source']['url'],
                        'quote_sha256':hashlib.sha256(scene['source_refs'][0]['quote'].encode()).hexdigest()} for scene in earliest.get('items',[])],
                    timing=earliest.get('timing',{}),classifier_calls=earliest.get('classifier_calls',[]),raw_sha256=file_hash(raw))
            except Exception as exc:
                row.update(status='error',error_type=type(exc).__name__,elapsed_s=time.monotonic()-started,
                           first_supported_result_s=first[0] if first else None)
            result['conditions'].append(row);save(out_dir/'result.json',result)
            print(json.dumps(row),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--baseline-root',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args();run(args.folder,args.baseline_root,args.out_dir,args.repeats)


if __name__=='__main__':main()
