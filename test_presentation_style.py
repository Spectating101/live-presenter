"""Speaker-led style: the screen starts on the speaker and returns to the speaker once speech moves on."""
from pathlib import Path
import tempfile
import unittest

from presenter.engine import STYLES, Store, Studio
from presenter.materials import ingest
from presenter.native_output import VisualOutput
from presenter.planning import source_outline
from presenter.server import EXAMPLE


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Outline:
    def prepare(self, project):
        return source_outline(project)


class PresentationStyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.store = Store(Path(self.temp.name))
        self.studio = Studio(self.store, planner=Outline(), dwell_s=0, clock=self.clock)
        sources = [ingest(s['name'], s['text'].encode()) for s in EXAMPLE['sources']]
        p = self.store.create(title=EXAMPLE['title'], brief=EXAMPLE['brief'], audience=EXAMPLE['audience'],
                              sources=sources, provider='outline')
        p = self.studio.prepare(p['id'], background=False)
        self.pid = self.studio.approve(p['id'], p['revision'], True)['id']
        self.concepts = self.store.read(self.pid)['approval']['package']['concepts']
        self.seq = 0

    def tearDown(self):
        self.temp.cleanup()

    def say(self, text, after_s=1.0):
        self.clock.now += after_s
        p = self.store.read(self.pid)
        p = self.studio.transcript(self.pid, text, self.seq, generation=p['live']['generation'])
        self.seq += 1
        return p

    def start(self, style):
        self.studio.control(self.pid, 'style', style=style)
        return self.studio.control(self.pid, 'start')

    def test_persist_style_keeps_the_existing_opening_visual(self):
        p = self.start('persist')
        self.assertIsNotNone(p['live']['current_scene_id'])

    def test_speaker_led_starts_on_the_speaker_and_shows_when_speech_needs_a_visual(self):
        p = self.start('speaker_led')
        self.assertIsNone(p['live']['current_scene_id'])
        self.assertEqual(p['live']['decision']['action'], 'HOLD')
        p = self.say(self.concepts[1]['title'])
        self.assertEqual(p['live']['decision']['action'], 'SHOW')
        self.assertEqual(p['live']['style'], 'speaker_led')

    def test_visual_returns_to_the_speaker_after_speech_moves_on(self):
        release = STYLES['speaker_led']['release_after_s']
        self.start('speaker_led')
        shown = self.say(self.concepts[1]['title'])['live']['current_scene_id']
        p = self.say('Let me tell you a story about my grandmother.', after_s=release / 2)
        self.assertEqual(p['live']['current_scene_id'], shown)
        p = self.say('She had never travelled outside her village.', after_s=release / 2)
        self.assertIsNone(p['live']['current_scene_id'])
        self.assertEqual(p['live']['decision']['action'], 'CLEAR')
        self.assertEqual(p['live']['history'][-1], shown)
        output = VisualOutput()
        output.accept(p)
        self.assertIsNone(output.scene)
        self.assertIn('speaker', output.reason)

    def test_continued_support_keeps_the_visual(self):
        release = STYLES['speaker_led']['release_after_s']
        self.start('speaker_led')
        shown = self.say(self.concepts[1]['title'])['live']['current_scene_id']
        for _ in range(4):
            p = self.say(self.concepts[1]['title'], after_s=release * .75)
        self.assertEqual(p['live']['current_scene_id'], shown)

    def test_hold_prevents_automatic_release_and_clear_is_a_manual_control(self):
        release = STYLES['speaker_led']['release_after_s']
        self.start('speaker_led')
        shown = self.say(self.concepts[1]['title'])['live']['current_scene_id']
        self.studio.control(self.pid, 'hold')
        p = self.say('An unrelated aside about the weather.', after_s=release * 2)
        self.assertEqual(p['live']['current_scene_id'], shown)
        p = self.studio.control(self.pid, 'clear')
        self.assertIsNone(p['live']['current_scene_id'])
        self.assertEqual(p['live']['decision']['action'], 'CLEAR')

    def test_style_is_validated_and_survives_stop(self):
        with self.assertRaises(ValueError):
            self.studio.control(self.pid, 'style', style='cinematic')
        self.start('speaker_led')
        self.studio.control(self.pid, 'stop')
        p = self.studio.control(self.pid, 'start')
        self.assertEqual(p['live']['style'], 'speaker_led')
        self.assertIsNone(p['live']['current_scene_id'])


if __name__ == '__main__':
    unittest.main()
