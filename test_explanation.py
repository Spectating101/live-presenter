"""A stable illustration, source-linked attention and purpose-aware procurement."""
import copy
import tempfile
import unittest

from presenter.engine import Conflict, Store, Studio
from presenter.explanation import explanation_need, focus_target, media_query, presentation_fit
from presenter.materials import ingest
from presenter.planning import PlanError, validate_plan
from test_supplied_visuals import png


def fixture():
    notes = ingest('Mechanism.md', b'The pump impeller circulates the liquid. The radiator fins transfer heat to air.')
    asset = ingest('Reviewed diagram.png', png(300, 180), 'Synthetic placement fixture, not a quality demonstration.')
    quote = notes['units'][0]['text']
    targets = [
        {'id':'pump','label':'Pump impeller','x':.2,'y':.5,'label_x':.3,'label_y':.25,
         'cue_phrases':['pump impeller'], 'quote':'The pump impeller circulates the liquid.'},
        {'id':'radiator','label':'Radiator fins','x':.8,'y':.5,'label_x':.7,'label_y':.25,
         'cue_phrases':['radiator fins'], 'quote':'The radiator fins transfer heat to air.'},
    ]
    raw = {'concepts':[{'title':'Cooling mechanism', 'summary':quote, 'aliases':['cooling mechanism'],
           'explanation':{'goal':'mechanism','question':'How does heat leave the loop?', 'rationale':'Show spatial relationships and direct attention within the image.'},
           'source_refs':[{'unit_id':notes['units'][0]['id'],'quote':quote}],
           'visuals':[{'kind':'annotated_image','asset_id':asset['id'],'annotations':targets}]}]}
    return {'title':'Cooling','audience':'Novices','sources':[notes,asset]}, raw


class ExplanationDesign(unittest.TestCase):
    def test_procurement_is_driven_by_the_explanation_goal(self):
        for words, goal in [('How does a heat pipe work?', 'mechanism'), ('Compare heat pipes versus pumps.', 'comparison'),
                            ('How much flow was measured?', 'quantity'),
                            ('Where is the launch site?', 'location'), ('Show the source for the efficiency claim.', 'source')]:
            with self.subTest(goal=goal):
                need=explanation_need(words,'Students')
                self.assertEqual(need['goal'],goal)
                self.assertNotIn('definition',need['preferred_media'])
        self.assertEqual(media_query('heat pipe',explanation_need('How does a heat pipe work?')), 'heat pipe mechanism diagram')
        self.assertTrue(explanation_need('What about that other thing?')['missing_intent'])

    def test_relevant_text_and_image_metadata_are_not_explanatory_pixel_verification(self):
        need=explanation_need('How does heat transfer work?')
        self.assertFalse(presentation_fit({'kind':'evidence'},need)['automatic'])
        self.assertFalse(presentation_fit({'kind':'image','web_source':{'pixels_semantically_verified':False}},need)['automatic'])
        self.assertTrue(presentation_fit({'kind':'evidence'},explanation_need('Show the source please.'))['automatic'])

    def test_annotations_preserve_pixel_provenance_and_distinguish_interpretation(self):
        project,raw=fixture();plan=validate_plan(raw,project);scene=plan['scenes'][0]
        self.assertEqual(scene['asset'],project['sources'][1]['asset'])
        self.assertEqual(scene['coordinate_status'],'requires_presenter_visual_review')
        self.assertEqual(scene['source_refs'][0]['quote'],project['sources'][0]['units'][0]['text'])
        self.assertEqual(plan['concepts'][0]['explanation']['goal'],'mechanism')
        self.assertEqual(focus_target(scene,'Now the pump impeller moves liquid.'),'pump')
        self.assertIsNone(focus_target(scene,'The pump impeller and radiator fins work together.'))
        self.assertIsNone(focus_target(scene,'Ignore the pump impeller for now.'))
        self.assertIsNone(focus_target(scene,'An unrelated subject.'))

    def test_ungrounded_labels_bad_geometry_and_remote_assets_are_rejected(self):
        for key,value in [('x',float('nan')),('y',1.01),('label_x',True),('label_y',-.1),
                          ('quote','An unsupported new physical relationship.'),('cue_phrases',['pump'])]:
            with self.subTest(key=key,value=value):
                project,raw=fixture();raw['concepts'][0]['visuals'][0]['annotations'][0][key]=value
                with self.assertRaises(PlanError):validate_plan(raw,project)
        project,raw=fixture();raw['concepts'][0]['visuals'][0]['asset_id']='https://example.org/image.png'
        with self.assertRaises(PlanError):validate_plan(raw,project)


