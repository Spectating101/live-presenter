"""Procure material from the brief before the reviewable visual package is built."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import threading
import time

from .materials import ingest


def supplied(project):
    return [s for s in project['sources'] if not s.get('retrieved_for_preparation')]


def signature(project):
    value={'title':project['title'],'brief':project['brief'],'audience':project['audience'],
           'sources':[s['sha256'] for s in supplied(project)]}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class PreparationResearch:
    def __init__(self,backend):
        self.backend=backend;self.lock=threading.Lock();self.active=set();self.closed=False

    def needs(self,project):
        return project.get('preparation_research',{}).get('input_signature')!=signature(project)

    def enrich(self,project):
        result=copy.deepcopy(project);original=supplied(project);fingerprint=signature(project)
        result['sources']=original
        record={'input_signature':fingerprint,'query':project['title'],'started_at':time.time(),
                'sources':[],'status':'searching','future_speech_used':False}
        result['preparation_research']=record
        if len(original)>=8:
            record.update(status='limit',message='All material slots are occupied; online preparation was skipped.')
            return result
        cancel=threading.Event()
        with self.lock:
            if self.closed:cancel.set()
            self.active.add(cancel)
        try:
            response=self.backend.run({'mode':'preparation','topic':project['title'][:160],
                'title':project['title'],'brief':project['brief'],'utterance':project['title']+'. '+project['brief'],
                'concepts':[],'recent_past':[]},cancel)
            record['status']=response['status'];record['classifier_calls']=response.get('classifier_calls',[])
            record['errors']=response.get('errors',[])
            # Import an actual source quotation first; an optional image is a
            # separate material with its original source and license metadata.
            items=sorted(response.get('items',[]),key=lambda s:s['kind']=='image')
            imported=set(s['id'] for s in original)
            for scene in items:
                if len(result['sources'])>=8:break
                origin=copy.deepcopy(scene['web_source']);quote=scene['source_refs'][0]['quote']
                if scene['kind']=='image':
                    asset=scene['asset'];data=base64.b64decode(asset['data_url'].split(',',1)[1],validate=True)
                    suffix='.png' if asset['mime']=='image/png' else '.jpg'
                    material=ingest(Path(scene['title'][:100]).stem+suffix,data,scene['title']+'. '+quote)
                else:
                    material=ingest(scene['title'][:100]+'.md',('# '+scene['title']+'\n\n'+quote).encode())
                if material['id'] in imported:continue
                if sum(s['characters'] for s in result['sources'])+material['characters']>130_000:continue
                if sum(len(s.get('asset',{}).get('data_url','')) for s in result['sources'])+len(material.get('asset',{}).get('data_url',''))>2_000_000:continue
                material.update(retrieved_for_preparation=True,web_source=origin)
                result['sources'].append(material);imported.add(material['id'])
                record['sources'].append({'id':material['id'],'sha256':material['sha256'],'url':origin['url'],
                    'image_url':origin.get('image_url'),'image_license':origin.get('image_license')})
            record['message']=('Online material added to the draft for review.' if record['sources'] else
                               'No suitable online material was added. Supplied material remains available.')
        except Exception:
            record.update(status='error',message='Online preparation research was unavailable. Supplied material remains available.')
        finally:
            record['completed_at']=time.time()
            with self.lock:self.active.discard(cancel)
        return result

    def close(self):
        with self.lock:
            self.closed=True
            for event in self.active:event.set()
