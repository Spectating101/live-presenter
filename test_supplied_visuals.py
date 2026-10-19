"""Supplied image provenance, approval boundaries and intentional view selection."""
import base64
import copy
import hashlib
import json
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from presenter.engine import Conflict, Store, Studio, preferred_kind, recommend, jev_adviser
from presenter.materials import ingest
from presenter.planning import CopilotPreparation, PlanError, validate_plan
from presenter.reflex import CueIndex
from presenter.server import make_server


def png(width=2, height=1):
    def chunk(kind, body):
        return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0'*width)*height))+chunk(b'IEND',b'')


def fixture():
    notes=ingest('Notes.md',b'Historical evidence is compared with popularity. A dataset can reveal that popular things have less research support.')
    image=ingest('Evidence map.png',png(),'Illustrative evidence versus popularity chart, supplied by the presenter.')
    raw={'concepts':[{'title':'Historical evidence','summary':'Compare research evidence with popularity.','aliases':['research support'],
      'source_refs':[{'unit_id':notes['units'][0]['id'],'quote':notes['units'][0]['text']}],
      'default_visual':1,'visuals':[{'kind':'definition','body':['Popularity and research support differ.']},
                                  {'kind':'image','asset_id':image['id']}]}]}
    return {'title':'Evidence and popularity','audience':'General audience','sources':[notes,image]},raw


