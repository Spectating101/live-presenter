"""Product acceptance checks: sources -> discussion -> approval -> prepared stage."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

from presenter.engine import Conflict, Store, Studio, jev_adviser, recommend
from presenter.materials import MaterialError, chart_data, ingest, normalized
from presenter.planning import PlanError, source_outline, validate_plan
from presenter.server import EXAMPLE, make_server
from system1_v10 import MockBackend


def example_sources():
    return [ingest(s['name'],s['text'].encode()) for s in EXAMPLE['sources']]


class DiscussionPartner:
    def prepare(self, project):
        plan=source_outline(project)
        if not any(m['role']=='user' for m in project['messages']):
            plan['questions']=[{'id':'q1','text':'Should we emphasize the circulation mechanism or energy efficiency?','blocking':True}]
            plan['understanding']='I understand the loop. I need to clarify the emphasis before preparing the final explanation.'
        else:
            plan['questions']=[]
            plan['understanding']='We will emphasize circulation. The supplied measurements do not establish efficiency.'
        return plan


class StudioAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root);self.studio=Studio(self.store,planner=DiscussionPartner(),dwell_s=0)
        self.p=self.store.create(title=EXAMPLE['title'],brief=EXAMPLE['brief'],audience=EXAMPLE['audience'],sources=example_sources())
        self.pid=self.p['id']
    def tearDown(self):self.temp.cleanup()

    def approved(self):
        p=self.studio.prepare(self.pid,'Focus on the circulation mechanism.',background=False)
        self.assertEqual(p['job']['status'],'ready')
        return self.studio.approve(self.pid,p['revision'],True)

    def test_full_preparation_dialogue_approval_and_stage(self):
        p=self.studio.prepare(self.pid,background=False)
        self.assertTrue(p['plan']['questions'][0]['blocking'])
        with self.assertRaises(Conflict):self.studio.approve(self.pid,p['revision'],True)
        p=self.approved();self.assertIsNotNone(p['approval'])
        self.assertIn('circulation',p['plan']['understanding'])
        p=self.studio.control(self.pid,'start');first=p['live']['current_scene_id']
        concept=p['approval']['package']['concepts'][1]
        p=self.studio.transcript(self.pid,concept['title'],0,generation=p['live']['generation'])
        self.assertEqual(p['live']['decision']['action'],'SHOW')
        self.assertNotEqual(p['live']['current_scene_id'],first)
        selected=p['live']['current_scene_id']
        p=self.studio.control(self.pid,'hold')
        p=self.studio.transcript(self.pid,p['plan']['concepts'][2]['title'],1,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],selected)
        self.assertIn('held',p['live']['decision']['reason'])
        p=self.studio.control(self.pid,'resume')
        p=self.studio.transcript(self.pid,'Quantum entanglement between superconducting qubits',2,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],selected)
        self.assertEqual(p['live']['decision']['action'],'HOLD')

    def test_edits_revoke_approval_and_stale_revision_is_rejected(self):
        p=self.approved();old_revision=p['revision']
        p=self.studio.prepare(self.pid,'Focus on another audience.',background=False)
        self.assertIsNone(p['approval'])
        with self.assertRaises(Conflict):self.studio.approve(self.pid,old_revision,True)
        with self.assertRaises(Conflict):self.studio.control(self.pid,'start')

    def test_live_package_cannot_be_mutated_after_approval(self):
        self.approved()
        with self.store.change(self.pid) as p:p['approval']['package']['title']='Unapproved change'
        with self.assertRaises(Conflict):self.studio.control(self.pid,'start')

    def test_interim_duplicate_and_old_session_transcripts_cannot_change_stage(self):
        self.approved();p=self.studio.control(self.pid,'start');generation=p['live']['generation']
        title=p['plan']['concepts'][1]['title'];first=p['live']['current_scene_id']
        p=self.studio.transcript(self.pid,title,1,final=False,generation=generation)
        self.assertEqual(p['live']['current_scene_id'],first);self.assertEqual(p['live']['last_seq'],-1)
        p=self.studio.transcript(self.pid,title,1,generation=generation)
        count=len(p['live']['transcript'])
        p=self.studio.transcript(self.pid,title,1,generation=generation)
        self.assertEqual(len(p['live']['transcript']),count)
        self.studio.control(self.pid,'stop');self.studio.control(self.pid,'start')
        with self.assertRaises(Conflict):self.studio.transcript(self.pid,title,2,generation=generation)

    def test_delayed_adviser_cannot_override_manual_selection(self):
        self.approved();p=self.studio.control(self.pid,'start')
        entered,release=threading.Event(),threading.Event()
        def slow(package,utterance):
            entered.set();release.wait(3)
            return {'scene_id':package['scenes'][0]['id'],'confidence':1}
        self.studio.live_assessor=slow
        p=self.studio.control(self.pid,'adviser',enabled=True)
        worker=threading.Thread(target=lambda:self.studio.transcript(self.pid,p['plan']['concepts'][1]['title'],0,generation=p['live']['generation']))
        worker.start();self.assertTrue(entered.wait(2))
        target=p['plan']['scenes'][-1]['id'];self.studio.control(self.pid,'show',target)
        release.set();worker.join(3)
        self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'],target)

    def test_dwell_prevents_rapid_switch_and_restart_requires_start(self):
        self.approved();p=self.studio.control(self.pid,'start');first=p['live']['current_scene_id']
        self.studio.dwell_s=100
        p=self.studio.transcript(self.pid,p['plan']['concepts'][1]['title'],0,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],first)
        Studio(self.store)
        self.assertFalse(self.store.read(self.pid)['live']['active'])
        self.assertIsNone(self.store.read(self.pid)['live']['current_scene_id'])
        self.assertTrue(self.store.read(self.pid)['approval'])

    def test_stopped_controls_and_malformed_advice_fail_closed(self):
        p=self.approved()
        with self.assertRaises(Conflict):self.studio.control(self.pid,'next')
        p=self.studio.control(self.pid,'start');p=self.studio.control(self.pid,'adviser',enabled=True)
        first=p['live']['current_scene_id']
        for index,bad in enumerate((None,{'scene_id':None,'confidence':'high'},{'confidence':float('nan')})):
            self.studio.live_assessor=lambda *args,bad=bad:bad
            p=self.studio.transcript(self.pid,p['plan']['concepts'][1]['title'],index,generation=p['live']['generation'])
            self.assertEqual(p['live']['current_scene_id'],first)
            self.assertEqual(p['live']['last_seq'],index)
        p=self.studio.control(self.pid,'stop')
        self.assertIsNone(p['live']['current_scene_id'])

    def test_model_advice_cannot_show_an_unknown_or_semantically_unmatched_scene(self):
        self.approved();p=self.studio.control(self.pid,'start');first=p['live']['current_scene_id']
        self.studio.live_assessor=lambda *args:{'scene_id':'made-up-scene','confidence':1}
        p=self.studio.control(self.pid,'adviser',enabled=True)
        p=self.studio.transcript(self.pid,p['plan']['concepts'][1]['title'],0,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],first)

    def test_back_follows_actual_history_and_sources_are_persisted(self):
        self.approved();p=self.studio.control(self.pid,'start');first=p['live']['current_scene_id']
        p=self.studio.control(self.pid,'show',p['plan']['scenes'][-1]['id'])
        p=self.studio.control(self.pid,'back');self.assertEqual(p['live']['current_scene_id'],first)
        self.assertEqual(len(Store(self.root).read(self.pid)['sources']),2)

    def test_new_rehearsal_resets_sequence_and_archives_previous_transcript(self):
        self.approved();p=self.studio.control(self.pid,'start')
        title=p['plan']['concepts'][1]['title']
        self.studio.transcript(self.pid,title,40,generation=p['live']['generation'])
        self.studio.control(self.pid,'stop');p=self.studio.control(self.pid,'start')
        self.assertEqual(p['live']['last_seq'],-1)
        self.assertEqual(p['live']['candidate_count'],0)
        self.assertEqual(p['live']['transcript'],[])
        p=self.studio.transcript(self.pid,title,0,generation=p['live']['generation'])
        self.assertEqual(p['live']['last_seq'],0)
        self.assertEqual(p['rehearsals'][0]['transcript'][0]['seq'],40)
        Studio(self.store)
        p=self.store.read(self.pid)
        self.assertEqual(p['live']['last_seq'],-1)
        self.assertFalse(p['live']['active'])
        self.assertEqual(len(p['rehearsals']),2)

    def test_manual_controls_clear_pending_automatic_switch(self):
        self.approved();p=self.studio.control(self.pid,'start')
        target=p['plan']['scenes'][-1]['id']
        suggestion={'scene_id':target,'score':.6,'confirmed':False,'supported_concepts':[]}
        with patch('presenter.engine.recommend',return_value=suggestion):
            p=self.studio.transcript(self.pid,'A possible match',0,generation=p['live']['generation'])
            self.assertEqual(p['live']['candidate_count'],1)
            first=p['live']['current_scene_id']
            p=self.studio.control(self.pid,'show',first)
            self.assertEqual(p['live']['candidate_count'],0)
            p=self.studio.transcript(self.pid,'A possible match',1,generation=p['live']['generation'])
            self.assertEqual(p['live']['decision']['action'],'WARM')
            self.assertEqual(p['live']['current_scene_id'],first)
            self.studio.control(self.pid,'hold');p=self.studio.control(self.pid,'resume')
            self.assertEqual(p['live']['candidate_count'],0)
            self.assertNotIn('recommendation',p['live'])


class MaterialAndGrounding(unittest.TestCase):
    def setUp(self):
        self.p={**EXAMPLE,'sources':example_sources()}

    def test_chart_uses_dataset_values_and_rejects_invented_columns(self):
        ds=self.p['sources'][1]['dataset']
        self.assertEqual([r['value'] for r in chart_data(ds,'Setting','Electrical_power_W')],[90,145,230])
        with self.assertRaises(MaterialError):chart_data(ds,'Setting','Invented_efficiency')
        with self.assertRaises(MaterialError):ingest('bad.csv',b'A,A\n1,2\n')
        with self.assertRaises(MaterialError):ingest('bad.csv',b'A,B\n1\n')
        with self.assertRaises(MaterialError):ingest('empty.csv',b'A,B\n,\n')

    def test_sources_do_not_silently_accept_unsupported_files_and_docx_extracts(self):
        with self.assertRaises(MaterialError):ingest('script.html',b'<script>alert(1)</script>')
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as doc:
            doc.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Readable source text.</w:t></w:r></w:p></w:body></w:document>')
        source=ingest('source.docx',data.getvalue())
        self.assertEqual(source['units'][0]['text'],'Readable source text.')

    def test_fabricated_quotes_numbers_and_executable_scenes_rejected(self):
        source=self.p['sources'][0]['units'][0]
        concept={'title':'The loop','summary':'Cooling mechanism','source_refs':[{'unit_id':source['id'],'quote':normalized(source['text'])}],
                 'visuals':[{'kind':'definition','body':['A source-linked explanation']} ]}
        raw={'concepts':[concept]};self.assertTrue(validate_plan(raw,self.p)['scenes'])
        for change in ({'kind':'metric','value':'999999','label':'Invented'}, {'kind':'html','body':['<script>']}):
            bad=copy.deepcopy(raw);bad['concepts'][0]['visuals']=[change]
            with self.assertRaises(PlanError):validate_plan(bad,self.p)
        bad=copy.deepcopy(raw);bad['concepts'][0]['source_refs'][0]['quote']='This sentence is not in the supplied source.'
        with self.assertRaises(PlanError):validate_plan(bad,self.p)


class ConceptFollowing(unittest.TestCase):
    def setUp(self):
        self.package={'concepts':[
            {'id':'path','title':'Liquid path','summary':'Trace the loop.','aliases':['trace the liquid'],
             'source_refs':[{'quote':'The reservoir supplies liquid to the pump. The radiator releases heat.'}]},
            {'id':'limits','title':'Interpretation limits','summary':'The data cannot establish efficiency.','aliases':['interpretation limits'],
             'source_refs':[{'quote':'Coolant temperature and heat removal were not recorded.'}]}],
            'scenes':[{'id':'path_flow','concept_id':'path','kind':'flow'},
                      {'id':'path_evidence','concept_id':'path','kind':'evidence'},
                      {'id':'limits_definition','concept_id':'limits','kind':'definition'}]}

    def test_source_language_supports_idea_without_requiring_its_title(self):
        choice=recommend(self.package,'We did not measure coolant temperature or heat removal.')
        self.assertEqual(choice['scene_id'],'limits_definition')
        self.assertEqual(recommend(self.package,'Quantum entanglement between qubits')['scene_id'],None)

    def test_jev_classifies_idea_independently_of_visual_alternatives(self):
        backend=MockBackend({'concept':{'type':'choice','choice':'path','confidence':.91,'probabilities':{'path':.91,'limits':.04,'hold':.05}},
            'representation':{'type':'choice','choice':'flow','confidence':.85,'probabilities':{'flow':.85,'evidence':.1,'definition':.05}}})
        with patch('presenter.engine.JevBackend',return_value=backend):
            choice=jev_adviser(self.package,'Follow the liquid through the reservoir and pump.')
        self.assertEqual(choice['scene_id'],'path_flow')
        self.assertEqual(choice['confidence'],.91)
        questions=backend.calls[0][1]
        self.assertEqual(set(questions['concept']['criteria']),{'path','limits','hold'})
        self.assertNotIn('path_evidence',questions['concept']['criteria'])


class HTTPAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        self.server=make_server(self.store,port=0,planner=DiscussionPartner(),use_jev=False,dwell_s=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.temp.cleanup()
    def call(self,path,body=None,headers=None):
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Presenter-Key':self.server.access_token,**({'Content-Type':'application/json'} if body is not None else {}),**(headers or {})})
        with urllib.request.urlopen(request,timeout=5) as r:return r.status,json.loads(r.read())

    def test_browser_api_to_saved_package_to_projector_contract(self):
        status,p=self.call('/api/projects',{**EXAMPLE,'provider':'outline'})
        self.assertEqual(status,201);pid=p['id']
        for _ in range(50):
            _,p=self.call('/api/projects/'+pid)
            if p['job']['status']!='working':break
            time.sleep(.01)
        self.assertEqual(p['job']['status'],'ready')
        _,p=self.call(f'/api/projects/{pid}/approve',{'revision':p['revision'],'reviewed':True})
        _,p=self.call(f'/api/projects/{pid}/control',{'action':'start'})
        target=p['plan']['concepts'][1]['title']
        self.call(f'/api/projects/{pid}/transcript',{'text':target,'seq':0,'final':True,'generation':p['live']['generation']})
        _,stage=self.call(f'/api/projects/{pid}/stage')
        self.assertTrue(stage['scene']);self.assertNotIn('messages',stage);self.assertNotIn('sources',stage)
        self.assertTrue((Path(self.temp.name)/(pid+'.json')).exists())

    def test_cross_origin_and_disk_exposure_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call('/api/projects',EXAMPLE,{'Origin':'https://untrusted.example'})
        self.assertEqual(e.exception.code,403)
        for path in ('/presenter/server.py','/artifacts/studio/anything.json'):
            with self.assertRaises(urllib.error.HTTPError) as e:self.call(path)
            self.assertEqual(e.exception.code,404)

    def test_operator_key_and_projector_read_only_capability(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.call('/api/projects',headers={'X-Presenter-Key':''})
        self.assertEqual(e.exception.code,403)
        _,p=self.call('/api/projects',{**EXAMPLE,'provider':'outline'})
        key=self.server.stage_token(p['id'])
        self.call(f"/api/projects/{p['id']}/stage",headers={'X-Presenter-Key':key})
        with self.assertRaises(urllib.error.HTTPError) as e:self.call(f"/api/projects/{p['id']}",headers={'X-Presenter-Key':key})
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as e:self.call(f"/api/projects/{p['id']}/control",{'action':'start'},headers={'X-Presenter-Key':key})
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(RuntimeError):make_server(self.store,port=0,use_jev=False)

    def test_projector_long_poll_wakes_on_change_without_exposing_operator_state(self):
        _,p=self.call('/api/projects',{**EXAMPLE,'provider':'outline'})
        for _ in range(50):
            _,p=self.call('/api/projects/'+p['id'])
            if p['job']['status']=='ready':break
            time.sleep(.01)
        _,p=self.call(f"/api/projects/{p['id']}/approve",{'revision':p['revision'],'reviewed':True})
        _,p=self.call(f"/api/projects/{p['id']}/control",{'action':'start'})
        entered=threading.Event();original=self.store.condition
        def observe(pid):entered.set();return original(pid)
        self.store.condition=observe
        results=[]
        worker=threading.Thread(target=lambda:results.append(self.call(f"/api/projects/{p['id']}/stage?after={p['state_version']}",headers={'X-Presenter-Key':p['stage_access']})))
        worker.start();self.assertTrue(entered.wait(2))
        self.call(f"/api/projects/{p['id']}/control",{'action':'next'})
        worker.join(2)
        self.assertFalse(worker.is_alive())
        stage=results[0][1]
        self.assertGreater(stage['state_version'],p['state_version'])
        self.assertNotIn('sources',stage);self.assertNotIn('messages',stage)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call(f"/api/projects/{p['id']}/stage?after=invalid")
        self.assertEqual(e.exception.code,400)


if __name__=='__main__':unittest.main()
