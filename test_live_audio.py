"""Real HTTP/worker interruption checks; no Torch, model or provider needed."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from presenter.engine import Conflict, Store
from presenter.live_audio import SubprocessRecognizer, repeated_window_tail
from presenter.server import make_server
from test_prepared_reflex import example


class Decoder:
    ready = True
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.block = False
    def ensure_ready(self): self.ready = True
    def recognize(self, pcm):
        self.calls.append(pcm[0])
        self.entered.set()
        if self.block: self.release.wait(2)
        return {'text': 'Battery storage' if pcm[0] == 1 else 'Ocean transport', 'rejection': None}
    def reset(self): self.ready = False; self.release.set()
    def close(self): self.reset()


class LiveAudioTests(unittest.TestCase):
    def test_overlapping_suffix_does_not_replay_but_later_or_corrected_speech_does(self):
        previous='Compare the low setting and the high setting.'
        self.assertTrue(repeated_window_tail(previous,'the high setting',3))
        self.assertTrue(repeated_window_tail(previous,previous,1))
        self.assertFalse(repeated_window_tail(previous,'the high setting',5))
        self.assertFalse(repeated_window_tail(previous,'Actually the high setting',2))
        self.assertFalse(repeated_window_tail(previous,'At the low setting',2))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        source,plan = example()
        class Planner:
            def prepare(self,p): return copy.deepcopy(plan)
        self.decoder = Decoder()
        self.server = make_server(self.store,port=0,planner=Planner(),use_jev=False,dwell_s=0,audio_decoder=self.decoder)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.studio, self.audio = self.server.studio, self.server.audio
        p = self.store.create(title=source['title'],brief='Explain',audience='Students',sources=source['sources'])
        p = self.studio.prepare(p['id'],background=False)
        p = self.studio.approve(p['id'],p['revision'],True)
        p = self.studio.control(p['id'],'start')
        self.p = self.studio.control(p['id'],'reflex',enabled=True)
        self.pid = p['id']; self.path = f'/api/projects/{self.pid}/audio'
    def tearDown(self):
        self.decoder.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        self.temp.cleanup()
    def call(self,path,body=None,key=None):
        request = urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Presenter-Key':key or self.server.access_token,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=3) as response: return json.loads(response.read())
    def start(self):
        self.session = self.call(self.path,{'action':'start','generation':self.p['live']['generation']})
        return self.session
    def packet(self,seq=0,value=1):
        return {'action':'chunk','stream_id':self.session['stream_id'],'generation':self.session['generation'],
                'seq':seq,'end_sample':(seq+1)*16000,
                'pcm':base64.b64encode(bytes([value,0])*min((seq+1)*16000,64000)).decode()}
    def until(self,predicate):
        deadline = time.monotonic()+2
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.005)
        self.fail('Audio worker did not reach the expected state.')

    def test_http_pcm_to_approved_read_only_stage_and_no_pcm_on_disk(self):
        original = self.p['live']['current_scene_id']; self.start()
        self.call(self.path,self.packet())
        self.until(lambda:self.audio.snapshot(self.pid)['processed']==1)
        stage = self.call(f'/api/projects/{self.pid}/stage',key=self.server.stage_token(self.pid))
        self.assertNotEqual(stage['scene']['id'],original)
        self.assertEqual(stage['scene']['concept_id'],self.p['plan']['concepts'][1]['id'])
        self.assertNotIn('updates',stage); self.assertNotIn('transcript',stage)
        snapshot = self.call(self.path)
        self.assertEqual(snapshot['updates'][0]['seq'],0)
        self.assertNotIn('pending',snapshot)
        self.assertEqual([p.suffix for p in Path(self.temp.name).glob('*') if p.name not in {'.operator-key','.server.lock'}],['.json'])
        saved=self.store.read(self.pid)
        self.assertEqual(saved['live']['transcript'][-1]['text'],'Battery storage')
        self.assertNotIn('pcm',saved['live'])

    def test_single_pending_slot_coalesces_to_latest_pcm_window(self):
        self.decoder.block = True; self.start()
        self.call(self.path,self.packet(0,1)); self.assertTrue(self.decoder.entered.wait(1))
        self.call(self.path,self.packet(1,2)); self.call(self.path,self.packet(2,3))
        self.decoder.release.set()
        self.until(lambda:self.audio.snapshot(self.pid)['processed']==2)
        state = self.audio.snapshot(self.pid)
        self.assertEqual(self.decoder.calls,[1,3])
        self.assertEqual([row['seq'] for row in state['updates']],[0,2])
        self.assertEqual(state['dropped'],1)

    def test_stopping_microphone_invalidates_already_decoding_audio(self):
        self.decoder.block = True; self.start()
        self.call(self.path,self.packet()); self.assertTrue(self.decoder.entered.wait(1))
        self.call(self.path,{'action':'stop','stream_id':self.session['stream_id']})
        self.until(lambda:self.audio.snapshot(self.pid)['dropped']>=1)
        p=self.store.read(self.pid)
        self.assertNotEqual(p['live']['generation'],self.session['generation'])
        self.assertEqual(p['live']['current_scene_id'],self.p['live']['current_scene_id'])
        self.assertEqual(p['live']['transcript'],[])

    def test_manual_control_cancels_audio_without_overwriting_the_selected_scene(self):
        self.decoder.block=True; self.start()
        self.call(self.path,self.packet()); self.assertTrue(self.decoder.entered.wait(1))
        scene=self.p['plan']['scenes'][-1]['id']
        controlled=self.call(f'/api/projects/{self.pid}/control',{'action':'show','scene_id':scene})
        self.until(lambda:self.audio.snapshot(self.pid)['dropped']>=1)
        self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'],scene)
        self.assertEqual(self.store.read(self.pid)['live']['generation'],controlled['live']['generation'])

    def test_stale_inflight_and_pending_audio_are_both_discarded(self):
        clock=[0.0]; self.audio.clock=lambda:clock[0]
        self.decoder.block=True; self.start()
        self.call(self.path,self.packet()); self.assertTrue(self.decoder.entered.wait(1))
        self.call(self.path,self.packet(1,2))
        clock[0]=2.1; self.decoder.release.set()
        self.until(lambda:self.audio.snapshot(self.pid)['dropped']==2)
        self.assertEqual(self.decoder.calls,[1])
        self.assertEqual(self.store.read(self.pid)['live']['transcript'],[])

    def test_decoder_timeout_recovers_for_a_fresh_window_without_reusing_old_text(self):
        original=self.decoder.recognize
        attempted=[]
        def recognize(pcm):
            attempted.append(pcm[0])
            if len(attempted)==1:
                self.decoder.ready=False
                raise TimeoutError('Measured decoder deadline')
            return original(pcm)
        self.decoder.recognize=recognize
        self.start(); self.call(self.path,self.packet())
        self.until(lambda:self.audio.snapshot(self.pid)['timeouts']==1)
        self.call(self.path,self.packet(1,2))
        self.until(lambda:self.audio.snapshot(self.pid)['processed']==1)
        state=self.audio.snapshot(self.pid)
        self.assertEqual(state['dropped'],1)
        self.assertEqual([r['seq'] for r in state['updates']],[1])
        self.assertEqual(self.store.read(self.pid)['live']['transcript'][-1]['text'],'Ocean transport')

    def test_adviser_cannot_commit_after_audio_deadline_and_sequence_is_allocated_atomically(self):
        now=[100.0]; self.studio.clock=lambda:now[0]
        self.studio.control(self.pid,'reflex',enabled=False)
        p=self.studio.control(self.pid,'adviser',enabled=True)
        target=self.p['plan']['scenes'][1]['id']
        def slow_advice(*args):
            now[0]=102
            return {'scene_id':target,'confidence':1}
        self.studio.live_assessor=slow_advice
        p=self.studio.transcript(self.pid,'Battery storage',None,generation=p['live']['generation'],expires_at=101)
        self.assertEqual(p['live']['last_seq'],0)
        self.assertEqual(p['live']['current_scene_id'],self.p['live']['current_scene_id'])
        self.assertIn('expired',p['live']['decision']['reason'])

    def test_invalid_audio_generation_sequence_length_and_future_sample_rejected(self):
        self.start()
        for field,value in [('generation',None),('seq',True),('end_sample',32000),('end_sample',16000.0),
                            ('pcm','AA=='),('age_s',2.1),('age_s',float('nan'))]:
            body=self.packet(); body[field]=value
            with self.assertRaises(urllib.error.HTTPError) as caught: self.call(self.path,body)
            self.assertIn(caught.exception.code,(400,409))
        self.call(self.path,self.packet())
        with self.assertRaises(urllib.error.HTTPError) as caught: self.call(self.path,self.packet())
        self.assertEqual(caught.exception.code,409)

    def test_deadline_adviser_returns_without_waiting_for_late_network_call(self):
        from unittest.mock import patch
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set(); release.wait(2)
            return {'scene_id':self.p['plan']['scenes'][1]['id'],'confidence':1}
        self.studio.live_assessor=slow
        p=self.studio.control(self.pid,'adviser',enabled=True)
        choice={'scene_id':self.p['plan']['scenes'][1]['id'],'score':.7,'confirmed':False,
                'supported_concepts':[self.p['plan']['concepts'][1]['id']],'reflex_ready':False}
        try:
            with patch.object(self.studio.cue_index(p),'match',return_value=choice):
                begun=time.monotonic()
                result=self.studio.transcript(self.pid,'Ambiguous supported idea',None,
                    generation=p['live']['generation'],expires_at=time.time()+.15)
                self.assertLess(time.monotonic()-begun,.7)
            self.assertTrue(entered.is_set())
            self.assertEqual(result['live']['current_scene_id'],self.p['live']['current_scene_id'])
            self.assertIn('error',result['live']['recommendation']['advice'])
            # The same guarded adviser cannot accumulate new background calls.
            with self.assertRaises(TimeoutError):
                self.studio.deadline_adviser.ask(slow,{},'another idea',.1)
            selected=self.p['plan']['scenes'][-1]['id']
            self.studio.control(self.pid,'show',scene_id=selected)
            release.set()
            self.until(lambda:not self.studio.deadline_adviser.busy)
            self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'],selected)
        finally: release.set()

    def test_projector_capability_cannot_inspect_or_submit_microphone_audio(self):
        self.start(); key=self.server.stage_token(self.pid)
        for body in (None,self.packet(),{'action':'stop','stream_id':self.session['stream_id']}):
            with self.assertRaises(urllib.error.HTTPError) as caught: self.call(self.path,body,key)
            self.assertEqual(caught.exception.code,403)

    def test_idle_capture_expires_and_old_stop_cannot_cancel_new_capture(self):
        clock=[0.0]; self.audio.clock=lambda:clock[0]
        old=self.start()
        self.until(lambda:self.audio.snapshot(self.pid)['status']=='ready')
        clock[0]=6
        self.until(lambda:self.audio.snapshot(self.pid)['status']=='stopped')
        self.p=self.store.read(self.pid); new=self.start()
        with self.assertRaises(Conflict): self.audio.stop(self.pid,old['stream_id'])
        self.assertEqual(self.audio.snapshot(self.pid)['stream_id'],new['stream_id'])


class DecoderDeadlineTests(unittest.TestCase):
    def test_deadline_kills_owned_decoder_even_when_it_stops_reading_input(self):
        process=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(10)'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        decoder=SubprocessRecognizer(sys.executable,timeout_s=.15)
        decoder.process,decoder.ready=process,True
        try:
            begun=time.monotonic()
            with self.assertRaises(TimeoutError):decoder.recognize(b'\x00\x00'*64000)
            self.assertLess(time.monotonic()-begun,1)
            self.assertIsNotNone(process.poll())
            self.assertFalse(decoder.ready)
        finally:decoder.close()


if __name__=='__main__':unittest.main()
