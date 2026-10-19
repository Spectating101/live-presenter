"""Operator-authenticated handoff to an active web-capable research agent."""
import base64
import copy
import hashlib
import threading
import time
import uuid

from .materials import ingest, normalized
from .research_sources import public_url


def retrieved_scenes(raw):
    """The agent attests retrieval; these are never labeled presenter-approved."""
    if not isinstance(raw,list) or not 1<=len(raw)<=2:raise ValueError('Supply one or two retrieved sources.')
    scenes=[]
    for source in raw:
        url=public_url(source['url']);title=normalized(source['title'])[:160];quote=normalized(source['quote'])[:600]
        if len(quote)<24 or not title:raise ValueError('Each source needs a title and an actual retrieved quotation.')
        digest=hashlib.sha256((url+quote).encode()).hexdigest()[:16]
        origin={'url':url,'provider':'Connected research agent','retrieved':True,'presenter_reviewed':False,
                'retrieved_at':time.time(),
                'retrieval_attestation':'operator_agent','independently_verified_by_app':False}
        scene={'id':'web_agent_'+digest,'concept_id':'web_topic_'+digest,'object_id':'web_topic_'+digest,
               'kind':'evidence','title':title,'body':[],'source_refs':[{'unit_id':'web_'+digest,'source_name':title,'quote':quote}],
               'grounding':'agent_attested_source_quote','review_status':'live_retrieved','web_source':origin}
        image=source.get('image')
        if image:
            if len(image.get('base64',''))>690_000:raise ValueError('Retrieved image is too large.')
            if not image.get('artist') or not image.get('license') or not image.get('source_url'):
                raise ValueError('Retrieved images need creator, license and file-source attribution.')
            data=base64.b64decode(image['base64'],validate=True)
            material=ingest(image['name'],data,image.get('description',''))
            if not material.get('asset'):raise ValueError('Retrieve a PNG/JPEG image.')
            scene.update(id=scene['id']+'_'+material['sha256'][:12],kind='image',asset=material['asset'],grounding='agent_attested_image',
                web_source={**origin,'image_url':public_url(image['source_url']),'artist':normalized(image['artist'])[:180],
                            'image_license':normalized(image['license'])[:100],
                            'image_license_url':public_url(image['license_url']) if image.get('license_url') else '',
                            'pixels_semantically_verified':False})
        scenes.append(scene)
    return scenes


class ResearchBridge:
    def __init__(self,timeout_s=40):
        self.timeout_s=timeout_s;self.lock=threading.Lock();self.job=None

    def snapshot(self):
        with self.lock:
            return {k:copy.deepcopy(self.job[k]) for k in ('id','context','created_at')} if self.job and not self.job['cancel'].is_set() else None

    def supply(self,job_id,sources,status='ready'):
        if status not in {'ready','no_match'}:raise ValueError('Return ready or no_match.')
        scenes=retrieved_scenes(sources) if status=='ready' else []
        with self.lock:
            job=self.job
            if not job or job['id']!=job_id or job['cancel'].is_set() or job['result'] is not None:
                raise ValueError('This research request expired, was answered or was superseded.')
            job['result']={'status':status,'query':job['context']['utterance'],'items':scenes,'papers':[],
                           'message':'No suitable source was found.' if status=='no_match' else 'Related material found by the connected research agent.',
                           'provider_scope':['Connected web-capable research agent']}
            job['ready'].set()

    def run(self,context,cancel):
        job={'id':uuid.uuid4().hex,'context':copy.deepcopy(context),'created_at':time.time(),'ready':threading.Event(),'cancel':cancel,'result':None}
        with self.lock:self.job=job
        deadline=time.monotonic()+self.timeout_s
        try:
            while not job['ready'].wait(.04):
                if cancel.is_set() or time.monotonic()>deadline:raise TimeoutError('Connected research agent did not answer the current request.')
            if cancel.is_set():raise TimeoutError('Research superseded or stopped.')
            return job['result']
        finally:
            with self.lock:
                if self.job is job:self.job=None
