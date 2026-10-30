"""Speaker-led style: the screen starts on the speaker and returns to the speaker once speech moves on."""
from pathlib import Path
import tempfile
import unittest

from presenter.attention import past_context
from presenter.engine import STYLES, Store, Studio
from presenter.materials import ingest
from presenter.native_output import VisualOutput
from presenter.planning import source_outline
from presenter.server import EXAMPLE
from system1_v10 import System1Error


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

    def test_presenter_choice_is_not_released_by_speech_and_next_resumes_after_a_clear(self):
        self.start('speaker_led')
        first = self.store.read(self.pid)['approval']['package']['scenes'][0]['concept_id']
        p = self.studio.control(self.pid, 'next')
        shown = p['live']['current_scene_id']
        scenes = {s['id']: s for s in p['approval']['package']['scenes']}
        self.assertEqual(scenes[shown]['concept_id'], first)
        p = self.say('An unrelated aside about the weather.', after_s=60)
        self.assertEqual(p['live']['current_scene_id'], shown)
        self.assertEqual(self.studio.control(self.pid, 'clear')['live']['pinned'], False)
        p = self.studio.control(self.pid, 'next')
        self.assertNotEqual(scenes[p['live']['current_scene_id']]['concept_id'], first)

    def test_style_is_validated_and_survives_stop(self):
        with self.assertRaises(ValueError):
            self.studio.control(self.pid, 'style', style='cinematic')
        self.start('speaker_led')
        self.studio.control(self.pid, 'stop')
        p = self.studio.control(self.pid, 'start')
        self.assertEqual(p['live']['style'], 'speaker_led')
        self.assertIsNone(p['live']['current_scene_id'])


class LookSignalTests(PresentationStyleTests):
    """Jev's look/listen signal gates visuals that exist; it never invents one."""
    def setUp(self):
        super().setUp()
        self.look = 0.9
        self.earlier = []
        def assessor(words, earlier):
            self.earlier.append(list(earlier))
            if isinstance(self.look, Exception):
                raise self.look
            return {'look': self.look}
        self.studio.moment_assessor = assessor

    def show_visual(self):
        self.look = .9
        self.start('speaker_led')
        return self.say(self.concepts[1]['title'])['live']['current_scene_id']

    # Topic-only behavior inherited from the base class is covered there, not with a signal.
    test_visual_returns_to_the_speaker_after_speech_moves_on = None
    test_continued_support_keeps_the_visual = None
    test_hold_prevents_automatic_release_and_clear_is_a_manual_control = None
    test_speaker_led_starts_on_the_speaker_and_shows_when_speech_needs_a_visual = None

    def test_listen_keeps_a_matching_visual_backstage(self):
        self.look = .1
        self.start('speaker_led')
        p = self.say(self.concepts[1]['title'])
        self.assertIsNone(p['live']['current_scene_id'])
        self.assertEqual(p['live']['decision']['action'], 'WARM')
        self.assertIn('moment for the speaker', p['live']['decision']['reason'])

    def test_look_without_a_prepared_visual_shows_nothing(self):
        self.start('speaker_led')
        p = self.say('Look at this strange unrelated purple giraffe.')
        self.assertIsNone(p['live']['current_scene_id'])

    def test_listen_releases_even_while_the_topic_still_matches(self):
        release = STYLES['speaker_led']['look_release_s']
        shown = self.show_visual()
        self.look = .1
        p = self.say(self.concepts[1]['title'], after_s=release / 2)
        self.assertEqual(p['live']['current_scene_id'], shown)
        p = self.say(self.concepts[1]['title'], after_s=release / 2)
        self.assertIsNone(p['live']['current_scene_id'])
        self.assertEqual(p['live']['decision']['action'], 'CLEAR')

    def test_look_renews_a_visual_on_an_unrelated_topic(self):
        release = STYLES['speaker_led']['look_release_s']
        shown = self.show_visual()
        self.look = STYLES['speaker_led']['look_keep']
        for _ in range(4):
            p = self.say('And look at this part here on the left.', after_s=release * .75)
        self.assertEqual(p['live']['current_scene_id'], shown)

    def test_failed_signal_falls_back_to_topics_in_both_directions(self):
        self.look = System1Error('down')
        self.start('speaker_led')
        p = self.say(self.concepts[1]['title'])
        self.assertIsNotNone(p['live']['current_scene_id'])
        self.assertIn('error', p['live']['recommendation']['moment'])
        p = self.say('Let me tell you a story about my grandmother.', after_s=STYLES['speaker_led']['release_after_s'])
        self.assertIsNone(p['live']['current_scene_id'])

    def test_malformed_signal_counts_as_no_signal(self):
        self.look = float('nan')
        self.start('speaker_led')
        p = self.say(self.concepts[1]['title'])
        self.assertIn('error', p['live']['recommendation']['moment'])

    def test_hold_beats_the_signal(self):
        shown = self.show_visual()
        self.studio.control(self.pid, 'hold')
        self.look = .1
        p = self.say('A story.', after_s=30)
        self.assertEqual(p['live']['current_scene_id'], shown)

    def test_persist_style_never_calls_jev_for_timing(self):
        self.look = .1
        self.start('persist')
        p = self.say(self.concepts[1]['title'])
        self.assertEqual(self.earlier, [])
        self.assertNotIn('moment', p['live']['recommendation'])

    def test_a_pause_returns_to_the_speaker_without_new_words(self):
        shown = self.show_visual()
        generation = self.store.read(self.pid)['live']['generation']
        self.clock.now += 1
        self.studio.idle(self.pid, generation)
        self.assertEqual(self.store.read(self.pid)['live']['current_scene_id'], shown)
        self.clock.now += STYLES['speaker_led']['look_release_s']
        self.studio.idle(self.pid, generation)
        self.assertIsNone(self.store.read(self.pid)['live']['current_scene_id'])
        self.studio.idle(self.pid, 'an older rehearsal')

    def test_context_skips_overlapping_recognition_windows(self):
        rows = [{'text': f'w{i}', 'at': 1000.0 + i} for i in range(12)]
        self.assertEqual(past_context(rows, 1012.0), ['w4', 'w8'])
        self.assertEqual(past_context(rows[:1], 1001.0), [])


if __name__ == '__main__':
    unittest.main()
