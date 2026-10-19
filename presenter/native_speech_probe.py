"""Headless, real-paced PCM -> local ASR -> native visual probe.

The synthetic script is reference data, never a transcript input. Connected
research requires a separately running agent; the harness does not invent an
online result or pre-load a detour illustration.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import wave

from .live_audio import SubprocessRecognizer
from .native_output import VisualOutput, demo_engine
from .recording import save, file_hash
from .research_bridge import ResearchBridge
from .server import make_server


CUES = [
    (1, 'Flow rate.', 'prepared_baseline'),
    (7, 'At the high setting.', 'prepared_focus_high'),
    (14, 'Compare the low setting and the high setting.', 'prepared_comparison'),
    (23, 'Now electrical power consumption.', 'prepared_power'),
    (31, 'At the low setting.', 'prepared_focus_low'),
]
DETOUR = 'How does a heat pipe move heat using evaporation and condensation?'


def synthesize(folder, unprepared=False):
    cues=list(CUES)
    if unprepared:
        cues += [(at, DETOUR, 'unprepared_mechanism') for at in range(42, 108, 8)]
        cues += [(117, 'Back to the flow rate.', 'return_to_prepared')]
    duration=126 if unprepared else 40
    pcm=bytearray(duration*32000);script=[];previous_end=0
    for index,(at,text,condition) in enumerate(cues):
        (folder/f'cue-{index}.txt').write_text(text)
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
            '-f','lavfi','-i',f'flite=textfile=cue-{index}.txt:voice=slt',
            '-ar','16000','-ac','1','-c:a','pcm_s16le',f'cue-{index}.wav'],
            cwd=folder,check=True,capture_output=True,timeout=20)
        with wave.open(str(folder/f'cue-{index}.wav'),'rb') as wav:
            data=wav.readframes(wav.getnframes())
        start=round(at*16000)*2;end=start+len(data)
        if start<previous_end or end>len(pcm):raise ValueError('Speech clips overlap or exceed the replay.')
        pcm[start:end]=data;previous_end=end
        script.append({'start_s':at,'end_s':end/32000,'text':text,'condition':condition})
    with wave.open(str(folder/'audio.wav'),'wb') as wav:
        wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(pcm)
    return bytes(pcm),script,duration


def summarize(script, events, scenes):
    """Only changes after a cue count; the already-visible baseline never does."""
    rows=[];episode_start=None;previous_condition=None
    for index,cue in enumerate(script):
        stop=script[index+1]['start_s'] if index+1<len(script) else float('inf')
        condition=cue['condition']
        if condition!=previous_condition:episode_start=cue['start_s']
        previous_condition=condition
        def matches(event):
            scene=scenes.get(event.get('scene_id'),{})
            attention=event.get('attention') or {}
            if condition=='prepared_focus_high':return attention.get('annotation_id')=='datum_2' and scene.get('y')=='Flow_L_min'
            if condition=='prepared_focus_low':return attention.get('annotation_id')=='datum_0' and scene.get('y')=='Electrical_power_W'
            if condition=='prepared_comparison':return attention.get('target_ids')==['datum_0','datum_2'] and scene.get('y')=='Flow_L_min'
            if condition=='prepared_power':return scene.get('y')=='Electrical_power_W'
            if condition=='return_to_prepared':return scene.get('y')=='Flow_L_min'
            if condition=='unprepared_mechanism':return scene.get('kind') in {'image','annotated_image'} and bool(scene.get('web_source'))
            return False
        event=next((e for e in events if cue['start_s']<=e['at_s']<stop and matches(e)),None)
        first_pixels=event.get('first_changed_pixels_at_s') if event else None
        rows.append({**cue,'changed_visual_observed':first_pixels is not None,
            'first_changed_pixels_at_s':first_pixels,
            'cue_start_to_pixels_s':first_pixels-cue['start_s'] if first_pixels is not None else None,
            'cue_end_to_pixels_s':first_pixels-cue['end_s'] if first_pixels is not None else None,
            'episode_start_to_pixels_s':first_pixels-episode_start if first_pixels is not None else None,
            'baseline_excluded':condition=='prepared_baseline'})
    return rows


def run(folder, asr_python, *, unprepared=False, stabilize_text=False):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from .native import qt_types
    from PySide6.QtGui import QImage
    QApplication,Surface,_=qt_types()
    code_names=('native_speech_probe.py','native.py','native_output.py','engine.py',
                'live_audio.py','research.py','research_bridge.py','explanation.py','speech_stability.py')
    code_fingerprints={name:file_hash(Path(__file__).with_name(name)) for name in code_names}
    folder=folder.absolute();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (folder/'started.json').exists():raise ValueError('Use a new attempt directory.')
    save(folder/'started.json',{'started_at':time.time()})
    pcm,script,duration=synthesize(folder,unprepared)
    save(folder/'reference-script.json',script)
    store,_,pid=demo_engine(folder/'studio',brief='Explain computer cooling, measured liquid circulation and electrical power, and how heat moves from a processor to the surrounding air.')
    prepared=store.read(pid)
    if 'heat pipe' in json.dumps(prepared['sources']).lower():raise ValueError('Detour leaked into preparation.')
    bridge=ResearchBridge(timeout_s=55) if unprepared else None
    server=make_server(store,port=0,use_jev=False,dwell_s=0,
        research_backend=bridge,audio_decoder=SubprocessRecognizer(asr_python),stabilize_text=stabilize_text)
    service=threading.Thread(target=server.serve_forever,daemon=True);service.start()
    save(folder/'connection.json',{'base_url':f'http://127.0.0.1:{server.server_port}',
        'operator_key':server.access_token,'project_id':pid})
    app=QApplication.instance() or QApplication([])
    surface=Surface(animate=True);surface.resize(1280,720);surface.show()
    output=VisualOutput();events=[];scenes={};sent=[];errors=[];stopping=threading.Event()
    encoder=feeder=log=None
    try:
        studio=server.studio
        p=studio.control(pid,'start');p=studio.control(pid,'reflex',enabled=True)
        if unprepared:p=studio.control(pid,'research',enabled=True)
        session=server.audio.start(pid,p['live']['generation'])
        warmup=time.monotonic()
        while server.audio.snapshot(pid)['status']!='ready':
            if server.audio.snapshot(pid)['status']=='error' or time.monotonic()-warmup>40:
                raise RuntimeError('Local ASR failed to warm up.')
            app.processEvents();time.sleep(.02)
        asr_warmup_s=time.monotonic()-warmup
        fps=24;origin=time.monotonic();perf_origin=time.perf_counter();wall_origin=time.time()
        print(json.dumps({'status':'replaying','duration_s':duration,'asr_warmup_s':asr_warmup_s}),flush=True)
        def feed():
            try:
                for seq in range(duration):
                    if stopping.is_set():return
                    target=origin+seq+1
                    while time.monotonic()<target:
                        if stopping.wait(min(.02,max(0,target-time.monotonic()))):return
                    age=max(0,time.monotonic()-target)
                    server.audio.submit(pid,{'stream_id':session['stream_id'],'generation':session['generation'],
                        'seq':seq,'end_sample':(seq+1)*16000,'age_s':age,
                        'pcm':base64.b64encode(pcm[max(0,seq-3)*32000:(seq+1)*32000]).decode()})
                    sent.append({'seq':seq,'at_s':time.monotonic()-origin,'capture_age_s':age})
            except Exception as error:errors.append(type(error).__name__+': '+str(error))
        feeder=threading.Thread(target=feed,daemon=True);feeder.start()
        command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pixel_format','rgba','-video_size','1280x720','-framerate',str(fps),
            '-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',str(folder/'silent.mp4')]
        log=(folder/'encoder.log').open('wb')
        encoder=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        frame=0;last_pixels=bytes(1280*720*4);last_digest=None;active_event=None;poll_at=0;render_at=0
        while time.monotonic()-origin<duration+3:
            elapsed=time.monotonic()-origin
            if elapsed>=poll_at:
                p=store.read(pid);poll_at=elapsed+.02
                if output.accept(p):
                    active_event={'at_s':elapsed,'scene_id':(output.scene or {}).get('id'),
                        'attention':output.attention,'state_version':p['state_version'],
                        'decision':p['live']['decision'],'last_transcript':p['live']['transcript'][-1:]}
                    events.append(active_event)
                    if output.scene:scenes[output.scene['id']]=output.scene
                    surface.present(output)
            app.processEvents()
            if elapsed>=render_at:
                image=surface.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                pixels=bytes(image.constBits());captured=time.monotonic()-origin
                # Frames preceding this capture keep previous pixels. New pixels
                # are assigned to the next frame boundary, never backdated.
                boundary=math.ceil(captured*fps)
                while frame<boundary:
                    encoder.stdin.write(last_pixels);frame+=1
                digest=hashlib.sha256(pixels).hexdigest()
                if active_event and 'first_changed_pixels_at_s' not in active_event and digest!=last_digest:
                    active_event.update(first_changed_pixels_at_s=captured,video_first_pixels_s=frame/fps,
                        pixels_sha256=digest,paint_sample=dict(surface.samples[-1]) if surface.samples else None)
                    image.save(str(folder/f'visual-{len(events):03}.png'))
                last_pixels,last_digest=pixels,digest;render_at=captured+1/fps
            time.sleep(.003)
        feeder.join(3)
        encoder.stdin.close();encoder.wait(timeout=30);log.close()
        if encoder.returncode:raise RuntimeError('Native frame encoder failed.')
        state=server.audio.snapshot(pid);p=store.read(pid)
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
            '-i',str(folder/'silent.mp4'),'-i',str(folder/'audio.wav'),'-c:v','copy','-c:a','aac',
            '-movflags','+faststart',str(folder/'speech-visual.mp4')],check=True,timeout=30)
        rows=state.pop('updates');state={k:v for k,v in state.items() if k not in {'stream_id','generation','last_seen'}}
        report={'schema':'live_presenter.native_speech_probe.v1','browser_used':False,'visible_window_opened':False,
            'desktop_captured':False,'physical_microphone_used':False,'physical_display_measured':False,
            'asr':'local tiny.en, one thread, 4s rolling past-only windows, 1s arrivals, 2s expiry',
            'experimental_realtimestt_stabilizer':stabilize_text,
            'asr_warmup_s':asr_warmup_s,'wall_origin':wall_origin,'monotonic_origin':origin,'perf_origin':perf_origin,
            'source_sha256':prepared['sources'][0]['sha256'],'audio_sha256':file_hash(folder/'audio.wav'),
            'approved_package_hash':prepared['approval']['package_hash'],
            'approval_unchanged':p['approval']['package_hash']==prepared['approval']['package_hash'],
            'future_script_supplied_to_preparation_or_follower':False,'unprepared_topic_in_supplied_material':False,
            'research_mode':'connected AI agent with authenticated pixel-review attestation' if unprepared else 'disabled',
            'speech':'Development-authored synthetic flite slt; not a human or blinded holdout.',
            'stage_dwell_s':0,'fps':fps,'frame_count':frame,'elapsed_s':time.monotonic()-origin,
            'worker':state,'asr_updates':rows,'sent':sent,'visual_events':events,'scenes':scenes,
            'cue_results':summarize(script,events,scenes),'research_history':p.get('research_history',[]),
            'final_research':p['live'].get('research',{}),'errors':errors,
            'limitations':['Offscreen paint/frame timings exclude physical microphone, projector and scanout.',
                'A rendered baseline is excluded from speech-responsive success.',
                'Connected-agent image review is attested, not independently verified by the app.',
                'No independent audience learning or visual-quality evaluation.'],
            'code_fingerprints':code_fingerprints,
            'code_changed_during_run':any(file_hash(Path(__file__).with_name(name))!=digest
                for name,digest in code_fingerprints.items())}
        save(folder/'report.json',report)
        print(json.dumps({'report':str(folder/'report.json'),'worker':state,
            'cue_results':report['cue_results']}),flush=True)
        return report
    finally:
        stopping.set()
        if feeder:feeder.join(3)
        if encoder and encoder.poll() is None:encoder.kill();encoder.wait(timeout=5)
        if log:log.close()
        surface.close();server.shutdown();server.server_close();service.join(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--asr-python',type=Path,default=Path('.venv-asr/bin/python'))
    parser.add_argument('--unprepared',action='store_true')
    parser.add_argument('--stabilize-text',action='store_true',help='Evaluate the optional RealtimeSTT stable-text adapter')
    args=parser.parse_args();run(args.out_dir,args.asr_python,unprepared=args.unprepared,stabilize_text=args.stabilize_text)


if __name__=='__main__':main()
