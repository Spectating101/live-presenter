"""Background live procurement. The prepared follower never waits for this worker."""
from collections import OrderedDict
import copy
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .language import tokens,STOP
from .explanation import explanation_need, presentation_fit, focus_target


class ResearchProcess:
    def __init__(self, timeout_s=25,command=None):self.timeout_s,self.command=timeout_s,command

    def run(self, context, cancelled):
        return self._run(context,cancelled,None)

    def run_progressive(self,context,cancelled,publish):
        return self._run({**context,'_stream':True},cancelled,publish)

    def revalidate(self,context,cached,cancelled):
        scene=next((s for s in cached['items'] if s['kind']=='evidence'),cached['items'][0])
        return self._run({**context,'mode':'reuse','cached_source':{
            'query':cached['query'],'title':scene['title'],
            'quote':scene['source_refs'][0]['quote']}},cancelled,None)

    def _run(self, context, cancelled, publish):
        env=os.environ.copy()
        for key in list(env):
            if key.endswith(('API_KEY','TOKEN')) and key not in {'JEV_API_KEY','TYPESAFE_API_KEY'}:env.pop(key,None)
        payload=json.dumps(context,ensure_ascii=False).encode()
        if len(payload)>100_000:raise ValueError('Research context exceeds its limit.')
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as input_file:
            input_file.write(payload);input_file.seek(0)
            process=subprocess.Popen(self.command or [sys.executable,'-m','presenter.research','--child'],
              cwd=Path(__file__).resolve().parent.parent,env=env,stdin=input_file,stdout=output,
              stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline=time.monotonic()+self.timeout_s
                offset=0;buffer=b'';result=None
                def consume():
                    nonlocal offset,buffer,result
                    size=os.fstat(output.fileno()).st_size
                    if size>2_000_000:raise ValueError('Research output exceeded its limit.')
                    block=os.pread(output.fileno(),size-offset,offset);offset+=len(block);buffer+=block
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1)
                        if not line.strip():continue
                        packet=json.loads(line)
                        if 'progress' in packet:
                            if publish:publish(packet['progress'])
                        else:result=packet
                while process.poll() is None:
                    if cancelled.wait(.04):raise TimeoutError('Research superseded or stopped.')
                    if time.monotonic()>deadline:raise TimeoutError(f'Research exceeded its {self.timeout_s:g}-second budget.')
                    consume()
                consume()
                if buffer.strip():result=json.loads(buffer)
                if not isinstance(result,dict):raise ValueError('Research returned no final result.')
                if process.returncode or result.get('status')=='error':raise ValueError(result.get('message','Research unavailable.'))
                return result
            finally:
                if process.poll() is None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                process.wait(timeout=3)


def empty_research():
    return {'status':'idle','request_id':'','query':'','items':[],'papers':[],'request_count':0,'last_heard':0,'last_requested':0,
            'assessment_count':0,'message':'Related online material will be researched when a new topic needs it.'}


