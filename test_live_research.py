"""Live research remains asynchronous, source-bound and subordinate to controls."""
import copy
import json
import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from presenter.engine import Store, Studio
from presenter.materials import ingest
from presenter.research import LiveResearch, ResearchProcess
from presenter import research_sources as sources
from presenter.server import make_server
from presenter.research_bridge import ResearchBridge, retrieved_scenes


def result(title='Heat pipe'):
    scene={'id':'web_'+title.replace(' ','_'),'concept_id':'web_topic','object_id':'web_topic','kind':'evidence','title':title,
      'source_refs':[{'unit_id':'web_unit','source_name':title,'quote':'This fixture represents an exact quotation returned by the source adapter.'}],
      'body':[],'review_status':'live_retrieved','web_source':{'url':'https://en.wikipedia.org/wiki/Heat_pipe','provider':'Wikipedia','presenter_reviewed':False}}
    return {'status':'ready','query':title,'items':[scene],'papers':[]}


class Backend:
    def __init__(self):self.entered=threading.Event();self.release=threading.Event();self.calls=[]
    def run(self,context,cancel):
        self.calls.append(context);self.entered.set();self.release.wait(2)
        return result('Heat pipe' if len(self.calls)==1 else 'Second related topic')


def until(predicate,timeout=2):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Research did not reach the expected state.')