class AttentionAuthority(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        project,raw=fixture();self.plan=validate_plan(raw,project)
        class Planner:
            def prepare(inner,p):return copy.deepcopy(self.plan)
        self.clock=100
        self.store=Store(self.temp.name);self.studio=Studio(self.store,planner=Planner(),dwell_s=2,clock=lambda:self.clock)
        p=self.store.create(title='Cooling',brief='Explain the mechanism.',audience='Students',sources=project['sources'])
        p=self.studio.prepare(p['id'],background=False);p=self.studio.approve(p['id'],p['revision'],True)
        self.pid=p['id'];self.hash=p['approval']['package_hash'];self.p=self.studio.control(self.pid,'start')

    def speak(self,words,seq):
        return self.studio.transcript(self.pid,words,seq,generation=self.store.read(self.pid)['live']['generation'])

    def test_speech_changes_attention_without_changing_scene_or_approval(self):
        first=self.p['live']['current_scene_id'];p=self.speak('Now the pump impeller moves liquid.',0)
        self.assertEqual(p['live']['decision']['action'],'FOCUS')
        self.assertEqual(p['live']['attention']['annotation_id'],'pump')
        self.assertEqual(p['live']['current_scene_id'],first)
        self.assertEqual(p['approval']['package_hash'],self.hash)
        self.assertEqual(p['live']['history'],[])
        self.clock+=3;p=self.speak('At the radiator fins heat enters air.',1)
        self.assertEqual(p['live']['attention']['annotation_id'],'radiator')
        self.assertEqual(p['live']['current_scene_id'],first)

    def test_hold_dwell_ambiguous_and_stale_input_preserve_attention(self):
        p=self.speak('The pump impeller circulates.',0)
        p=self.speak('Now the radiator fins.',1)
        self.assertEqual(p['live']['attention']['annotation_id'],'pump')
        self.clock+=3;p=self.speak('The pump impeller and radiator fins.',2)
        self.assertEqual(p['live']['attention']['annotation_id'],'pump')
        p=self.studio.control(self.pid,'hold');old=p['live']['generation']
        p=self.speak('The radiator fins.',3)
        self.assertEqual(p['live']['attention']['annotation_id'],'pump')
        p=self.studio.control(self.pid,'focus',annotation_id='radiator')
        self.assertEqual(p['live']['attention']['annotation_id'],'radiator')
        with self.assertRaises(Conflict):self.studio.transcript(self.pid,'The pump impeller.',4,generation=old)
        p=self.studio.control(self.pid,'stop');self.assertIsNone(p['live']['attention'])

    def test_presenter_can_clear_focus_and_placement_edits_break_approval(self):
        self.studio.control(self.pid,'focus',annotation_id='pump')
        p=self.studio.control(self.pid,'focus',annotation_id=None)
        self.assertIsNone(p['live']['attention']['annotation_id'])
        with self.assertRaises(ValueError):self.studio.control(self.pid,'focus',annotation_id='unknown')
        with self.store.change(self.pid) as p:p['approval']['package']['scenes'][0]['annotations'][0]['x']=.9
        with self.assertRaises(Conflict):self.studio.package(self.store.read(self.pid))


if __name__ == '__main__':
    unittest.main()
