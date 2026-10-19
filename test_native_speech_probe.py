"""Speech-probe scoring and authenticated research-image review boundaries."""
import base64
import copy
import hashlib
import struct
import threading
import time
import unittest
import zlib

from presenter.native_speech_probe import summarize
from presenter.research_bridge import ResearchBridge, retrieved_scenes
from presenter.explanation import presentation_fit, explanation_need


class SpeechScoring(unittest.TestCase):
    def test_partial_causal_question_does_not_inherit_a_quantity_intent(self):
        self.assertEqual(explanation_need('How does a heat pipe move using')['goal'],'mechanism')
        self.assertEqual(explanation_need('How much flow was measured?')['goal'],'quantity')

    def test_repeated_detour_does_not_reset_the_cold_latency(self):
        script=[{'start_s':42,'end_s':46,'condition':'unprepared_mechanism'},
                {'start_s':106,'end_s':110,'condition':'unprepared_mechanism'}]
        events=[{'at_s':107,'scene_id':'heat','first_changed_pixels_at_s':107.1}]
        row=summarize(script,events,{'heat':{'kind':'image','web_source':{'url':'https://example.edu'}}})[1]
        self.assertAlmostEqual(row['episode_start_to_pixels_s'],65.1)

    def test_baseline_and_late_or_wrong_visuals_do_not_count(self):
        script=[{'start_s':1,'end_s':2,'condition':'prepared_baseline'},
                {'start_s':7,'end_s':8,'condition':'prepared_focus_high'},
                {'start_s':14,'end_s':16,'condition':'prepared_comparison'}]
        events=[{'at_s':0,'scene_id':'flow','first_changed_pixels_at_s':.01},
                {'at_s':9,'scene_id':'flow','attention':{'annotation_id':'datum_0'},'first_changed_pixels_at_s':9.1},
                {'at_s':17,'scene_id':'flow','attention':{'annotation_id':'datum_2'},'first_changed_pixels_at_s':17.1}]
        self.assertFalse(any(row['changed_visual_observed'] for row in summarize(script,events,{'flow':{'y':'Flow_L_min'}})))
        events.insert(2,{'at_s':10,'scene_id':'flow','attention':{'annotation_id':'datum_2'},'first_changed_pixels_at_s':10.1})
        row=summarize(script,events,{'flow':{'y':'Flow_L_min'}})[1]
        self.assertAlmostEqual(row['cue_end_to_pixels_s'],2.1)


class PixelReview(unittest.TestCase):
    def source(self):
        def chunk(kind,body):
            return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body))
        data=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+
              chunk(b'IDAT',zlib.compress(b'\0\xff\0\0'))+chunk(b'IEND',b''))
        return {'url':'https://example.edu/heat','title':'Test mechanism',
            'quote':'A source quotation fixture explains heat transport by phase change.',
            'image':{'name':'fixture.png','base64':base64.b64encode(data).decode(),
                'artist':'Test fixture author','license':'Test fixture only','source_url':'https://example.edu/heat.png',
                'visual_review':{'method':'connected_agent_pixel_inspection','sha256':hashlib.sha256(data).hexdigest(),
                    'reviewer':'Test fixture reviewer','question':'How does a heat pipe move heat?',
                    'observed_content':'Test-only attestation; this one-pixel fixture is not an explanation.',
                    'explanatory_fit':'Protocol test only, not a visual-quality judgment.'}}}

    def test_review_is_bound_to_bytes_and_is_explicitly_an_attestation(self):
        source=self.source();scene=retrieved_scenes([source])[0]
        self.assertTrue(scene['web_source']['pixels_semantically_verified'])
        self.assertFalse(scene['web_source']['independently_verified_by_app'])
        self.assertEqual(scene['web_source']['visual_verification'],'connected_agent_attested_pixels')
        need={'goal':'mechanism','question':'How does it work?'}
        self.assertTrue(presentation_fit(scene,need)['automatic'])
        source['image'].pop('visual_review');scene=retrieved_scenes([source])[0]
        self.assertFalse(presentation_fit(scene,need)['automatic'])
        source=self.source();source['image']['visual_review']['sha256']='0'*64
        with self.assertRaises(ValueError):retrieved_scenes([source])

    def test_a_review_for_a_different_question_cannot_answer_the_current_job(self):
        bridge=ResearchBridge(timeout_s=2);result=[]
        worker=threading.Thread(target=lambda:result.append(bridge.run(
            {'utterance':'How does a heat pipe move heat?'},threading.Event())))
        worker.start()
        deadline=time.monotonic()+1
        while bridge.snapshot() is None and time.monotonic()<deadline:time.sleep(.005)
        job=bridge.snapshot();source=self.source();wrong=copy.deepcopy(source)
        wrong['image']['visual_review']['question']='Explain something entirely different.'
        try:
            with self.assertRaises(ValueError):bridge.supply(job['id'],[wrong])
            bridge.supply(job['id'],[source]);worker.join(1)
            self.assertEqual(result[0]['status'],'ready')
            with self.assertRaises(ValueError):bridge.supply(job['id'],[source])
        finally:worker.join(3)


if __name__=='__main__':unittest.main()
