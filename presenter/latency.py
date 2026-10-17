"""Best-case eligible prepared-cue -> read-only stage API response benchmark.

No ASR or browser paint is included. A simulated rehearsal clock advances between
samples so the ordinary 2.5-second display dwell is satisfied, never disabled.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import urllib.request

from .engine import Store, Studio
from .recording import file_hash, percentile, save
from .server import make_server


def benchmark(folder, samples=40):
    if not 2 <= samples <= 1000:
        raise ValueError('Use between 2 and 1,000 samples.')
    folder=Path(folder)
    pid=json.loads((folder/'project.json').read_text())['project_id']
    project=Store(folder/'studio').read(pid)
    package=Studio.package(project)
    if len(package['concepts'])<2:
        raise ValueError('The benchmark needs at least two prepared ideas.')
    with tempfile.TemporaryDirectory(prefix='presenter-latency-') as temporary:
        store=Store(temporary);store.save(copy.deepcopy(project))
        server=make_server(store,port=0,use_jev=False)
        now=[0.0];server.studio.clock=lambda:now[0]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def call(path,body=None,stage=False):
            key=server.stage_token(pid) if stage else server.access_token
            req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'X-Presenter-Key':key,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
        latencies=[]
        try:
            p=call(f'/api/projects/{pid}/control',{'action':'reflex','enabled':True})
            p=call(f'/api/projects/{pid}/control',{'action':'start'})
            entered=threading.Event();original_condition=store.condition
            def observed(project_id):entered.set();return original_condition(project_id)
            store.condition=observed
            with ThreadPoolExecutor(max_workers=1) as executor:
                for seq in range(samples):
                    target=package['concepts'][(seq+1)%len(package['concepts'])]
                    version=p['state_version'];entered.clear();now[0]+=3
                    def receive():
                        after=version
                        while True:
                            state=call(f'/api/projects/{pid}/stage?after={after}',stage=True)
                            if state['scene'] and state['scene']['concept_id']==target['id']:
                                return state
                            after=state['state_version']
                    stage=executor.submit(receive)
                    if not entered.wait(2):raise RuntimeError('Projector listener did not start.')
                    begun=time.perf_counter()
                    p=call(f'/api/projects/{pid}/transcript',{'text':target['title'],'seq':seq,'final':True,'generation':p['live']['generation']})
                    stage.result(timeout=3)
                    latencies.append((time.perf_counter()-begun)*1000)
        finally:
            server.shutdown();server.server_close();thread.join(2)
    return {'schema':'live_presenter.prepared_cue_latency.v1','samples':samples,
            'cue_to_stage_api_ms_p50':percentile(latencies,.5),'cue_to_stage_api_ms_p95':percentile(latencies,.95),
            'cue_to_stage_api_ms_max':max(latencies),'measurements_ms':latencies,
            'package_hash':project['approval']['package_hash'],
            'controller_sha256':file_hash(Path(__file__).with_name('engine.py')),
            'cue_index_sha256':file_hash(Path(__file__).with_name('reflex.py')),
            'scope':'Best-case exact prepared titles, warm cue index, eligible dwell, localhost HTTP, read-only stage capability. Excludes ASR, browser paint, display/device latency and ambiguous speech.',
            'network_adviser_used':False,'dwell_disabled':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=40)
    parser.add_argument('--out',type=Path,default=Path('artifacts/prepared_cue_latency.json'))
    args=parser.parse_args();result=benchmark(args.folder,args.samples);save(args.out,result)
    print(json.dumps({k:v for k,v in result.items() if k!='measurements_ms'},indent=2))


if __name__=='__main__':main()