class LiveResearchAuthority(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        self.studio=Studio(self.store,dwell_s=0)
        material=ingest('Cooling notes.md',b'# Circulation\n\nA pump circulates liquid through a hot component and radiator.\n\n# Flow measurement\n\nThe flow setting affects the rate of circulation.')
        p=self.store.create(title='A cooling loop',brief='Explain cooling and heat transfer.',audience='Students',sources=[material],provider='outline')
        p=self.studio.prepare(p['id'],background=False);p=self.studio.approve(p['id'],p['revision'],True)
        self.pid=p['id'];self.original_hash=p['approval']['package_hash'];self.backend=Backend()
        self.research=LiveResearch(self.studio,self.backend,cooldown_s=0);self.studio.research=self.research
        self.studio.control(self.pid,'start');self.studio.control(self.pid,'research',enabled=True)
    def tearDown(self):self.backend.release.set();self.research.close();self.temp.cleanup()
    def queue(self,text='What about heat pipes using evaporation and condensation?'):
        self.research.observe(self.pid,text,{},force=True)
        self.assertTrue(self.backend.entered.wait(1))
    def finish(self):
        self.backend.release.set();until(lambda:self.research.active is None)
        return self.store.read(self.pid)

    def test_follower_returns_while_research_runs_and_does_not_mutate_approval(self):
        p=self.store.read(self.pid);begun=time.monotonic()
        p=self.studio.transcript(self.pid,'What about heat pipes using evaporation and condensation?',0,generation=p['live']['generation'])
        self.assertLess(time.monotonic()-begun,.3)
        self.assertTrue(self.backend.entered.wait(1))
        self.assertIsNone(self.store.read(self.pid)['live']['research_scene'])
        p=self.finish()
        self.assertEqual(p['live']['research_scene']['title'],'Heat pipe')
        self.assertEqual(p['approval']['package_hash'],self.original_hash)
        self.assertNotIn('web_Heat_pipe',[s['id'] for s in p['approval']['package']['scenes']])
        self.assertTrue(p['research_history'][-1]['displayed_automatically'])

    def reject_after(self,action,**kwargs):
        self.queue();self.studio.control(self.pid,action,**kwargs);p=self.finish()
        self.assertIsNone(p['live']['research_scene'])
    def test_stop_rejects_late_research(self):self.reject_after('stop')
    def test_hold_rejects_late_research(self):self.reject_after('hold')
    def test_disabling_research_rejects_late_research(self):self.reject_after('research',enabled=False)
    def test_manual_visual_selection_rejects_late_research(self):
        scene=self.store.read(self.pid)['plan']['scenes'][-1]['id']
        self.reject_after('show',scene_id=scene)
        self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'],scene)

    def test_topic_expiry_keeps_material_backstage(self):
        self.queue()
        with self.store.change(self.pid) as p:p['live']['research']['last_heard']=time.time()-30
        p=self.finish();self.assertIsNone(p['live']['research_scene'])
        self.assertEqual(p['live']['research']['items'][0]['title'],'Heat pipe')
        self.assertFalse(p['research_history'][-1]['displayed_automatically'])

    def test_uncertain_relation_can_retrieve_material_without_automatic_display(self):
        self.backend.run=lambda context,cancel:{**result(),'allow_auto_display':False}
        self.research.observe(self.pid,'What about an alternative heat-transfer mechanism?',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='ready')
        p=self.store.read(self.pid)
        self.assertTrue(p['live']['research']['items']);self.assertIsNone(p['live']['research_scene'])
        self.assertFalse(p['research_history'][-1]['displayed_automatically'])

    def test_old_transcript_generation_and_sequence_cannot_start_research(self):
        old=self.store.read(self.pid)['live']['generation'];self.studio.control(self.pid,'hold');self.studio.control(self.pid,'resume')
        self.research.observe(self.pid,'What about heat pipes and evaporation?',{},generation=old,seq=0)
        self.assertIsNone(self.research.pending)
        self.assertFalse(self.backend.entered.is_set())
        current=self.store.read(self.pid)
        self.research.observe(self.pid,'What about heat pipes and evaporation?',{},generation=current['live']['generation'],seq=-2)
        self.assertFalse(self.backend.entered.is_set())

    def test_exact_repeated_query_uses_cached_material(self):
        self.queue();self.finish()
        self.queue();until(lambda:self.research.active is None and self.store.read(self.pid)['live']['research'].get('cache_hit'))
        self.assertEqual(len(self.backend.calls),1)
        self.assertEqual(self.store.read(self.pid)['live']['research']['request_count'],1)

    def test_ambiguous_fragments_do_not_exhaust_the_real_lookup_budget(self):
        self.backend.run=lambda context,cancel:{'status':'no_match','items':[]}
        self.research.observe(self.pid,'Could we explore another supporting mechanism?',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='no_match')
        research=self.store.read(self.pid)['live']['research']
        self.assertEqual(research['request_count'],0);self.assertEqual(research['assessment_count'],1)
        with self.store.change(self.pid) as p:p['live']['research']['assessment_count']=60
        self.research.observe(self.pid,'A further related mechanism needs explanation.',{},force=True)
        self.assertEqual(self.store.read(self.pid)['live']['research']['status'],'limit')

    def test_pending_topic_supersedes_old_result(self):
        self.queue();self.research.observe(self.pid,'Discuss thermoelectric semiconductor modules and voltage.',{},force=True)
        p=self.finish()
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='ready')
        p=self.store.read(self.pid)
        self.assertEqual(p['live']['research_scene']['title'],'Second related topic')
        self.assertEqual(len(p.get('research_history',[])),1)

    def test_failed_research_preserves_the_prepared_stage(self):
        def fail(*args):raise OSError('provider unavailable')
        self.backend.run=fail
        self.research.observe(self.pid,'What about heat pipes and evaporation?',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='error')
        p=self.store.read(self.pid);self.assertIsNone(p['live']['research_scene'])
        self.assertTrue(p['live']['current_scene_id'])

    def test_new_topic_cancels_old_result_even_during_search_cooldown(self):
        self.research.cooldown_s=100;self.queue()
        self.research.observe(self.pid,'Thermoelectric semiconductor voltage transport.',{})
        p=self.finish();self.assertIsNone(p['live']['research_scene'])

    def test_explicit_related_question_can_expand_a_high_scoring_prepared_match(self):
        self.research.observe(self.pid,'What about Peltier circulation?',{'scene_id':'prepared','score':.99})
        self.assertTrue(self.backend.entered.wait(1));self.finish()

    def progressive_backend(self):
        def run_progressive(context,cancel,publish):
            first=result();publish(first);self.backend.entered.set();self.backend.release.wait(2)
            enriched=copy.deepcopy(first);enriched['items'][0]['id']+='_enriched'
            return enriched
        self.backend.run_progressive=run_progressive

    def test_checked_source_appears_while_optional_enrichment_is_still_running(self):
        self.progressive_backend();self.queue()
        p=self.store.read(self.pid)
        self.assertEqual(p['live']['research_scene']['id'],'web_Heat_pipe')
        self.assertEqual(p['live']['research']['status'],'enriching')
        self.assertFalse(p['research_history'][-1]['final'])
        self.studio.dwell_s=100  # An upgrade of this same source is not a new topic.
        p=self.finish()
        self.assertEqual(p['live']['research_scene']['id'],'web_Heat_pipe_enriched')
        self.assertEqual(len(p['research_history']),1)
        self.assertTrue(p['research_history'][-1]['final'])

    def test_hold_rejects_optional_upgrade_but_retains_the_already_shown_source(self):
        self.progressive_backend();self.queue();self.studio.control(self.pid,'hold');p=self.finish()
        self.assertEqual(p['live']['research_scene']['id'],'web_Heat_pipe')
        self.assertEqual(p['research_history'][-1]['displayed_scene_ids'],['web_Heat_pipe'])

    def test_stop_during_enrichment_clears_the_source_and_rejects_the_upgrade(self):
        self.progressive_backend();self.queue();self.studio.control(self.pid,'stop');p=self.finish()
        self.assertIsNone(p['live']['research_scene'])

    def test_enrichment_failure_keeps_the_checked_source(self):
        def run_progressive(context,cancel,publish):
            publish(result());raise TimeoutError('image lookup too slow')
        self.backend.run_progressive=run_progressive
        self.research.observe(self.pid,'What about heat pipes and condensation?',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='ready')
        p=self.store.read(self.pid)
        self.assertEqual(p['live']['research_scene']['id'],'web_Heat_pipe')
        self.assertTrue(p['live']['research']['errors'])

    def test_stable_new_topic_can_start_before_the_general_cooldown(self):
        self.research.cooldown_s=100
        with self.store.change(self.pid) as p:
            p['live']['research']={'status':'no_match','last_requested':time.time()-2,'requested_novel':['old'],'request_count':0,'assessment_count':1}
            p['live']['transcript']=[{'text':'semiconductor voltage transport','at':time.time()},{'text':'semiconductor voltage transport mechanism','at':time.time()}]
        self.research.observe(self.pid,'semiconductor voltage transport mechanism',{})
        self.assertTrue(self.backend.entered.wait(1));self.finish()

    def prime_reuse(self):
        self.queue();self.finish();self.rechecked=[]
        def revalidate(context,cached,cancel):
            self.rechecked.append(copy.deepcopy(context))
            return {'status':'ready','query':cached['query'],'items':[],
                    'allow_auto_display':True,'plan_decision':{'source_support_probability':.95}}
        self.backend.revalidate=revalidate
        self.studio.control(self.pid,'show',scene_id=self.store.read(self.pid)['live']['current_scene_id'])

    def test_rephrased_topic_rechecks_cached_quote_without_another_lookup_or_ttl_extension(self):
        self.prime_reuse();created=list(self.research.cache.values())[0][0]
        with self.store.change(self.pid) as p:p['live']['research'].update(request_count=12)
        self.research.observe(self.pid,'Can we compare heat pipes with this cooling loop?',{},force=True)
        until(lambda:len(self.rechecked)==1 and self.research.active is None)
        p=self.store.read(self.pid)
        self.assertEqual(len(self.backend.calls),1);self.assertEqual(p['live']['research']['request_count'],12)
        self.assertEqual(p['live']['research']['assessment_count'],2)
        self.assertEqual(p['live']['research_scene']['title'],'Heat pipe')
        self.assertEqual(p['research_history'][-1]['cache_kind'],'topic_revalidated')
        self.assertEqual(list(self.research.cache.values())[0][0],created)
        self.assertEqual(p['approval']['package_hash'],self.original_hash)

    def test_cached_topic_must_appear_in_current_speech_and_expire_with_its_package(self):
        self.prime_reuse();key=next(iter(self.research.cache));created,cached=self.research.cache[key]
        self.assertIsNone(self.research.reusable('different_package','Compare heat pipes please.'))
        self.assertIsNone(self.research.reusable(self.original_hash,'How does that comparison work?'))
        self.research.cache[key]=(created-301,cached)
        self.assertIsNone(self.research.reusable(self.original_hash,'Compare heat pipes please.'))

    def test_rejected_reuse_cannot_publish_the_cached_quote(self):
        self.prime_reuse()
        self.backend.revalidate=lambda context,cached,cancel:{'status':'no_match','query':cached['query'],'items':[],'allow_auto_display':False}
        self.research.observe(self.pid,'Heat pipe means an unrelated object here.',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='no_match')
        p=self.store.read(self.pid)
        self.assertIsNone(p['live']['research_scene']);self.assertFalse(p['research_history'][-1]['displayed_automatically'])

    def test_stop_vetoes_revalidation_in_flight(self):
        self.prime_reuse();entered=threading.Event();release=threading.Event();original=self.backend.revalidate
        def blocked(context,cached,cancel):entered.set();release.wait(2);return original(context,cached,cancel)
        self.backend.revalidate=blocked
        try:
            self.research.observe(self.pid,'Compare heat pipes with cooling circulation.',{},force=True)
            self.assertTrue(entered.wait(1));self.studio.control(self.pid,'stop');release.set()
            until(lambda:self.research.active is None)
            self.assertIsNone(self.store.read(self.pid)['live']['research_scene'])
        finally:release.set()

    def test_reuse_still_respects_assessment_cap_and_never_replays_uncertain_sources(self):
        self.prime_reuse();key=next(iter(self.research.cache));self.research.cache[key][1]['allow_auto_display']=False
        self.assertIsNone(self.research.reusable(self.original_hash,'Compare heat pipes please.'))
        self.research.cache[key][1]['allow_auto_display']=True
        with self.store.change(self.pid) as p:p['live']['research']['assessment_count']=60
        self.research.observe(self.pid,'Compare heat pipes please.',{},force=True)
        self.assertEqual(self.store.read(self.pid)['live']['research']['status'],'limit');self.assertEqual(self.rechecked,[])

    def test_cached_source_that_expires_during_revalidation_cannot_publish(self):
        self.prime_reuse();created=list(self.research.cache.values())[0][0]
        clock=[created+299];self.research.clock=lambda:clock[0]
        original=self.backend.revalidate
        def delayed(context,cached,cancel):
            value=original(context,cached,cancel);clock[0]=created+301;return value
        self.backend.revalidate=delayed
        self.research.observe(self.pid,'Compare heat pipes please.',{},force=True)
        until(lambda:self.store.read(self.pid)['live']['research'].get('status')=='no_match')
        self.assertIsNone(self.store.read(self.pid)['live']['research_scene'])


