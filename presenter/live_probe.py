"""Paced WAV -> live PCM HTTP/ASR worker -> read-only stage API measurement.

This uses actual wall time, not replayed inference costs. It excludes browser
capture, browser paint and physical microphone/projector timing.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
import wave

from jev_credentials_v10 import load_jev_env
from .engine import Store, Studio
from .live_audio import SubprocessRecognizer
from .recording import audio_windows, file_hash, percentile, save, preparation_inputs
from .server import make_server


def probe(folder, output, *, asr_python, offset_s=40, duration_s=90, use_jev=False):
    if offset_s < 0 or not 1 <= duration_s <= 600 or offset_s != int(offset_s) or duration_s != int(duration_s):
        raise ValueError('Choose a nonnegative whole-second offset and 1–600 whole seconds of audio.')
    folder = Path(folder)
    source = json.loads((folder/'source.json').read_text())
    if (file_hash(folder/'audio.wav') != source['audio_sha256']
            or file_hash(folder/'preparation.md') != source['preparation_sha256']):
        raise ValueError('Audio or preparation material changed after acquisition.')
    pid = json.loads((folder/'project.json').read_text())['project_id']
    project = Store(folder/'studio').read(pid)
    Studio.package(project)
    inputs = preparation_inputs(folder,project,source)
    if use_jev and not load_jev_env():
        raise ValueError('An existing Jev credential is required for this optional condition.')
    with tempfile.TemporaryDirectory(prefix='presenter-live-probe-') as temp:
        root = Path(temp)
        wav = root/'excerpt.wav'
        with wave.open(str(folder/'audio.wav'),'rb') as original:
            original.setpos(int(offset_s*16000))
            pcm = original.readframes(int(duration_s*16000))
            if len(pcm) != int(duration_s*32000):
                raise ValueError('The requested excerpt exceeds the recording.')
            with wave.open(str(wav),'wb') as target:
                target.setparams(original.getparams()); target.writeframes(pcm)
        store = Store(root/'studio'); store.save(copy.deepcopy(project))
        server = make_server(store,port=0,use_jev=use_jev,audio_decoder=SubprocessRecognizer(asr_python))
        service = threading.Thread(target=server.serve_forever,daemon=True); service.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def call(path,body=None,stage=False):
            request = urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'X-Presenter-Key':server.stage_token(pid) if stage else server.access_token,'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=20) as response: return json.loads(response.read())
        updates, observations, sent, observer_errors = {}, [], {}, []
        stop = threading.Event(); observer = None
        try:
            p = call(f'/api/projects/{pid}/control',{'action':'start'})
            p = call(f'/api/projects/{pid}/control',{'action':'reflex','enabled':True})
            if use_jev:
                p = call(f'/api/projects/{pid}/control',{'action':'adviser','enabled':True})
            path = f'/api/projects/{pid}/audio'
            begun = time.monotonic()
            session = call(path,{'action':'start','generation':p['live']['generation']})
            while True:
                state = call(path)
                if state['status']=='ready': break
                if state['status']=='error' or time.monotonic()-begun > 35:
                    raise RuntimeError(state.get('error') or 'Recognizer startup timed out.')
                time.sleep(.05)
            warmup_s = time.monotonic()-begun
            origin = time.monotonic()
            def observe():
                version, scene = -1, None
                while not stop.is_set():
                    try:
                        stage = call(f'/api/projects/{pid}/stage?after={version}',stage=True)
                        if stop.is_set(): return
                        version = stage['state_version']
                        current = (stage.get('scene') or {}).get('id')
                        if current != scene:
                            scene = current
                            observations.append({'at':time.monotonic()-origin,'scene_id':scene,'state_version':version})
                    except Exception:
                        if not stop.is_set(): observer_errors.append('Read-only stage observer unavailable.')
                        return
            observer = threading.Thread(target=observe,daemon=True); observer.start()
            for seq,(_,end,window_start,data) in enumerate(audio_windows(wav,1,4)):
                target_time = origin+end
                while time.monotonic()<target_time:
                    time.sleep(min(.05,max(0,target_time-time.monotonic())))
                sent[seq] = {'audio_end_s':end,'window_start_s':window_start,'sent_at_s':time.monotonic()-origin}
                state = call(path,{'action':'chunk','stream_id':session['stream_id'],'generation':session['generation'],
                    'seq':seq,'end_sample':(seq+1)*16000,'pcm':base64.b64encode(data).decode(),
                    'age_s':max(0,time.monotonic()-target_time)})
                for row in state['updates']: updates[row['seq']]=row
                print(f'Live audio {end:.0f}s · {state["processed"]} processed · {state["dropped"]} skipped · {state["timeouts"]} timeouts',flush=True)
            deadline=time.monotonic()+35
            while True:
                state=call(path)
                for row in state['updates']: updates[row['seq']]=row
                if state['status']=='ready' and state['processed']+state['dropped']>=state['received']: break
                if state['status'] in {'error','stopped'} or time.monotonic()>deadline:
                    raise RuntimeError('The live worker did not finish the excerpt.')
                time.sleep(.05)
            elapsed_s=time.monotonic()-origin
            current=store.read(pid)
            rows=[updates[k] for k in sorted(updates)]
            scenes={s['id']:s for s in project['approval']['package']['scenes']}
            latencies=[r['received_to_decision_s'] for r in rows]
            switches, previous = [], project['approval']['package']['scenes'][0]['id']
            for row in rows:
                if row['scene_id'] != previous:
                    observed = next((e for e in observations if e['scene_id']==row['scene_id']
                                     and e['state_version'] >= row['state_version']),None)
                    if observed:
                        switches.append({'seq':row['seq'],'scene_id':row['scene_id'],
                            'audio_end_s':sent[row['seq']]['audio_end_s'], 'observed_at_s':observed['at'],
                            'chunk_end_to_stage_api_s':observed['at']-sent[row['seq']]['audio_end_s']})
                previous=row['scene_id']
            result={'schema':'live_presenter.paced_audio_probe.v1','source_url':source['page_url'],
                'source_audio_sha256':source['audio_sha256'],'package_hash':project['approval']['package_hash'],
                'asr':'openai-whisper tiny.en, CPU, 4 threads, 48 tokens, 2 s subprocess deadline',
                'fingerprints':{name:file_hash(Path(__file__).with_name(name)) for name in (
                    'live_audio.py','server.py','engine.py','recording.py','reflex.py','live_probe.py','selection.py')},
                'preparation_inputs':inputs,
                'capture_fingerprints':{name:file_hash(Path(__file__).with_name('web')/name) for name in (
                    'microphone.js','pcm-worklet.js','stage.js','studio.js')},
                'offset_s':offset_s,'duration_s':duration_s,'elapsed_s':elapsed_s,'model_ready_s':warmup_s,
                'use_jev':use_jev,'timing_model':'Measured wall time, one-second PCM arrivals over authenticated loopback HTTP.',
                'microphone_capture_used':False,'browser_used':False,'physical_projector_used':False,
                'metrics':{'processed':state['processed'],'dropped':state['dropped'],'rejected':state['rejected'],
                    'timeouts':state['timeouts'],'stage_observer_errors':len(observer_errors),
                    'expired_windows':state['expired'],
                    'received_to_decision_p50_s':percentile(latencies,.5),'received_to_decision_p95_s':percentile(latencies,.95),
                    'received_to_decision_max_s':max(latencies) if latencies else None,
                    'ideas_observed':len({scenes[e['scene_id']]['concept_id'] for e in observations if e['scene_id']}),
                    'visual_changes_observed':max(0,len(observations)-1)},
                'worker':{k:v for k,v in state.items() if k not in {'stream_id','generation','updates','last_seen'}},
                'rows':rows,'sent':sent,'stage_observations':observations,'observed_switch_latencies':switches,
                'final_scene_id':current['live']['current_scene_id'],
                'limitations':['WAV excerpt feeds the actual local audio API at wall-clock pace; no simulated decoder costs.',
                    'No browser capture/permission/paint or physical microphone/projector measurement.',
                    'Same-talk transcript supplied as advance preparation; no independent editorial accuracy assessment.',
                    'Shared machine; excludes up to one second of audio collection and time needed to hear a distinctive cue.']}
            save(output,result)
            return result
        finally:
            stop.set()
            try: call(f'/api/projects/{pid}/control',{'action':'stop'})
            finally:
                if observer: observer.join(2)
                server.shutdown(); server.server_close(); service.join(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--asr-python',type=Path,required=True)
    parser.add_argument('--offset-s',type=int,default=40)
    parser.add_argument('--duration-s',type=int,default=90)
    parser.add_argument('--jev',action='store_true')
    args=parser.parse_args()
    result=probe(args.folder,args.out,asr_python=args.asr_python,offset_s=args.offset_s,duration_s=args.duration_s,use_jev=args.jev)
    print(json.dumps(result['metrics'],indent=2))


if __name__=='__main__': main()
