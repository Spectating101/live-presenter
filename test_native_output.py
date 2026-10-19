"""Visual-only output and backend authority; optional real Qt rendering checks."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from presenter.native_output import VisualOutput, demo_engine, axis_label
from presenter.explanation import focus_target, chart_comparison


class NativeOutput(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,self.studio,self.pid=demo_engine(Path(self.temp.name))
        self.output=VisualOutput()

    def speak(self, text, seq):
        p=self.store.read(self.pid)
        return self.studio.transcript(self.pid,text,seq,generation=p['live']['generation'])

    def test_chart_focus_and_next_quantity_use_the_existing_engine(self):
        p=self.store.read(self.pid);self.assertTrue(self.output.accept(p))
        first=self.output.scene['id']
        p=self.speak('At the high setting.',0);self.output.accept(p)
        self.assertEqual(self.output.scene['id'],first)
        self.assertEqual(self.output.attention['annotation_id'],'datum_2')
        self.assertEqual([r['value'] for r in self.output.scene['data']],[12,18,24])
        p=self.speak('Now electrical power consumption.',1);self.output.accept(p)
        self.assertNotEqual(self.output.scene['id'],first)
        self.assertIsNone(self.output.attention)
        self.assertEqual([r['value'] for r in self.output.scene['data']],[90,145,230])
        self.assertEqual(axis_label(self.output.scene['y']),'Electrical power (W)')

    def test_prose_does_not_replace_a_chart_and_stop_does_clear_it(self):
        self.output.accept(self.store.read(self.pid));first=self.output.scene['id']
        source=self.store.read(self.pid)['approval']['package']['scenes'][1]['id']
        p=self.studio.control(self.pid,'show',source);self.output.accept(p)
        self.assertEqual(self.output.scene['id'],first)
        self.assertIn('retaining',self.output.reason)
        p=self.studio.control(self.pid,'stop');self.output.accept(p)
        self.assertIsNone(self.output.scene)

    def test_revoked_or_tampered_approval_clears_output(self):
        p=self.store.read(self.pid);self.output.accept(p)
        p['approval']['package']['scenes'][0]['data'][0]['value']=999
        self.output.accept(p);self.assertIsNone(self.output.scene)
        p=self.store.read(self.pid);self.output.accept(p)
        p['approval']=None
        self.output.accept(p);self.assertIsNone(self.output.scene)

    def test_chart_focus_is_specific_and_ambiguous_mentions_hold(self):
        scene=self.store.read(self.pid)['approval']['package']['scenes'][0]
        self.assertIsNone(focus_target(scene,'A high level explanation.'))
        self.assertEqual(focus_target(scene,'At the high setting.'),'datum_2')
        self.assertIsNone(focus_target(scene,'Compare the high setting and low setting.'))
        self.assertIsNone(focus_target(scene,'Ignore the high setting.'))

    def test_explicit_comparison_derives_the_answer_instead_of_copying_spoken_numbers(self):
        scene=self.store.read(self.pid)['approval']['package']['scenes'][0]
        comparison=chart_comparison(scene,'Compare low and high. The difference is 999!')
        self.assertEqual(comparison['delta'],12)
        self.assertEqual(comparison['ratio'],2)
        self.assertIsNone(chart_comparison(scene,'Compare low, medium and high.'))
        self.assertIsNone(chart_comparison(scene,'Do not compare low and high.'))
        scene['data'][0]['value']=0
        self.assertIsNone(chart_comparison(scene,'Compare low and high.')['ratio'])
        scene['data'][0]['value']=1e-308;scene['data'][2]['value']=1e308
        self.assertIsNone(chart_comparison(scene,'Compare low and high.')['ratio'])
        scene['data'][0]['value']=-1e308
        self.assertIsNone(chart_comparison(scene,'Compare low and high.'))

    def test_comparison_preserves_the_chart_and_obeys_hold(self):
        p=self.store.read(self.pid);digest=p['approval']['package_hash']
        self.output.accept(p);first=self.output.scene['id']
        p=self.speak('Compare low and high.',0);self.output.accept(p)
        self.assertEqual(p['live']['decision']['action'],'COMPARE')
        self.assertEqual(self.output.scene['id'],first)
        self.assertEqual(self.output.attention['comparison']['delta'],12)
        self.assertEqual(p['approval']['package_hash'],digest)
        p=self.studio.control(self.pid,'hold')
        p=self.speak('At the medium setting.',1);self.output.accept(p)
        self.assertEqual(self.output.attention['comparison']['delta'],12)


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'Optional native environment not installed in this interpreter.')
class QtVisualOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM']='offscreen'
        from presenter.native import qt_types
        App,cls.Surface,_=qt_types()
        cls.app=App.instance() or App([])

    def test_native_window_contains_no_widgets_and_paints_real_measurements(self):
        from PySide6.QtWidgets import QWidget
        with tempfile.TemporaryDirectory() as folder:
            store,studio,pid=demo_engine(Path(folder));state=VisualOutput();state.accept(store.read(pid))
            surface=self.Surface();self.addCleanup(surface.close)
            surface.present(state);surface.show();self.app.processEvents()
            image=surface.grab().toImage()
            self.assertEqual(surface.findChildren(QWidget),[])
            self.assertFalse(image.isNull())
            self.assertGreater(len(surface.samples),0)
            self.assertEqual(surface.scene['data'][2]['value'],24)
            # Focus is an update within the same native surface and chart.
            original=surface
            p=store.read(pid);p=studio.transcript(pid,'At the high setting.',0,generation=p['live']['generation'])
            state.accept(p);surface.present(state);self.app.processEvents()
            self.assertIs(surface,original)
            self.assertEqual(surface.samples[-1]['target_id'],'datum_2')

    def test_image_focus_reuses_decoded_pixels(self):
        from test_explanation import fixture
        from presenter.planning import validate_plan
        project,raw=fixture();scene=validate_plan(raw,project)['scenes'][0]
        state=VisualOutput();state.scene=scene
        surface=self.Surface();self.addCleanup(surface.close)
        surface.present(state);image=surface.images[scene['asset']['sha256']]
        state.attention={'scene_id':scene['id'],'annotation_id':'pump'}
        surface.present(state);surface.show();self.app.processEvents()
        self.assertIs(surface.images[scene['asset']['sha256']],image)
        self.assertEqual(surface.samples[-1]['target_id'],'pump')

    def test_explanatory_motion_changes_pixels_without_changing_source_values(self):
        with tempfile.TemporaryDirectory() as folder:
            store,studio,pid=demo_engine(Path(folder));state=VisualOutput();state.accept(store.read(pid))
            clock=[0.]
            surface=self.Surface(animate=True,clock=lambda:clock[0]);self.addCleanup(surface.close)
            surface.present(state);surface.show();self.app.processEvents()
            initial=surface.grab().toImage()
            clock[0]=1.;surface.update();self.app.processEvents()
            settled=surface.grab().toImage()
            self.assertEqual(initial,settled)
            p=store.read(pid);p=studio.transcript(pid,'At the high setting.',0,generation=p['live']['generation'])
            state.accept(p);surface.present(state);self.app.processEvents()
            before_emphasis=surface.grab().toImage()
            clock[0]=2.;surface.update();self.app.processEvents()
            self.assertNotEqual(before_emphasis,surface.grab().toImage())
            self.assertEqual([r['value'] for r in surface.scene['data']],[12,18,24])
            surface.animate=False
            p=store.read(pid);p=studio.transcript(pid,'Compare low and high.',1,generation=p['live']['generation'])
            state.accept(p);surface.present(state);self.app.processEvents()
            self.assertEqual(surface.motion_progress(),1)
            self.assertEqual(surface.attention['comparison']['ratio'],2)


if __name__=='__main__':
    unittest.main()