class ConnectedResearchAgent(unittest.TestCase):
    def test_actual_http_handoff_is_operator_only_and_stop_rejects_a_pending_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            server=make_server(Store(folder),port=0,use_jev=False,research_bridge=True,dwell_s=0)
            service=threading.Thread(target=server.serve_forever,daemon=True);service.start()
            def call(path,body=None,key=None):
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={'X-Presenter-Key':key or server.access_token,'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=3) as r:return json.loads(r.read())
            try:
                p=call('/api/projects',{'title':'Cooling','brief':'Explain a pumped cooling loop.','provider':'outline',
                    'sources':[{'name':'Notes.md','text':'A pump circulates liquid through a hot component and radiator.'}]})
                pid=p['id'];url='/api/projects/'+pid
                until(lambda:call(url)['job']['status']=='ready');p=call(url)
                p=call(url+'/approve',{'revision':p['revision'],'reviewed':True});approval=p['approval']['package_hash']
                p=call(url+'/control',{'action':'start'});p=call(url+'/control',{'action':'research','enabled':True})
                call(url+'/transcript',{'text':'What about heat pipes and evaporation?','seq':0,'final':True,'generation':p['live']['generation']})
                until(lambda:call('/api/research/job')['job'] is not None)
                job=call('/api/research/job')['job']
                with self.assertRaises(urllib.error.HTTPError) as error:call('/api/research/job',key=p['stage_access'])
                self.assertEqual(error.exception.code,403)
                answer={'job_id':job['id'],'sources':[{'url':'https://www.nasa.gov/example','title':'Heat pipe source','quote':'Retrieved source quotation fixture supporting phase-change heat transport.'}]}
                call('/api/research/result',answer)
                until(lambda:bool(call(url+'/stage',key=p['stage_access'])['scene'].get('web_source')))
                self.assertEqual(call(url)['approval']['package_hash'],approval)
                self.assertEqual(len(call(url)['sources']),1)
                call(url+'/research',{'query':'What about thermoelectric semiconductor cooling?'})
                until(lambda:call('/api/research/job')['job'] is not None)
                old=call('/api/research/job')['job']['id'];call(url+'/control',{'action':'stop'})
                with self.assertRaises(urllib.error.HTTPError):call('/api/research/result',{**answer,'job_id':old})
                self.assertIsNone(call(url+'/stage',key=p['stage_access'])['scene'])
            finally:
                server.shutdown();server.server_close();service.join(2)

    def test_external_agent_result_is_bound_to_one_pending_request(self):
        bridge=ResearchBridge(timeout_s=2);cancel=threading.Event();results=[]
        thread=threading.Thread(target=lambda:results.append(bridge.run({'utterance':'thermoelectric cooling'},cancel)))
        thread.start();until(lambda:bridge.snapshot() is not None);job=bridge.snapshot()
        raw=[{'url':'https://science.nasa.gov/example','title':'Thermoelectric cooling','quote':'This is an actual-source quotation fixture, not a generated answer.'}]
        with self.assertRaises(ValueError):bridge.supply('old-request',raw)
        bridge.supply(job['id'],raw);thread.join(1)
        self.assertEqual(results[0]['items'][0]['review_status'],'live_retrieved')
        self.assertFalse(results[0]['items'][0]['web_source']['independently_verified_by_app'])
        with self.assertRaises(ValueError):bridge.supply(job['id'],raw)

    def test_connected_agent_can_report_no_suitable_source(self):
        bridge=ResearchBridge(timeout_s=2);results=[]
        thread=threading.Thread(target=lambda:results.append(bridge.run({'utterance':'A related topic'},threading.Event())))
        thread.start();until(lambda:bridge.snapshot() is not None)
        bridge.supply(bridge.snapshot()['id'],None,'no_match');thread.join(1)
        self.assertEqual(results[0]['items'],[])

    def test_retrieved_source_validation_rejects_active_links_and_unattributed_images(self):
        for source in ({'url':'javascript:alert(1)','title':'Unsafe','quote':'This source quotation has sufficient characters.'},
          {'url':'https://example.org','title':'Image','quote':'This source quotation has sufficient characters.','image':{'base64':'','name':'x.png'}}):
            with self.assertRaises(ValueError):retrieved_scenes([source])


class ProcurementSources(unittest.TestCase):
    def test_unrelated_topic_never_fetches_material(self):
        with patch.object(sources,'choose_query',return_value=None),patch.object(sources,'wiki') as fetch:
            self.assertEqual(sources.procure({})['status'],'no_match');fetch.assert_not_called()

    def test_candidate_rejection_does_not_publish_a_keyword_match(self):
        article={'id':'0','title':'Other domain','url':'https://en.wikipedia.org/wiki/Other','text':'Unrelated source text.'}
        response=SimpleNamespace(answers={'source':SimpleNamespace(value='none',confidence=.99)})
        with patch.object(sources,'choose_query',return_value={'query':'heat pipe'}),patch.object(sources,'wiki',return_value=[article]),patch.object(sources,'papers',return_value=[]),patch.object(sources,'commons',return_value=[]),patch.object(sources,'assess',return_value=response):
            self.assertEqual(sources.procure({'title':'Cooling','utterance':'heat pipes'})['items'],[])

    def test_source_quote_is_retrieved_text_and_a_bad_image_retains_the_quote(self):
        article={'id':'0','title':'Heat pipe','url':'https://en.wikipedia.org/wiki/Heat_pipe',
                 'text':'A heat pipe transfers heat using phase transition. This exact sentence comes from the retrieved fixture.',
                 'provider':'Wikipedia','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/'}
        image={'title':'File:Mechanism.png','url':'https://commons.wikimedia.org/wiki/File:Mechanism.png','image_url':'https://upload.wikimedia.org/a.png',
               'description':'Heat pipe mechanism','artist':'Fixture author','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/','mime':'image/png'}
        responses=[SimpleNamespace(answers={'source':SimpleNamespace(value='0',confidence=.99)}),SimpleNamespace(answers={'image':SimpleNamespace(value='0',confidence=.99)})]
        with patch.object(sources,'choose_query',return_value={'query':'heat pipe'}),patch.object(sources,'wiki',return_value=[article]),patch.object(sources,'papers',return_value=[]),patch.object(sources,'commons',return_value=[image]),patch.object(sources,'assess',side_effect=responses),patch.object(sources,'download',return_value=b'<script>not an image</script>'):
            r=sources.procure({'title':'Cooling','utterance':'Heat pipes and phase transition'})
        self.assertEqual(len(r['items']),1);scene=r['items'][0]
        self.assertEqual(scene['source_refs'][0]['quote'],article['text'])
        self.assertEqual(scene['web_source']['url'],article['url'])
        self.assertFalse(scene['web_source']['presenter_reviewed'])

    def test_unlicensed_or_non_raster_assets_are_not_procured(self):
        data={'query':{'pages':[{'title':'File:Unknown.png','imageinfo':[{'mime':'image/png','url':'https://upload.wikimedia.org/a.png','extmetadata':{}}]}]}}
        with patch.object(sources,'api',return_value=data):self.assertEqual(sources.commons('heat pipe'),[])

    def test_source_fetch_and_redirects_cannot_reach_arbitrary_or_private_hosts(self):
        for url in ('http://en.wikipedia.org/wiki/X','https://127.0.0.1/x','https://example.org/','https://en.wikipedia.org@127.0.0.1/x','https://commons.wikimedia.org:8765/'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):sources.checked_url(url)

    def test_provider_hard_deadline_kills_and_reaps_the_process(self):
        import subprocess
        captured=[];original=subprocess.Popen
        def spawn(*args,**kwargs):
            process=original(*args,**kwargs);captured.append(process);return process
        backend=ResearchProcess(timeout_s=.12,command=[sys.executable,'-c','import time;time.sleep(30)'])
        begun=time.monotonic()
        with patch('presenter.research.subprocess.Popen',side_effect=spawn):
            with self.assertRaises(TimeoutError):backend.run({},threading.Event())
        self.assertLess(time.monotonic()-begun,1)
        self.assertIsNotNone(captured[0].returncode)
        with self.assertRaises(ProcessLookupError):os.kill(captured[0].pid,0)

    def test_oversized_provider_output_is_rejected(self):
        backend=ResearchProcess(timeout_s=2,command=[sys.executable,'-c','print("x"*2000001)'])
        with self.assertRaises(ValueError):backend.run({},threading.Event())

    def test_subprocess_stream_publishes_before_optional_work_finishes(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            gate=Path(folder)/'published';source=result()
            script='import json,time;from pathlib import Path;print(json.dumps({"progress":'+repr(source)+'}),flush=True)\nwhile not Path('+repr(str(gate))+').exists():time.sleep(.01)\nprint(json.dumps('+repr(source)+'),flush=True)'
            backend=ResearchProcess(timeout_s=2,command=[sys.executable,'-c',script]);published=[]
            def publish(packet):published.append(packet);gate.touch()
            completed=backend.run_progressive({},threading.Event(),publish)
            self.assertEqual(completed['status'],'ready');self.assertEqual(len(published),1)


if __name__=='__main__':unittest.main()
