"""Optional bounded Docling extraction, producing source-linked visual candidates.

The base backend stays stdlib-only. Models live in a separate subprocess and
the exported figures receive no automatic semantic-review authority.
"""
import argparse
import base64
from collections import OrderedDict
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from .materials import ingest


class DoclingFigures:
    def __init__(self,python='.venv-research/bin/python',timeout_s=45):
        if isinstance(timeout_s,bool) or not math.isfinite(timeout_s) or not 0<timeout_s<=180:
            raise ValueError('Use a finite extraction budget of at most 180 seconds.')
        self.python=str(Path(python).absolute());self.timeout_s=timeout_s
        self.cache=OrderedDict();self.lock=threading.Lock()

    def extract(self,name,data,*,pages=(1,3),cancel=None):
        if not isinstance(data,bytes) or not data.startswith(b'%PDF-') or len(data)>4_000_000:
            raise ValueError('Figure extraction requires a PDF under 4 MB.')
        if not isinstance(pages,(list,tuple)) or len(pages)!=2:
            raise ValueError('Select the first and last PDF page.')
        first,last=pages
        if any(isinstance(v,bool) or not isinstance(v,int) for v in pages) or not 1<=first<=last<=500 or last-first>=3:
            raise ValueError('Select up to three consecutive PDF pages, from 1 to 500.')
        if cancel is not None and cancel.is_set():raise TimeoutError('Figure extraction cancelled.')
        if not self.lock.acquire(blocking=False):raise ValueError('A PDF figure extraction is already running.')
        try:
            # A cached figure is still an unreviewed candidate. This cache grants
            # no display authority and never reuses results for changed bytes.
            key=(hashlib.sha256(data).hexdigest(),tuple(pages),Path(name).name)
            if key in self.cache:
                self.cache.move_to_end(key)
                return {**copy.deepcopy(self.cache[key]),'cache_hit':True,'wall_s':0.0}
            result=self._extract(name,data,pages=pages,cancel=cancel)
            result.update(cache_hit=False,extraction_wall_s=result['wall_s'])
            self.cache[key]=copy.deepcopy(result)
            while len(self.cache)>4:self.cache.popitem(last=False)
            return result
        finally:self.lock.release()

    def _extract(self,name,data,*,pages,cancel):
        first,last=pages
        cancel=cancel or threading.Event()
        payload=json.dumps({'name':Path(name).name,'pdf':base64.b64encode(data).decode(),'pages':[first,last]}).encode()
        env={k:v for k,v in os.environ.items() if not k.endswith(('API_KEY','TOKEN'))}
        env.update(OMP_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false')
        with tempfile.TemporaryFile() as source,tempfile.TemporaryFile() as output:
            source.write(payload);source.seek(0)
            process=subprocess.Popen([self.python,'-m','presenter.pdf_figures','--child'],
                cwd=Path(__file__).resolve().parent.parent,env=env,stdin=source,stdout=output,stderr=subprocess.DEVNULL)
            started=time.monotonic()
            try:
                while process.poll() is None:
                    if cancel.wait(.03):raise TimeoutError('Figure extraction cancelled.')
                    if time.monotonic()-started>self.timeout_s:raise TimeoutError('Docling figure extraction exceeded its budget.')
                    if os.fstat(output.fileno()).st_size>6_000_000:raise ValueError('Extracted figures exceed the output limit.')
                output.seek(0);raw=output.read(6_000_001)
                if len(raw)>6_000_000 or process.returncode:raise ValueError('Docling extraction failed; check optional research dependencies and model availability.')
                result=json.loads(raw)
                if result.get('source_sha256')!=hashlib.sha256(data).hexdigest():raise ValueError('Extracted figure source mismatch.')
                if not isinstance(result.get('figures'),list) or len(result['figures'])>8:raise ValueError('Invalid extracted figure collection.')
                materials=[]
                for figure in result['figures']:
                    if figure.get('source_sha256')!=result['source_sha256'] or not first<=figure.get('page',0)<=last:
                        raise ValueError('Figure provenance does not match the selected source pages.')
                    image=base64.b64decode(figure.pop('base64'),validate=True)
                    material=ingest(figure['name'],image,figure['caption'] or f'Extracted figure on PDF page {figure["page"]}. Review its meaning before use.')
                    material['provenance']={**figure,'extractor':'Docling','version':result['docling_version'],
                        'pixels_semantically_verified':False,'review_status':'unreviewed_extraction'}
                    materials.append(material)
                return {**result,'figures':materials,'wall_s':time.monotonic()-started}
            finally:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)