class LiveResearch:
    def __init__(self,studio,backend=None,*,clock=time.time,cooldown_s=6,fresh_s=20):
        self.studio,self.store,self.backend=studio,studio.store,backend or ResearchProcess()
        self.clock,self.cooldown_s,self.fresh_s=clock,cooldown_s,fresh_s
        self.condition=threading.Condition();self.pending=None;self.active=None;self.closed=False
        self.cache=OrderedDict()
        self.worker=threading.Thread(target=self.work,daemon=True,name='presenter-research');self.worker.start()

    def invalidate(self,pid):
        with self.condition:
            if self.active and self.active['pid']==pid:self.active['cancel'].set()
            if self.pending and self.pending['pid']==pid:self.pending=None
            self.condition.notify_all()

    def reusable(self,package_hash,utterance):
        # A literal topic mention only nominates cached material. The provider
        # must check this new context before it gets any display authority.
        def words(text):
            return [w[:-1] if w.endswith('s') and not w.endswith(('ss','us','is')) else w
                    for w in re.findall(r'[a-z0-9]+',text.lower()) if w not in STOP-{'first'}]
        speech=words(utterance);now=self.clock()
        with self.condition:
            for (bound_package,_),(created,result) in reversed(self.cache.items()):
                query=words(result.get('query',''))
                if (bound_package==package_hash and now-created<300 and result.get('allow_auto_display',True)
                        and any(s.get('kind')=='evidence' for s in result.get('items',[]))
                        and len(re.findall(r'[a-z0-9]+',result.get('query','').lower()))>=2 and query
                        and any(speech[i:i+len(query)]==query for i in range(len(speech)-len(query)+1))):
                    return created,copy.deepcopy(result)
        return None

    def observe(self,pid,utterance,recommendation,*,force=False,generation=None,seq=None):
        p=self.store.read(pid)
        live=p['live']
        if not live['active'] or live['locked'] or not live.get('research_enabled'):return
        if generation is not None and live['generation']!=generation:return
        if seq is not None and live['last_seq']!=seq:return
        package=self.studio.package(p)
        known=tokens(' '.join(c['title']+' '+c['summary']+' '+' '.join(c['aliases']) for c in package['concepts']))
        known |= tokens(' '.join(phrase for scene in package['scenes'] for target in scene.get('annotations', []) for phrase in target['cue_phrases']))
        recent=[r['text'] for r in live['transcript'][-4:-1] if self.clock()-r['at']<=8]
        from .research_sources import spoken_context
        topic_speech=spoken_context({'utterance':utterance,'recent_past':recent})
        novel=tokens(topic_speech)-known-{'compared','instead','please','find','show','explain','could','would','about','tell'}
        current_scene = next((s for s in package['scenes'] if s['id'] == live['current_scene_id']), None)
        prepared=bool((recommendation.get('scene_id') and recommendation.get('score',0)>=.88) or focus_target(current_scene,utterance))
        explicit=bool(re.search(r'\b(?:what about|how about|instead of|compared with|versus|can you find|look up|research)\b',utterance,re.I))
        if prepared and len(novel)<2 and not force and not (explicit and novel):
            with self.store.change(pid) as current:
                if current['live']['generation']!=live['generation'] or (seq is not None and current['live']['last_seq']!=seq):return
                research=current['live'].setdefault('research',empty_research())
                research.update(request_id='',status='idle',message='Prepared material covers the current explanation.')
            self.invalidate(pid)
            return
        if (len(tokens(utterance))<3 and not (explicit or force)) or (not force and not novel):return
        now=self.clock();research=live.get('research',empty_research())
        previous=set(research.get('novel',[]))
        continuation=bool(previous and novel and len(previous&novel)/max(1,min(len(previous),len(novel)))>=.5)
        if continuation and research.get('status')=='ready' and live.get('research_scene') and not force and not explicit:
            with self.store.change(pid) as current:
                if current['live']['generation']==live['generation']:
                    current['live']['research'].update(last_heard=now,novel=sorted(novel))
            return
        if continuation and research.get('request_id') and research.get('status') in {'queued','searching','enriching'}:
            with self.store.change(pid) as current:
                if current['live'].get('research',{}).get('request_id')==research['request_id']:
                    current['live']['research']['last_heard']=now
                    current['live']['research']['novel']=sorted(novel)
            return
        if previous and novel and not continuation and research.get('request_id') and research.get('status') in {'queued','searching','enriching'}:
            with self.store.change(pid) as current:
                if current['live'].get('research',{}).get('request_id')==research['request_id']:
                    current['live']['research'].update(request_id='',status='idle',message='The topic changed; earlier research will not take the stage.')
            self.invalidate(pid)
        reuse=self.reusable(p['approval']['package_hash'],utterance) if hasattr(self.backend,'revalidate') else None
        elapsed=now-research.get('last_requested',0)
        stable_new=(tokens(utterance)&tokens(recent[-1]) if recent else set())-known-set(research.get('requested_novel',[]))
        early=(research.get('status') in {'no_match','no_results','idle'} and elapsed>=1.5 and len(stable_new)>=2)
        corrected=(research.get('status')=='no_match' and not research.get('query') and elapsed>=1.5
                   and bool(tokens(utterance)-known-set(research.get('requested_novel',[]))))
        if not force and elapsed<self.cooldown_s and not early and not corrected and not reuse:return
        cache_key=(p['approval']['package_hash'],tuple(sorted(tokens(utterance))))
        with self.condition:cached=self.cache.get(cache_key)
        exact=bool(cached and now-cached[0]<300)
        warm=exact or bool(reuse)
        if research.get('request_count',0)>=12 and not warm:
            with self.store.change(pid) as current:current['live']['research'].update(status='limit',message='This rehearsal has used its twelve research requests. Prepared following continues.')
            return
        if research.get('assessment_count',0)>=60 and not exact:
            with self.store.change(pid) as current:current['live']['research'].update(status='limit',message='This rehearsal reached its sixty topic assessments. Prepared following continues.')
            return
        request_id=uuid.uuid4().hex
        context={'title':package['title'],'brief':p['brief'],'concepts':[{k:c[k] for k in ('title','summary','aliases')} for c in package['concepts']],
                 'utterance':utterance[:600],'recent_past':recent}
        need = explanation_need(topic_speech, p.get('audience', ''))
        current_scene = next((s for s in package['scenes'] if s['id'] == live['current_scene_id']), None)
        current_concept = next((c for c in package['concepts'] if current_scene and c['id'] == current_scene['concept_id']), {})
        if need['missing_intent'] and current_concept.get('explanation', {}).get('goal'):
            need = explanation_need(topic_speech, p.get('audience', ''), goal=current_concept['explanation']['goal'])
        context['explanation_need'] = need
        job={'pid':pid,'generation':live['generation'],'package_hash':p['approval']['package_hash'],
             'request_id':request_id,'context':context,'cancel':threading.Event(),
             'cache_key':cache_key,'queued_at':now,'reuse':reuse}
        with self.store.change(pid) as current:
            if (current['live']['generation']!=job['generation'] or not current['live'].get('research_enabled')
                    or not current['live']['active'] or current['live']['locked']
                    or (seq is not None and current['live']['last_seq']!=seq)):return
            current['live']['research']={**research,'status':'queued','request_id':request_id,'novel':sorted(novel),
              'last_heard':now,'last_requested':now,'request_count':research.get('request_count',0)+int(not warm),
              'assessment_count':research.get('assessment_count',0)+int(not exact),
              'requested_novel':sorted(novel),
              'message':'Finding related sources and visual material online…'}
        with self.condition:
            if self.closed:return
            if self.active:self.active['cancel'].set()
            self.pending=job;self.condition.notify_all()

    def valid(self,job,p):
        live=p['live'];research=live.get('research',{})
        return (not self.closed and not job['cancel'].is_set() and live['active'] and not live['locked']
            and live.get('research_enabled') and live['generation']==job['generation']
            and (p.get('approval') or {}).get('package_hash')==job['package_hash']
            and research.get('request_id')==job['request_id'])

    def complete(self,job,result,*,final=True):
        with self.store.change(job['pid']) as p:
            if not self.valid(job,p):return
            self.studio.package(p)
            research=p['live']['research'];fresh=self.clock()-research['last_heard']<=self.fresh_s
            items=result.get('items',[])[:2]
            research.update(status=result['status'] if final else 'enriching',query=result.get('query',''),items=copy.deepcopy(items),
              papers=result.get('papers',[])[:3],completed_at=self.clock(),errors=result.get('errors',[]),
              message=result.get('message') or ('Related material found.' if fresh else 'Related material found after the topic expired; retained backstage.'),
              cache_hit=result.get('cache_hit',False),cache_kind=result.get('cache_kind'),
              provider_scope=result.get('provider_scope',[]))
            research['classifier_calls']=result.get('classifier_calls',[])
            research['plan_decision']=result.get('plan_decision',{})
            research['allow_auto_display']=result.get('allow_auto_display',True)
            research['timing']=result.get('timing',{})
            need = job['context'].get('explanation_need')
            fits = {s['id']: presentation_fit(s, need) for s in items}
            research['explanation_need'] = copy.deepcopy(need)
            research['presentation_fit'] = fits
            if items and not fresh:research['message']='Material arrived after the topic expired; retained backstage.'
            elif items and not result.get('allow_auto_display',True):research['message']='Material found with uncertain topic context; retained backstage for review.'
            if final and result['status']=='no_match' and not result.get('query') and not result.get('cache_hit'):
                research['request_count']=max(0,research.get('request_count',1)-1)
            displayed=False
            current=p['live'].get('research_scene')
            suitable = [s for s in items if fits[s['id']]['automatic']]
            if need and need['goal'] == 'source':
                suitable.sort(key=lambda s: s['kind'] != 'evidence')
            chosen = suitable[0] if suitable else None
            if items and not chosen:
                research['message'] = fits[items[0]['id']]['reason'] + ' Retained backstage; the current visual stays.'
            same_source=bool(current and chosen and current['object_id']==chosen['object_id'])
            if chosen and fresh and result.get('allow_auto_display',True) and (same_source or self.studio.clock()-p['live']['last_change']>=self.studio.dwell_s):
                p['live']['research_scene']=copy.deepcopy(chosen)
                p['live']['attention']=None
                if not current or current['id']!=chosen['id']:p['live']['last_change']=self.studio.clock()
                p['live']['decision']={'action':'SHOW_RESEARCH','scene_id':chosen['id'],
                    'reason':'Showing a related web source; retrieved live, not presenter-reviewed.'}
                displayed=True
                job['displayed']=True
                if chosen['id'] not in job.setdefault('displayed_scene_ids',[]):job['displayed_scene_ids'].append(chosen['id'])
            if items:
                job.setdefault('first_result_at',self.clock())
                research['first_result_latency_s']=job['first_result_at']-job.get('queued_at',job['first_result_at'])
            if not final:
                job['progress_result']=copy.deepcopy(result)
            entry={'completed_at':self.clock(),'query':result.get('query',''),'request_id':job['request_id'],'final':final,
                'status':result['status'],'package_hash':job['package_hash'],'displayed_automatically':job.get('displayed',displayed),
                'cache_hit':result.get('cache_hit',False),'cache_kind':result.get('cache_kind'),
                'reuse_source_age_s':result.get('reuse_source_age_s'),
                'displayed_scene_ids':list(job.get('displayed_scene_ids',[])),
                'first_result_at':job.get('first_result_at'),'first_result_latency_s':(job['first_result_at']-job['queued_at']) if 'first_result_at' in job and 'queued_at' in job else None,
                'timing':result.get('timing',{}),
                'allow_auto_display':result.get('allow_auto_display',True),
                'utterance':job['context']['utterance'],'recent_past':job['context']['recent_past'],
                'plan_decision':result.get('plan_decision',{}),'classifier_calls':result.get('classifier_calls',[]),
                'explanation_need':copy.deepcopy(need),'presentation_fit':fits,
                'message':result.get('message',''),'errors':result.get('errors',[]),
                'sources':[{'scene_id':s['id'],'url':s['web_source']['url'],'image_url':s['web_source'].get('image_url'),
                            'asset_sha256':s.get('asset',{}).get('sha256'),'quote':s['source_refs'][0]['quote']} for s in items]}
            previous_entry=next((h for h in p.setdefault('research_history',[]) if h.get('request_id')==job['request_id']),None)
            if previous_entry is not None:previous_entry.update(entry)
            else:p['research_history'].append(entry)
            p['research_history']=p['research_history'][-50:]

    def work(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.pending is not None)
                if self.closed:return
                job,self.pending=self.pending,None;self.active=job
            try:
                with self.store.change(job['pid']) as p:
                    if not self.valid(job,p):continue
                    p['live']['research']['status']='searching'
                with self.condition:cached=self.cache.get(job['cache_key'])
                if cached and self.clock()-cached[0]<300:
                    result={**copy.deepcopy(cached[1]),'cache_hit':True,'cache_kind':'exact_utterance'}
                elif job.get('reuse'):
                    created,original=job['reuse']
                    if self.clock()-created>=300:
                        result={'status':'no_match','query':original['query'],'items':[],
                                'message':'The cached source expired; fresh research is needed.'}
                    else:
                        checked=self.backend.revalidate(job['context'],original,job['cancel'])
                        if checked['status']=='ready' and self.clock()-created<300:
                            # Only the quotation was rechecked. Do not silently
                            # give an old image authority in a different context.
                            items=copy.deepcopy([s for s in original['items'] if s['kind']=='evidence'])[:1]
                            for scene in items:
                                scene['web_source'].update(revalidated_at=self.clock(),
                                    revalidation_support_probability=checked.get('plan_decision',{}).get('source_support_probability'),
                                    revalidation_support_scope=checked.get('plan_decision',{}).get('source_support_scope'))
                            result={**copy.deepcopy(original),**checked,'items':items,
                                'cache_hit':True,'cache_kind':'topic_revalidated','reuse_source_age_s':self.clock()-created,
                                'message':'Previously retrieved source rechecked for the current explanation.'}
                        elif checked['status']=='ready':
                            result={'status':'no_match','query':original['query'],'items':[],
                                    'message':'The cached source expired during revalidation.'}
                        else:result=checked
                else:
                    if hasattr(self.backend,'run_progressive'):
                        result=self.backend.run_progressive(job['context'],job['cancel'],lambda partial:self.complete(job,partial,final=False))
                    else:result=self.backend.run(job['context'],job['cancel'])
                    if result.get('status')=='ready' and not job['cancel'].is_set():
                        with self.condition:
                            self.cache[job['cache_key']]=(self.clock(),copy.deepcopy(result))
                            self.cache.move_to_end(job['cache_key'])
                            while len(self.cache)>8:self.cache.popitem(last=False)
                self.complete(job,result)
            except Exception:
                fallback={**job['progress_result'],'errors':[*job['progress_result'].get('errors',[]),'Optional enrichment unavailable.']} if job.get('progress_result') else {'status':'error','message':'Live research was unavailable or exceeded its budget. Prepared following continues.','items':[]}
                try:self.complete(job,fallback)
                except (KeyError,ValueError):pass
            finally:
                with self.condition:
                    if self.active is job:self.active=None

    def close(self):
        with self.condition:
            self.closed=True;self.pending=None
            if self.active:self.active['cancel'].set()
            self.condition.notify_all()
        self.worker.join(3)


def main():
    if '--child' not in sys.argv:raise SystemExit('Use this module through the local studio research worker.')
    try:
        from .research_sources import procure,revalidate
        context=json.loads(sys.stdin.buffer.read(100_001))
        result=revalidate(context) if context.get('mode')=='reuse' else procure(context)
    except Exception:
        result={'status':'error','message':'The research provider or source service was unavailable.','items':[]}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main()
