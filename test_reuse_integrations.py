"""Boundaries for upstream speech stabilization and source figure ingestion."""
import array
import base64
import copy
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from presenter.engine import Store,Studio
from presenter.materials import ingest
from presenter.pdf_figures import DoclingFigures
from presenter.server import material_sources
from presenter.speech_stability import StableTranscript
from test_supplied_visuals import png


def pdf_fixture():
    content=b'BT /F1 16 Tf 50 700 Td (A cooling mechanism transfers heat.) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data=b'%PDF-1.4\n';offsets=[0]
    for index,obj in enumerate(objects,1):
        offsets.append(len(data));data+=f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'
    data+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


class SpeechStabilization(unittest.TestCase):
    def test_only_confirmed_text_is_emitted_and_repeated_snapshot_is_quiet(self):
        model=StableTranscript();pcm=array.array('h',[400]*16000).tobytes()
        text,meta=model.observe('At the high setting.',0,pcm,1.,1.5)
        self.assertEqual(text,'');self.assertFalse(meta['has_new_stable_text'])
        text,meta=model.observe('At the high setting.',1,pcm,2.,2.5)
        self.assertIn('high setting',text)
        text,_=model.observe('At the high setting.',2,pcm,3.,3.5)
        self.assertEqual(text,'')

    def test_new_acoustic_segment_does_not_inherit_old_stable_words(self):
        model=StableTranscript();pcm=array.array('h',[400]*16000).tobytes()
        model.observe('At the high setting.',0,pcm,1.,1.5)
        model.observe('At the high setting.',1,pcm,2.,2.5)
        text,meta=model.observe('Electrical power consumption.',5,pcm,6.,6.5)
        self.assertEqual(meta['segment'],2);self.assertNotIn('high',text)


class FigureBoundaries(unittest.TestCase):
    def test_invalid_inputs_and_cancel_never_launch_optional_worker(self):
        extractor=DoclingFigures()
        with patch('presenter.pdf_figures.subprocess.Popen') as launch:
            for pages in ((0,1),(1,4),(True,2),None,({},2)):
                with self.assertRaises(ValueError):extractor.extract('x.pdf',b'%PDF-',pages=pages)
            with self.assertRaises(ValueError):extractor.extract('x.pdf',b'not pdf')
            cancel=threading.Event();cancel.set()
            with self.assertRaises(TimeoutError):extractor.extract('x.pdf',b'%PDF-',cancel=cancel)
            launch.assert_not_called()

    def test_cache_is_bound_to_source_bytes_and_does_not_grant_visual_review(self):
        extractor=DoclingFigures()
        candidate={'source_sha256':'fixture','figures':[{'provenance':{'pixels_semantically_verified':False}}],'wall_s':.1}
        with patch.object(extractor,'_extract',side_effect=lambda *a,**k:copy.deepcopy(candidate)) as worker:
            first=extractor.extract('x.pdf',b'%PDF-one');cached=extractor.extract('x.pdf',b'%PDF-one')
            self.assertFalse(first['cache_hit']);self.assertTrue(cached['cache_hit'])
            cached['figures'][0]['provenance']['pixels_semantically_verified']=True
            self.assertFalse(extractor.extract('x.pdf',b'%PDF-one')['figures'][0]['provenance']['pixels_semantically_verified'])
            extractor.extract('x.pdf',b'%PDF-two')
            self.assertEqual(worker.call_count,2)

    @unittest.skipUnless(shutil.which('pdftotext'),'PDF import requires pdftotext')
    def test_extracted_figure_enters_draft_sources_and_requires_normal_approval(self):
        image=ingest('mechanism.png',png(),'Extracted source figure; review its meaning before approval.')
        image['provenance']={'page':1,'pixels_semantically_verified':False}
        class Extractor:
            def extract(self,name,data,*,pages):return {'figures':[image]}
        raw=[{'name':'source.pdf','base64':base64.b64encode(pdf_fixture()).decode(),'extract_figures':{'pages':[1,1]}}]
        with self.assertRaises(ValueError):material_sources(raw)
        sources=material_sources(raw,Extractor())
        self.assertEqual(len(sources),2);self.assertEqual(sources[1]['asset'],image['asset'])
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);studio=Studio(store)
            p=store.create(title='Cooling',brief='Explain heat transfer.',audience='Students',sources=sources,provider='outline')
            p=studio.prepare(p['id'],background=False)
            self.assertIsNone(p['approval']);self.assertFalse(p['live']['active'])
            self.assertTrue(any(scene['kind']=='image' for scene in p['plan']['scenes']))


if __name__=='__main__':unittest.main()
