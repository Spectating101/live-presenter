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

from .language import tokens


class ResearchProcess:
    def __init__(self, timeout_s=25,command=None):self.timeout_s,self.command=timeout_s,command

    def run(self, context, cancelled):
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
                while process.poll() is None:
                    if cancelled.wait(.04):raise TimeoutError('Research superseded or stopped.')
                    if time.monotonic()>deadline:raise TimeoutError(f'Research exceeded its {self.timeout_s:g}-second budget.')
                    if os.fstat(output.fileno()).st_size>2_000_000:raise ValueError('Research output exceeded its limit.')
                if os.fstat(output.fileno()).st_size>2_000_000:raise ValueError('Research output exceeded its limit.')
                output.seek(0);result=json.loads(output.read())
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

    def observe(self,pid,utterance,recommendation,*,force=False,generation=None,seq=None):
        p=self.store.read(pid)
        live=p['live']
        if not live['active'] or live['locked'] or not live.get('research_enabled'):return
        if generation is not None and live['generation']!=generation:return
        if seq is not None and live['last_seq']!=seq:return
        package=self.studio.package(p)
        known=tokens(' '.join(c['title']+' '+c['summary']+' '+' '.join(c['aliases']) for c in package['concepts']))
        recent=[r['text'] for r in live['transcript'][-4:-1] if self.clock()-r['at']<=8]
        from .research_sources import spoken_context
        topic_speech=spoken_context({'utterance':utterance,'recent_past':recent})
        novel=tokens(topic_speech)-known-{'compared','instead','please','find','show','explain','could','would','about','tell'}
        prepared=bool(recommendation.get('scene_id') and recommendation.get('score',0)>=.88)
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
        if continuation and research.get('request_id') and research.get('status') in {'queued','searching'}:
            with self.store.change(pid) as current:
                if current['live'].get('research',{}).get('request_id')==research['request_id']:
                    current['live']['research']['last_heard']=now
                    current['live']['research']['novel']=sorted(novel)
            return
        if previous and novel and not continuation and research.get('request_id') and research.get('status') in {'queued','searching'}:
            with self.store.change(pid) as current:
                if current['live'].get('research',{}).get('request_id')==research['request_id']:
                    current['live']['research'].update(request_id='',status='idle',message='The topic changed; earlier research will not take the stage.')
            self.invalidate(pid)
        if not force and now-research.get('last_requested',0)<self.cooldown_s:return
        cache_key=(p['approval']['package_hash'],tuple(sorted(tokens(utterance))))
        with self.condition:cached=self.cache.get(cache_key)
        warm=bool(cached and now-cached[0]<300)
        if research.get('request_count',0)>=12 and not warm:
            with self.store.change(pid) as current:current['live']['research'].update(status='limit',message='This rehearsal has used its twelve research requests. Prepared following continues.')
            return
        if research.get('assessment_count',0)>=60 and not warm:
            with self.store.change(pid) as current:current['live']['research'].update(status='limit',message='This rehearsal reached its sixty topic assessments. Prepared following continues.')
            return
        request_id=uuid.uuid4().hex
        context={'title':package['title'],'brief':p['brief'],'concepts':[{k:c[k] for k in ('title','summary','aliases')} for c in package['concepts']],
                 'utterance':utterance[:600],'recent_past':recent}
        job={'pid':pid,'generation':live['generation'],'package_hash':p['approval']['package_hash'],
             'request_id':request_id,'context':context,'cancel':threading.Event(),
             'cache_key':cache_key}
        with self.store.change(pid) as current:
            if (current['live']['generation']!=job['generation'] or not current['live'].get('research_enabled')
                    or not current['live']['active'] or current['live']['locked']
                    or (seq is not None and current['live']['last_seq']!=seq)):return
            current['live']['research']={**research,'status':'queued','request_id':request_id,'novel':sorted(novel),
              'last_heard':now,'last_requested':now,'request_count':research.get('request_count',0)+int(not warm),
              'assessment_count':research.get('assessment_count',0)+int(not warm),
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

    def complete(self,job,result):
        with self.store.change(job['pid']) as p:
            if not self.valid(job,p):return
            self.studio.package(p)
            research=p['live']['research'];fresh=self.clock()-research['last_heard']<=self.fresh_s
            items=result.get('items',[])[:2]
            research.update(status=result['status'],query=result.get('query',''),items=copy.deepcopy(items),
              papers=result.get('papers',[])[:3],completed_at=self.clock(),errors=result.get('errors',[]),
              message=result.get('message') or ('Related material found.' if fresh else 'Related material found after the topic expired; retained backstage.'),
              cache_hit=result.get('cache_hit',False),provider_scope=result.get('provider_scope',[]))
            research['classifier_calls']=result.get('classifier_calls',[])
            research['plan_decision']=result.get('plan_decision',{})
            if result['status']=='no_match' and not result.get('query') and not result.get('cache_hit'):
                research['request_count']=max(0,research.get('request_count',1)-1)
            displayed=False
            if items and fresh and self.studio.clock()-p['live']['last_change']>=self.studio.dwell_s:
                p['live']['research_scene']=copy.deepcopy(items[0])
                p['live']['last_change']=self.studio.clock()
                p['live']['decision']={'action':'SHOW_RESEARCH','scene_id':items[0]['id'],
                    'reason':'Showing a related web source; retrieved live, not presenter-reviewed.'}
                displayed=True
            p.setdefault('research_history',[]).append({'completed_at':self.clock(),'query':result.get('query',''),
                'status':result['status'],'package_hash':job['package_hash'],'displayed_automatically':displayed,
                'utterance':job['context']['utterance'],'recent_past':job['context']['recent_past'],
                'plan_decision':result.get('plan_decision',{}),'classifier_calls':result.get('classifier_calls',[]),
                'message':result.get('message',''),'errors':result.get('errors',[]),
                'sources':[{'scene_id':s['id'],'url':s['web_source']['url'],'image_url':s['web_source'].get('image_url'),
                            'asset_sha256':s.get('asset',{}).get('sha256'),'quote':s['source_refs'][0]['quote']} for s in items]})
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
                    result={**copy.deepcopy(cached[1]),'cache_hit':True}
                else:
                    result=self.backend.run(job['context'],job['cancel'])
                    if result.get('status')=='ready' and not job['cancel'].is_set():
                        with self.condition:
                            self.cache[job['cache_key']]=(self.clock(),copy.deepcopy(result))
                            self.cache.move_to_end(job['cache_key'])
                            while len(self.cache)>8:self.cache.popitem(last=False)
                self.complete(job,result)
            except Exception:
                try:self.complete(job,{'status':'error','message':'Live research was unavailable or exceeded its budget. Prepared following continues.','items':[]})
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
        from .research_sources import procure
        context=json.loads(sys.stdin.buffer.read(100_001))
        result=procure(context)
    except Exception:
        result={'status':'error','message':'The research provider or source service was unavailable.','items':[]}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main()