def child():
    # This is optional-dependency code, never imported by the ordinary server.
    import importlib.metadata
    import torch
    from docling_core.types.doc import PictureItem
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.accelerator_options import AcceleratorOptions,AcceleratorDevice
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter,PdfFormatOption
    torch.set_num_threads(1)
    payload=json.loads(sys.stdin.buffer.read(5_500_000));data=base64.b64decode(payload['pdf'],validate=True)
    digest=hashlib.sha256(data).hexdigest()
    options=PdfPipelineOptions(do_ocr=False,do_table_structure=False,
        generate_picture_images=True,generate_page_images=True,images_scale=1.5,
        accelerator_options=AcceleratorOptions(num_threads=1,device=AcceleratorDevice.CPU))
    converter=DocumentConverter(allowed_formats=[InputFormat.PDF],format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)})
    with tempfile.TemporaryDirectory(prefix='presenter-docling-') as folder:
        pdf=Path(folder)/'source.pdf';pdf.write_bytes(data)
        result=converter.convert(pdf,page_range=tuple(payload['pages']))
        figures=[]
        for element,_ in result.document.iterate_items():
            if not isinstance(element,PictureItem) or not element.prov:continue
            image=element.get_image(result.document)
            if image is None:continue
            # Bound pixels and encoded bytes without changing crop geometry.
            image=image.convert('RGB');image.thumbnail((1600,1200))
            out=io.BytesIO();image.save(out,format='PNG')
            if out.tell()>512_000:
                out=io.BytesIO();image.save(out,format='JPEG',quality=88)
            if out.tell()>512_000:continue
            prov=element.prov[0]
            suffix='.png' if out.getvalue().startswith(b'\x89PNG') else '.jpg'
            figures.append({'name':Path(payload['name']).stem+f'-page-{prov.page_no}-figure-{len(figures)+1}'+suffix,
                'page':prov.page_no,'bbox':prov.bbox.model_dump(mode='json'),
                'caption':element.caption_text(result.document)[:1200],
                'figure_ref':element.self_ref,'source_sha256':digest,
                'base64':base64.b64encode(out.getvalue()).decode()})
            if len(figures)>=8:break
    print(json.dumps({'schema':'live_presenter.docling_figures.v1','source_sha256':digest,
        'docling_version':importlib.metadata.version('docling-slim'),'pages':payload['pages'],
        'figures':figures},allow_nan=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--pdf',type=Path)
    parser.add_argument('--out-dir',type=Path)
    parser.add_argument('--first-page',type=int,default=1)
    parser.add_argument('--last-page',type=int,default=3)
    parser.add_argument('--python',default='.venv-research/bin/python')
    parser.add_argument('--timeout-s',type=float,default=45)
    args=parser.parse_args()
    if args.child:
        try:child()
        except Exception as error:
            # The worker has no provider credentials. Bound diagnostics to error
            # types and missing module names; don't echo PDF text or remote data.
            print(json.dumps({'error_type':type(error).__name__,
                'missing_module':getattr(error,'name',None)}),flush=True)
            raise SystemExit(1)
        return
    if not args.pdf or not args.out_dir:parser.error('Use --pdf and --out-dir.')
    folder=args.out_dir;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'figures.json').exists():parser.error('Use a new extraction directory.')
    result=DoclingFigures(args.python,args.timeout_s).extract(args.pdf.name,args.pdf.read_bytes(),pages=(args.first_page,args.last_page))
    for material in result['figures']:
        encoded=material['asset']['data_url'].split(',',1)[1]
        (folder/material['name']).write_bytes(base64.b64decode(encoded))
    (folder/'figures.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'figures':len(result['figures']),'wall_s':result['wall_s'],'output':str(folder/'figures.json')}),flush=True)


if __name__=='__main__':main()
