"""Offline checks for bounded audio input, replay timing and comparison math."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from presenter.engine import Conflict, Store, Studio
from presenter.materials import ingest
from presenter.recording import audio_chunks, audio_windows, build_report, file_hash, recording_store, replay, save, score_replay, validate_chunks
from research_evidence_v10 import json_hash


def write_wav(path, seconds=3):
    with wave.open(str(path), 'wb') as file:
        file.setparams((1,2,16000,0,'NONE','not compressed'))
        file.writeframes(b'\x01\x00' * (seconds * 16000))


class RecordedTalkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, approve=True):
        folder = self.folder
        write_wav(folder / 'audio.wav')
        (folder / 'preparation.md').write_text('# Reservoir\n\nThe reservoir supplies liquid to a pump.\n\n# Radiator\n\nThe radiator releases absorbed heat into the surrounding air.')
        save(folder / 'source.json', {'title':'Loop','preparation_sha256':file_hash(folder / 'preparation.md'),
                                     'audio_sha256':file_hash(folder / 'audio.wav')})
        store = Store(folder / 'studio')
        studio = Studio(store)
        p = store.create(title='Loop',brief='Explain the loop',audience='Students',provider='outline',
                         sources=[ingest('Supplied talk material.md',(folder / 'preparation.md').read_bytes())])
        p = studio.prepare(p['id'],background=False)
        if approve:
            p = studio.approve(p['id'],p['revision'],True)
        save(folder / 'project.json',{'project_id':p['id']})
        asr = {'schema':'live_presenter.chunk_asr.v1','complete':True,
               'audio_sha256':file_hash(folder / 'audio.wav'),'future_audio_visible':False,'official_captions_visible':False,
               'chunks':[{'start':0,'end':1,'asr_s':1.5,'text':'Radiator'},
                         {'start':1,'end':2,'asr_s':1.5,'text':'Reservoir'},
                         {'start':2,'end':3,'asr_s':.2,'text':'Quantum entanglement and qubits'}]}
        save(folder / 'asr.json',asr)
        return p,asr

    def test_audio_chunks_expose_only_current_samples_and_keep_last_partial_chunk(self):
        write_wav(self.folder / 'audio.wav',5)
        chunks = list(audio_chunks(self.folder / 'audio.wav',2))
        self.assertEqual([(a,b) for a,b,_ in chunks],[(0,2),(2,4),(4,5)])
        self.assertEqual([len(data) for _,_,data in chunks],[64000,64000,32000])
        for invalid in (0,float('nan'),31):
            with self.assertRaises(ValueError):list(audio_chunks(self.folder / 'audio.wav',invalid))

    def test_incomplete_future_visible_or_out_of_order_asr_is_rejected(self):
        _,asr = self.fixture()
        validate_chunks(asr)
        for key,value in [('complete',False),('future_audio_visible',True),('official_captions_visible',True)]:
            bad=copy.deepcopy(asr);bad[key]=value
            with self.assertRaises(ValueError):validate_chunks(bad)
        bad=copy.deepcopy(asr);bad['chunks'][1]['start']=.5
        with self.assertRaises(ValueError):validate_chunks(bad)
        bad=copy.deepcopy(asr);bad['chunks'][0]['asr_s']=float('nan')
        with self.assertRaises(ValueError):validate_chunks(bad)

    def test_rolling_recognition_window_contains_no_future_samples(self):
        path=self.folder/'distinct.wav'
        with wave.open(str(path),'wb') as f:
            f.setparams((1,2,16000,0,'NONE','not compressed'))
            for value in range(1,6):f.writeframes(bytes([value,0])*16000)
        windows=list(audio_windows(path,1,3))
        self.assertEqual([(a,b,c) for a,b,c,_ in windows],[(0,1,0),(1,2,0),(2,3,0),(3,4,1),(4,5,2)])
        for _,end,_,data in windows:
            self.assertLessEqual(max(data[::2]),end)
            self.assertEqual(data[-2],end)
        with self.assertRaises(ValueError):list(audio_windows(path,2,1))

    def test_replay_keeps_asr_queue_delay_and_leaves_original_workspace_untouched(self):
        p,_=self.fixture();before=(self.folder/'studio'/(p['id']+'.json')).read_bytes()
        result=replay(self.folder,self.folder/'asr.json')
        self.assertEqual([r['asr_available_at'] for r in result['rows']],[2.5,4,4.2])
        self.assertTrue(all(r['decision_completed_at']>=r['asr_available_at']>=r['end'] for r in result['rows']))
        self.assertEqual((self.folder/'studio'/(p['id']+'.json')).read_bytes(),before)
        self.assertEqual(result['rows'][-1]['decision']['action'],'HOLD')
        self.assertEqual(result['rows'][-1]['scene_id'],result['rows'][-2]['scene_id'])

    def test_approval_and_audio_source_binding_are_required(self):
        p,asr=self.fixture(approve=False)
        with self.assertRaises(Conflict):replay(self.folder,self.folder/'asr.json')
        store=Store(self.folder/'studio');studio=Studio(store);studio.approve(p['id'],p['revision'],True)
        asr['audio_sha256']='different audio';save(self.folder/'asr.json',asr)
        with self.assertRaises(ValueError):replay(self.folder,self.folder/'asr.json')

    def test_changed_preparation_cannot_be_attached_to_an_old_approved_package(self):
        self.fixture()
        (self.folder/'preparation.md').write_text('Unrelated new preparation material.')
        source=json.loads((self.folder/'source.json').read_text())
        source['preparation_sha256']=file_hash(self.folder/'preparation.md');save(self.folder/'source.json',source)
        with self.assertRaises(ValueError):replay(self.folder,self.folder/'asr.json')

    def test_stage_dwell_uses_injected_audio_clock(self):
        p,_=self.fixture()
        store=Store(self.folder/'studio');now=[0.0]
        studio=Studio(store,clock=lambda:now[0],dwell_s=2.5)
        p=studio.control(p['id'],'start');opening=p['live']['current_scene_id'];generation=p['live']['generation']
        now[0]=1
        p=studio.transcript(p['id'],'Radiator',0,generation=generation)
        self.assertEqual(p['live']['current_scene_id'],opening)
        now[0]=3
        p=studio.transcript(p['id'],'Radiator',1,generation=generation)
        self.assertNotEqual(p['live']['current_scene_id'],opening)
        self.assertEqual(p['live']['last_change'],3)

    def test_recording_commands_cannot_reset_a_workspace_owned_by_another_writer(self):
        with recording_store(self.folder / 'studio'):
            with self.assertRaises(ValueError):
                with recording_store(self.folder / 'studio'):
                    self.fail('Second writer was accepted.')

    def test_chapter_alignment_integrates_displayed_time_not_caption_votes(self):
        result={'package_hash':'approved','duration_s':20,'package':{'scenes':[{'id':'a','concept_id':'idea-a'},
                {'id':'b','concept_id':'idea-b'}],'concepts':[{},{}]},'events':[{'at':0,'scene_id':'a'},{'at':15,'scene_id':'b'}],
                'rows':[{'scene_id':'a','asr_s':.2,'audio_to_decision_s':.2,'decision_completed_at':10.2,'asr_available_at':10.2,'end':10,'recommendation':None}]}
        result['package_hash']=json_hash(result['package'])
        reference={'package_hash':result['package_hash'],'boundary_exclusion_s':0,'spans':[{'start':0,'end':10,'label':'A','acceptable_concept_ids':['idea-a'],'original_visual':'A'},
                    {'start':10,'end':20,'label':'B','acceptable_concept_ids':['idea-b'],'original_visual':'B'}]}
        metrics=score_replay(result,reference)
        self.assertEqual(metrics['development_chapter_alignment'],.75)
        self.assertEqual(metrics['chapters'][1]['first_matching_visual_lag_s'],5)
        self.assertEqual(metrics['causality_violations'],0)
        bad=copy.deepcopy(result);bad['events'][1]['scene_id']='unapproved'
        with self.assertRaises(ValueError):score_replay(bad,reference)
        bad=copy.deepcopy(reference);bad['package_hash']='other'
        with self.assertRaises(ValueError):score_replay(result,bad)
        bad=copy.deepcopy(result);bad['package']['scenes'][0]['concept_id']='tampered'
        with self.assertRaises(ValueError):score_replay(bad,reference)

    def test_report_keeps_source_content_inside_json_and_uses_actual_renderer(self):
        self.fixture()
        result=replay(self.folder,self.folder/'asr.json')
        attack='</script><script>alert(1)</script>'
        result['source'].update(title=attack,page_url='https://example.org/talk')
        result['package']['scenes'][0]['title']=attack
        result['package_hash']=json_hash(result['package'])
        result['asr']['chunk_s']=1
        scene=result['package']['scenes'][0]
        ref={'package_hash':result['package_hash'],'boundary_exclusion_s':0,'spans':[{'start':0,'end':3,'label':'Loop',
             'acceptable_concept_ids':[scene['concept_id']],'original_visual':'Diagram'}]}
        save(self.folder/'reference.json',ref)
        for mode in ('local','jev'):
            save(self.folder/('result-'+mode+'.json'),{**result,'mode':mode})
        build_report(self.folder)
        html=(self.folder/'comparison.html').read_text()
        self.assertNotIn(attack,html)
        self.assertIn('function renderScene(',html)
        self.assertIn('\\u003c/script>',html)
        result['package']['title']='changed after approval'
        save(self.folder/'result-jev.json',result)
        with self.assertRaises(ValueError):build_report(self.folder)


if __name__=='__main__':
    unittest.main()
