"""Causal typed early-mention/rephrasing probe; no audio or browser measurement."""
import argparse
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

from jev_credentials_v10 import load_jev_env
from .engine import Store
from .recording import file_hash,save
from .research import ResearchProcess
from .server import make_server


STEPS=[
    ('early_mention','Later I will compare heat pipes using evaporation and condensation with this pumped water loop.'),
    ('prepared_return','A pump circulates liquid through a hot component and radiator.'),
    ('rephrased_question','What about heat pipes using evaporation and condensation in a pumped water loop?'),
    ('prepared_return_again','A pump circulates liquid through a hot component and radiator.'),
    ('wrong_domain_control','What about heat pipes as loaves of sourdough bread in this cooling loop?'),
]


def run(folder):
    folder=Path(folder).absolute();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (folder/'started.json').exists():raise ValueError('Use a new output directory; failed attempts are retained.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    save(folder/'started.json',{'commit':commit,'steps':STEPS})
    load_jev_env()
    server=make_server(Store(folder/'studio'),port=0,use_jev=False,
        research_backend=ResearchProcess(command=['python3','-m','presenter.web_research']))
    service=threading.Thread(target=server.serve_forever,daemon=True);service.start()
    pid=None;stop=threading.Event();events=[];scenes={};errors=[];observer=None
    def call(path,body=None,stage=False):
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Presenter-Key':server.stage_token(pid) if stage else server.access_token,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=20) as response:return json.loads(response.read())
    def wait(predicate,seconds=35):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            p=call(url)
            if predicate(p):return p
            time.sleep(.04)
        return call(url)
    try:
        p=call('/api/projects',{'title':'A cooling loop','brief':'Explain heat transfer and alternatives to pumped liquid cooling.',
            'audience':'Engineering students','provider':'outline',
            'sources':[{'name':'Cooling notes.md','text':'A pump circulates liquid through a hot component and radiator.'}]})
        pid=p['id'];url='/api/projects/'+pid
        p=wait(lambda p:p['job']['status']!='working')
        if p['job']['status']!='ready':raise RuntimeError('Preparation unavailable.')
        p=call(url+'/approve',{'revision':p['revision'],'reviewed':True});approval=p['approval']['package_hash']
        save(folder/'prepared-project.json',p)
        for action in ('start','reflex','research'):p=call(url+'/control',{'action':action,'enabled':True})
        origin=time.monotonic()
        def observe():
            version=-1;previous=None
            while not stop.is_set():
                try:
                    state=call(url+'/stage?after='+str(version),stage=True);version=state['state_version']
                    scene=state.get('scene');key=scene['id'] if scene else None
                    if key!=previous:
                        events.append({'at_s':time.monotonic()-origin,'scene_id':key})
                        if scene:scenes[key]=scene
                        previous=key
                except Exception:
                    if not stop.is_set():errors.append('Stage observer failed.')
                    return
        observer=threading.Thread(target=observe,daemon=True);observer.start();observations=[]
        for seq,(name,text) in enumerate(STEPS):
            if seq:time.sleep(2.7)  # Respect the ordinary stage dwell, not force-show.
            p=call(url);submitted=time.monotonic()-origin
            p=call(url+'/transcript',{'text':text,'seq':seq,'final':True,'generation':p['live']['generation']})
            p=wait(lambda p:p['live'].get('research',{}).get('status') not in {'queued','searching','enriching'})
            time.sleep(.1)
            observations.append({'id':name,'text':text,'submitted_at_s':submitted,'settled_at_s':time.monotonic()-origin,
                'research':p['live'].get('research',{}),'stage_scene_id':call(url+'/stage',stage=True).get('scene',{}).get('id')})
            print(json.dumps({'step':name,'status':observations[-1]['research'].get('status'),
                'cache_kind':observations[-1]['research'].get('cache_kind')}),flush=True)
        p=call(url)
        assert p['approval']['package_hash']==approval
        result={'schema':'live_presenter.warm_research_probe.v1','git_commit':commit,
            'code_fingerprints':{n:file_hash(Path(__file__).with_name(n)) for n in ('research.py','research_sources.py','web_research.py','warm_research_demo.py')},
            'prepared_package_hash':approval,'approval_unchanged':True,'steps':observations,
            'stage_events':events,'scenes':scenes,'research_history':p.get('research_history',[]),'observer_errors':errors,
            'supplied_future_speech_to_preparation':False,'injected_online_results':0,'browser_used':False,'physical_microphone_used':False,
            'limitations':['Typed development script, not speech/audio or a held-out test.',
                'Early mention is a real lookup, not free anticipation of an unmentioned subject.',
                'Fresh revalidation is a model judgment, not independent editorial review.',
                'Records stage API observations, excluding browser paint and hardware.']}
        save(folder/'result.json',result);return result
    finally:
        stop.set()
        if pid:
            try:call('/api/projects/'+pid+'/control',{'action':'stop'})
            except Exception:pass
        if observer:observer.join(2)
        server.shutdown();server.server_close();service.join(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();run(args.out_dir)


if __name__=='__main__':main()
