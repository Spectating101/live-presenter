"""Reproducible paced synthetic-speech rehearsal, with hidden-from-prep detours.

Measures the actual PCM/ASR/research/stage APIs. The exported movie reconstructs
API observations; it is not a screen recording or a physical microphone test.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
import wave

from jev_credentials_v10 import load_jev_env
from .engine import Store
from .live_audio import SubprocessRecognizer
from .recording import audio_windows, file_hash, save
from .server import make_server


TITLE='Computer water cooling pump and radiator'
BRIEF='Explain how a pumped water loop moves heat from a computer processor to a radiator. The audience is new to the topic.'
NOTES='A pump circulates liquid through a hot component and radiator. The radiator transfers heat to the surrounding air.'
SEGMENTS=[
    ('prepared_loop', 'prepared', '''Let us start with the water cooling loop. A pump circulates water through a hot component and then through a radiator. The cooling pump keeps the water moving. At the radiator, heat moves into the surrounding air. The radiator and the water pump are the two parts I want you to keep in mind. A water cooling loop carries heat away from the processor.'''),
    ('heat_pipe_detour', 'unprepared_related', '''Now, what about heat pipes instead of this pumped cooling loop? How does a heat pipe move heat using evaporation and condensation? A heat pipe sounds different from a water pump. Can we find a source explaining the heat pipe mechanism? I want to understand evaporation and condensation inside a heat pipe. We can keep talking about heat pipes while the system looks for supporting material. What happens inside a heat pipe when the working fluid evaporates? How does the vapor condense at the cooler end of a heat pipe?'''),
    ('thermoelectric_detour', 'unprepared_related', '''Let us take another direction. What about thermoelectric cooling instead of a water cooling pump? How does a thermoelectric cooler move heat when electrical current passes through it? Can we find a source explaining thermoelectric cooling? A thermoelectric cooler uses an electrical effect, so I want supporting material about thermoelectric cooling. We should check a source before making a stronger claim. How does the thermoelectric cooling effect work, and what does a thermoelectric cooler actually do?'''),
    ('unrelated_control', 'unrelated', '''Now for a deliberately unrelated question. How do sourdough bread starters ferment flour? What about baking sourdough bread and feeding a sourdough starter? This is a different subject from our engineering presentation. Sourdough fermentation and baking bread are outside the subject of this talk. We should not replace the engineering visual with a bread recipe.'''),
    ('return_to_loop', 'prepared', '''Back to our water cooling loop. The cooling pump circulates water through the hot component and the radiator. The radiator transfers heat to surrounding air. Remember the water pump, the radiator, and the water circulation. These are the prepared ideas in our cooling loop. We can now finish the explanation with the pump and radiator.'''),
]


def synthesize(folder):
    """Local FFmpeg/libflite, without sending the script to an online service."""
    rows=[];offset=0;frames=[]
    for index,(name,kind,text) in enumerate(SEGMENTS):
        source=folder/f'speech-{index}.txt';source.write_text(text)
        audio=folder/f'speech-{index}.wav'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',
            f'flite=textfile=speech-{index}.txt:voice=slt','-ar','16000','-ac','1','-c:a','pcm_s16le',audio.name],
            cwd=folder,check=True,capture_output=True,timeout=30)
        with wave.open(str(audio),'rb') as wav:
            data=wav.readframes(wav.getnframes());duration=wav.getnframes()/wav.getframerate()
        frames.append(data);rows.append({'id':name,'condition':kind,'text':text,'start_s':offset,'end_s':offset+duration})
        offset+=duration
    with wave.open(str(folder/'audio.wav'),'wb') as wav:
        wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b''.join(frames))
    return rows


def run(folder,asr_python):
    folder=folder.absolute();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if any((folder/name).exists() for name in ('result.json','started.json')):
        raise ValueError('Use a new output directory; recorded attempts are preserved.')
    save(folder/'started.json',{'started_at':time.time(),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})
    script=synthesize(folder);save(folder/'withheld-script.json',script)
    load_jev_env()
    server=make_server(Store(folder/'studio'),port=0,use_jev=False,research_web=True,
                       audio_decoder=SubprocessRecognizer(asr_python))
    service=threading.Thread(target=server.serve_forever,daemon=True);service.start()
    pid=None
    def call(path,body=None,stage=False):
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Presenter-Key':server.stage_token(pid) if stage else server.access_token,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=20) as response:return json.loads(response.read())
    stop=threading.Event();observer=None;events=[];scenes={};observer_errors=[];rows={};sent={};samples=[]
    try:
        begun=time.monotonic()
        p=call('/api/projects',{'title':TITLE,'brief':BRIEF,'audience':'Engineering students','provider':'outline',
                              'sources':[{'name':'Pump notes.md','text':NOTES}]})
        pid=p['id'];url='/api/projects/'+pid
        while p['job']['status']=='working' and time.monotonic()-begun<40:
            time.sleep(.05);p=call(url)
        if p['job']['status']!='ready':raise RuntimeError('Preparation did not finish.')
        preparation_s=time.monotonic()-begun
        save(folder/'prepared-project.json',p)
        prepared_text=' '.join(unit['text'] for source in p['sources'] for unit in source['units']).lower()
        withheld_terms=['heat pipe','thermoelectric','sourdough']
        if any(term in prepared_text for term in withheld_terms):
            raise ValueError('A detour appeared in preparation; this attempt cannot claim it was unprepared.')
        p=call(url+'/approve',{'revision':p['revision'],'reviewed':True});approval=p['approval']['package_hash']
        p=call(url+'/control',{'action':'start'})
        p=call(url+'/control',{'action':'reflex','enabled':True})
        p=call(url+'/control',{'action':'research','enabled':True})
        session=call(url+'/audio',{'action':'start','generation':p['live']['generation']})
        warmup=time.monotonic()
        while True:
            state=call(url+'/audio')
            if state['status']=='ready':break
            if state['status']=='error' or time.monotonic()-warmup>35:raise RuntimeError('ASR startup failed.')
            time.sleep(.05)
        origin=time.monotonic();wall_origin=time.time()
        def observe():
            version=-1;previous=None
            while not stop.is_set():
                try:
                    stage=call(url+'/stage?after='+str(version),stage=True);version=stage['state_version']
                    if stop.is_set():return
                    scene=stage.get('scene');key=scene['id'] if scene else None
                    if key!=previous:
                        events.append({'at_s':time.monotonic()-origin,'scene_id':key,'state_version':version})
                        if scene:scenes[key]=scene
                        previous=key
                except Exception:
                    if not stop.is_set():observer_errors.append('Stage observer failed.')
                    return
        observer=threading.Thread(target=observe,daemon=True);observer.start()
        wav=folder/'audio.wav'
        for seq,(_,end,start,data) in enumerate(audio_windows(wav,1,4)):
            target=origin+end
            while time.monotonic()<target:time.sleep(min(.04,max(0,target-time.monotonic())))
            sent[seq]={'audio_end_s':end,'window_start_s':start,'sent_at_s':time.monotonic()-origin}
            state=call(url+'/audio',{'action':'chunk','stream_id':session['stream_id'],'generation':session['generation'],
                'seq':seq,'end_sample':(seq+1)*16000,'pcm':base64.b64encode(data).decode(),'age_s':max(0,time.monotonic()-target)})
            for row in state['updates']:rows[row['seq']]=row
            p=call(url);research=p['live'].get('research',{})
            samples.append({'at_s':time.monotonic()-origin,'status':research.get('status'),'request_id':research.get('request_id'),
                'query':research.get('query'),'request_count':research.get('request_count',0),'scene_id':(p['live'].get('research_scene') or {}).get('id')})
            if seq%10==0:print(json.dumps({'audio_s':end,'processed':state['processed'],'research_status':research.get('status')}),flush=True)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            state=call(url+'/audio')
            for row in state['updates']:rows[row['seq']]=row
            if state['status']=='ready' and state['processed']+state['dropped']>=state['received']:break
            time.sleep(.05)
        p=call(url)
        assert p['approval']['package_hash']==approval
        result={'schema':'live_presenter.researched_rehearsal.v1','git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'code_fingerprints':{name:file_hash(Path(__file__).with_name(name)) for name in ('engine.py','planning.py','research.py','research_sources.py','web_research.py','preparation_research.py','live_audio.py','server.py','researched_demo.py')},
            'input':{'title':TITLE,'brief':BRIEF,'supplied_notes':NOTES,'supplied_notes_sha256':hashlib.sha256(NOTES.encode()).hexdigest(),
                'future_speech_supplied_to_preparation':False,'withheld_terms_absent':withheld_terms,'audio_sha256':file_hash(wav),
                'speech':'FFmpeg libflite slt synthetic English speech; separately synthesized paragraphs concatenated without added pauses'},
            'preparation_s':preparation_s,'preparation_research':p.get('preparation_research'),'prepared_package_hash':approval,
            'prepared_source_count':len(p['sources']),'prepared_scene_count':len(p['approval']['package']['scenes']),
            'approval_unchanged_during_rehearsal':True,'wall_origin':wall_origin,'elapsed_s':time.monotonic()-origin,
            'script':script,'sent':sent,'asr_updates':[rows[k] for k in sorted(rows)],'stage_events':events,'scenes':scenes,
            'research_history':p.get('research_history',[]),'research_samples':samples,
            'worker':{k:v for k,v in state.items() if k not in {'stream_id','generation','updates','last_seen'}},
            'observer_errors':observer_errors,'browser_used':False,'physical_microphone_used':False,'independent_quality_review':False,
            'operator_interventions_during_speech':0,'online_results_injected_by_operator':0,'stage_dwell_s':2.5,
            'limitations':['Synthetic and development-authored script, not a human or independent holdout.',
                'Real paced PCM HTTP, local tiny.en ASR, unattended web requests and stage API; excludes browser paint and physical microphone/projector.',
                'Source outline preparation is extractive; a functioning generative preparation conversation was unavailable because Copilot accounts were quota-blocked.',
                'External search caches may already contain development queries; this is not a cold-provider service benchmark.']}
        save(folder/'result.json',result)
        return result
    finally:
        stop.set()
        if pid:
            try:call('/api/projects/'+pid+'/control',{'action':'stop'})
            except Exception:pass
        if observer:observer.join(2)
        server.shutdown();server.server_close();service.join(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--asr-python',type=Path,default=Path('.venv-asr/bin/python'))
    args=parser.parse_args()
    result=run(args.out_dir,args.asr_python)
    print(json.dumps({'elapsed_s':result['elapsed_s'],'stage_changes':len(result['stage_events']),
                     'research_completions':len(result['research_history']),'result':str(args.out_dir/'result.json')}),flush=True)


if __name__=='__main__':main()