class SuppliedVisuals(unittest.TestCase):
    def test_pixels_remain_exact_and_image_scene_cites_the_supplied_asset(self):
        project,raw=fixture()
        plan=validate_plan(raw,project)
        image=next(s for s in plan['scenes'] if s['kind']=='image')
        data=base64.b64decode(image['asset']['data_url'].split(',')[1])
        self.assertEqual(data,png())
        self.assertEqual(hashlib.sha256(data).hexdigest(),image['asset']['sha256'])
        self.assertEqual(image['source_refs'][0]['unit_id'],project['sources'][1]['units'][0]['id'])
        self.assertEqual(plan['concepts'][0]['default_scene_id'],image['id'])

    def test_unknown_or_remote_images_cannot_enter_a_prepared_package(self):
        project,raw=fixture()
        raw['concepts'][0]['visuals'][1]={'kind':'image','asset_id':'https://example.invalid/chart.png','src':'javascript:alert(1)'}
        with self.assertRaises(PlanError):validate_plan(raw,project)

    def test_bad_signatures_truncation_and_size_are_rejected(self):
        for name,data in [('chart.png',b'<svg onload="x"/>'),('chart.png',png()[:-2]),
                          ('chart.jpg',b'\xff\xd8'+b'\xff'*20+b'\xff\xd9'),
                          ('chart.png',png()+b'\0'*512_000),('chart.png',png(4097))]:
            with self.subTest(name=name,size=len(data)):
                with self.assertRaises(ValueError):ingest(name,data)
        damaged=bytearray(png());damaged[-5]^=1
        with self.assertRaises(ValueError):ingest('chart.png',bytes(damaged))

    def test_ordinary_evidence_language_uses_the_approved_default_in_both_paths(self):
        project,raw=fixture();plan=validate_plan(raw,project)
        expected=plan['concepts'][0]['default_scene_id']
        utterance='Historical evidence is compared with popularity.'
        self.assertIsNone(preferred_kind(utterance))
        self.assertEqual(recommend(plan,utterance)['scene_id'],expected)
        self.assertEqual(CueIndex(plan,project['sources']).match(utterance,preferred_kind(utterance))['scene_id'],expected)
        requested='Show the source: historical evidence is compared with popularity.'
        self.assertEqual(preferred_kind(requested),'evidence')
        self.assertEqual(CueIndex(plan,project['sources']).match(requested,'evidence')['scene_id'],plan['scenes'][-1]['id'])

    def test_classifier_representation_does_not_override_a_presenter_default(self):
        project,raw=fixture();plan=validate_plan(raw,project)
        response=SimpleNamespace(model='fixture',latency_ms=1,answers={
            'concept':SimpleNamespace(value=plan['concepts'][0]['id'],confidence=.95),
            'representation':SimpleNamespace(value='evidence',confidence=.99)})
        class Backend:
            async def ask(self,*args):return response
        with patch('presenter.engine.JevBackend',return_value=Backend()):
            answer=jev_adviser(plan,'Historical evidence and popularity')
        self.assertEqual(answer['scene_id'],plan['concepts'][0]['default_scene_id'])

    def test_preparation_prompt_contains_metadata_but_no_image_bytes_in_previous_plan(self):
        project,raw=fixture();project.update(brief='Explain the distinction.',messages=[])
        project['plan']=validate_plan(raw,project)
        image=project['sources'][1]['asset']
        def run(arguments,**kwargs):
            prompt=arguments[-1]
            self.assertNotIn(image['data_url'],prompt)
            self.assertNotIn(image['data_url'].split(',')[1],prompt)
            self.assertIn(image['sha256'],prompt)
            return SimpleNamespace(returncode=0,stdout=json.dumps(raw))
        with patch('presenter.planning.shutil.which',return_value='/fixture'),patch('presenter.planning.subprocess.run',side_effect=run):
            plan=CopilotPreparation().prepare(project)
        self.assertEqual(plan['scenes'][1]['asset']['data_url'],image['data_url'])

    def test_default_changes_invalidate_approval_and_cannot_happen_during_rehearsal(self):
        source,raw=fixture();plan=validate_plan(raw,source)
        class Planner:
            def prepare(self,p):return copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);studio=Studio(store,planner=Planner(),dwell_s=0)
            p=store.create(title=source['title'],brief='Explain.',audience=source['audience'],sources=source['sources'])
            p=studio.prepare(p['id'],background=False);p=studio.approve(p['id'],p['revision'],True)
            old_revision=p['revision'];p=studio.default_scene(p['id'],plan['scenes'][0]['id'])
            self.assertIsNone(p['approval'])
            with self.assertRaises(Conflict):studio.approve(p['id'],old_revision,True)
            p=studio.approve(p['id'],p['revision'],True);p=studio.control(p['id'],'start')
            self.assertEqual(p['live']['current_scene_id'],plan['scenes'][0]['id'])
            with self.assertRaises(Conflict):studio.default_scene(p['id'],plan['scenes'][1]['id'])
            with store.change(p['id']) as current:current['approval']['package']['scenes'][1]['asset']['data_url']='data:image/png;base64,changed'
            with self.assertRaises(Conflict):studio.package(store.read(p['id']))

    def test_stage_has_no_draft_image_and_only_approved_bytes_after_approval(self):
        source,raw=fixture();plan=validate_plan(raw,source)
        class Planner:
            def prepare(self,p):return copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as folder:
            server=make_server(Store(folder),port=0,planner=Planner(),use_jev=False)
            service=threading.Thread(target=server.serve_forever,daemon=True);service.start()
            def call(path,body=None,token=None):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={'X-Presenter-Key':token or server.access_token,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=3) as r:return json.loads(r.read())
            try:
                sources=[{'name':'Notes.md','text':source['sources'][0]['units'][0]['text']},
                         {'name':'Evidence map.png','base64':base64.b64encode(png()).decode()}]
                p=call('/api/projects',{'sources':sources,'title':source['title']})
                pid=p['id'];url=f'/api/projects/{pid}';key=p['stage_access']
                for _ in range(50):
                    p=call(url)
                    if p['job']['status']=='ready':break
                    time.sleep(.01)
                self.assertEqual(call(url+'/stage',token=key)['scenes'],[])
                p=call(url+'/approve',{'revision':p['revision'],'reviewed':True})
                call(url+'/control',{'action':'start'})
                stage=call(url+'/stage',token=key)
                self.assertEqual(stage['scene']['kind'],'image')
                self.assertEqual(stage['scene']['asset']['data_url'],source['sources'][1]['asset']['data_url'])
                self.assertNotIn('sources',stage)
                with self.assertRaises(urllib.error.HTTPError):call(url,token=key)
                call(url+'/control',{'action':'stop'})
                call(url+'/default-scene',{'scene_id':plan['scenes'][0]['id']})
                self.assertEqual(call(url+'/stage',token=key)['scenes'],[])
            finally:
                server.shutdown();server.server_close();service.join(2)


if __name__=='__main__':unittest.main()
