"""Prepared cue reactions retain authority and avoid cloud calls on clear cues."""
import copy
from pathlib import Path
import tempfile
import threading
import unittest

from presenter.engine import Store, Studio
from presenter.materials import ingest, normalized
from presenter.planning import validate_plan
from presenter.reflex import CueIndex


def example():
    material=ingest('Launch notes.md',b'# Departure\n\nThe rocket leaves the launch pad. Its ascent follows a gravity turn toward orbit.\n\n# Storage\n\nA rechargeable battery stores electrical energy. Thermal management keeps the cells within their operating limits.\n\n# Ocean\n\nOcean currents transport heat. Salinity and temperature affect water density.')
    refs=material['units']
    raw={'concepts':[
        {'title':'Rocket ascent','summary':'The rocket reaches orbit.','aliases':['leaving the pad'],
         'source_refs':[{'unit_id':refs[0]['id'],'quote':'The rocket leaves the launch pad.'}],
         'visuals':[{'kind':'definition','body':['The rocket leaves the pad.']}]},
        {'title':'Battery storage','summary':'Store electrical energy.','aliases':['rechargeable battery'],
         'source_refs':[{'unit_id':refs[1]['id'],'quote':'A rechargeable battery stores electrical energy.'}],
         'visuals':[{'kind':'definition','body':['Stored electrical energy.']}]},
        {'title':'Ocean transport','summary':'Water moves heat.','aliases':['ocean currents'],
         'source_refs':[{'unit_id':refs[2]['id'],'quote':'Ocean currents transport heat.'}],
         'visuals':[{'kind':'definition','body':['Currents move heat.']}]}]}
    project={'title':'Mechanisms','sources':[material],'audience':'Students'}
    return project,validate_plan(raw,project)


class PreparedReflex(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        p,plan=example()
        self.source=p;self.plan=plan
        class Planner:
            def prepare(self,p):return copy.deepcopy(plan)
        self.studio=Studio(self.store,planner=Planner(),dwell_s=0)
        p=self.store.create(title=p['title'],brief='Explain mechanisms',audience=p['audience'],sources=p['sources'])
        p=self.studio.prepare(p['id'],background=False)
        self.p=self.studio.approve(p['id'],p['revision'],True);self.pid=p['id']
    def tearDown(self):self.temp.cleanup()

    def test_compile_recognizes_linked_passage_language_outside_selected_quote(self):
        index=CueIndex(self.plan,self.source['sources'])
        choice=index.match('Follow the gravity turn toward orbit.')
        self.assertTrue(choice['reflex_ready'])
        target=next(s for s in self.plan['scenes'] if s['id']==choice['scene_id'])
        self.assertEqual(target['concept_id'],self.plan['concepts'][0]['id'])

    def test_off_topic_generic_and_single_word_fragments_do_not_trigger_reflex(self):
        index=CueIndex(self.plan,self.source['sources'])
        for text in ('Quantum entanglement between qubits','Look here, you know, this thing','battery'):
            self.assertIsNone(index.match(text)['scene_id'])
        mixed=index.match('quantum entanglement superconducting qubits interference wavefunction spin measurement gravity turn')
        self.assertFalse(mixed['reflex_ready'])

    def test_phrase_repeated_elsewhere_in_material_is_not_a_unique_source_cue(self):
        sources=copy.deepcopy(self.source['sources'])
        sources[0]['units'].append({'id':'unassigned','text':'In a different demonstration the gravity turn toward orbit was mentioned.'})
        index=CueIndex(self.plan,sources)
        choice=index.match('gravity turn toward orbit')
        self.assertFalse(choice['reflex_ready'])

    def test_repeating_ambiguous_fragment_does_not_turn_it_into_a_reflex(self):
        p=self.studio.control(self.pid,'start');p=self.studio.control(self.pid,'reflex',enabled=True)
        opening=p['live']['current_scene_id']
        from unittest.mock import patch
        suggestion={'scene_id':p['plan']['scenes'][-1]['id'],'score':.95,'confirmed':False,'supported_concepts':[], 'reflex_ready':False}
        with patch.object(self.studio.cue_index(p),'match',return_value=suggestion):
            for seq in range(3):
                p=self.studio.transcript(self.pid,'A repeated fragment',seq,generation=p['live']['generation'])
                self.assertEqual(p['live']['current_scene_id'],opening)

    def test_clear_prepared_cue_bypasses_adviser_and_reuses_compiled_index(self):
        p=self.studio.control(self.pid,'start')
        p=self.studio.control(self.pid,'reflex',enabled=True)
        p=self.studio.control(self.pid,'adviser',enabled=True)
        def forbidden(*args):self.fail('Clear prepared cue called the cloud adviser')
        self.studio.live_assessor=forbidden
        index=self.studio.cue_index(p)
        p=self.studio.transcript(self.pid,'Rechargeable battery stores electrical energy.',0,generation=p['live']['generation'])
        self.assertEqual(p['live']['decision']['action'],'SHOW')
        self.assertEqual(p['live']['recommendation']['method'],'compiled_source_cues')
        self.assertIs(index,self.studio.cue_index(p))
        self.assertNotIn('advice',p['live']['recommendation'])

    def test_fast_cue_still_respects_hold_and_dwell(self):
        p=self.studio.control(self.pid,'start');p=self.studio.control(self.pid,'reflex',enabled=True)
        opening=p['live']['current_scene_id'];p=self.studio.control(self.pid,'hold')
        p=self.studio.transcript(self.pid,'Rechargeable battery stores electrical energy.',0,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],opening)
        p=self.studio.control(self.pid,'resume');self.studio.dwell_s=100
        p=self.studio.transcript(self.pid,'Rechargeable battery stores electrical energy.',1,generation=p['live']['generation'])
        self.assertEqual(p['live']['current_scene_id'],opening)

    def test_toggling_mode_invalidates_older_in_flight_recommendation(self):
        p=self.studio.control(self.pid,'start');p=self.studio.control(self.pid,'adviser',enabled=True)
        entered,release=threading.Event(),threading.Event()
        target=p['plan']['scenes'][-1]['id']
        def slow(*args):entered.set();release.wait(3);return {'scene_id':target,'confidence':1}
        self.studio.live_assessor=slow
        worker=threading.Thread(target=lambda:self.studio.transcript(self.pid,'Ocean currents',0,generation=p['live']['generation']))
        worker.start();self.assertTrue(entered.wait(2))
        self.studio.control(self.pid,'reflex',enabled=True)
        release.set();worker.join(3)
        self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'],p['live']['current_scene_id'])


if __name__=='__main__':unittest.main()
