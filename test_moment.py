"""Offline checks for caption parsing, the look/listen screen policy and interval scoring."""
import unittest

from presenter.edit_benchmark import compare_intervals
from presenter.moment import cue_questions, parse_vtt, screen_intervals

VTT = """WEBVTT

00:00:00.000 --> 00:00:00.001


00:00:00.300 --> 00:00:02.341
I was only four years old

00:00:02.365 --> 00:00:05.276
when I saw my mother
load a washing machine

00:00:05.276 --> 00:00:06.000
when I saw my mother
load a washing machine

01:00:07.943 --> 01:00:09.919
<c>That was a great day.</c>
"""


def look(p):
    return {'look': p, 'listen': 1 - p, 'transition': 0.0}


class MomentTests(unittest.TestCase):
    def test_vtt_skips_empty_and_repeated_cues_and_reads_hours(self):
        cues = parse_vtt(VTT)
        self.assertEqual([c[2] for c in cues], ['I was only four years old',
                                               'when I saw my mother load a washing machine', 'That was a great day.'])
        self.assertAlmostEqual(cues[2][0], 3607.943)

    def test_rolling_automatic_captions_keep_only_new_words(self):
        auto = ('WEBVTT\n\n00:00:00.960 --> 00:00:05.829 align:start position:0%\n \n'
                'So<00:00:01.280><c> good</c>\n\n'
                '00:00:05.829 --> 00:00:05.839 align:start position:0%\nSo good\n \n\n'
                '00:00:05.839 --> 00:00:07.670 align:start position:0%\nSo good\nI<00:00:06.160><c> got it.</c>\n')
        self.assertEqual([c[2] for c in parse_vtt(auto)], ['So good', 'I got it.'])

    def test_questions_carry_only_past_context(self):
        cues = [(0, 1, 'one'), (1, 2, 'two'), (2, 3, 'three'), (3, 4, 'four')]
        text = cue_questions(cues, [2])['c2']['instructions']
        self.assertIn('"one two"', text)
        self.assertIn('"three"', text)
        self.assertNotIn('four', text)

    def test_policy_shows_on_look_renews_and_releases_after_silence_of_support(self):
        cues = [(i * 2.0, i * 2.0 + 2, f'cue {i}') for i in range(10)]
        probabilities = [look(p) for p in [.1, .9, .5, .1, .1, .1, .1, .9, .1, .1]]
        spans = screen_intervals(cues, probabilities, on=.6, keep=.4, release_s=4.0, min_dwell_s=3.0, delay_s=.5)
        # Shown at the end of cue 1 (4.5), renewed by cue 2 (6.5), released 4 s later (10.5 → first check at 10.5).
        self.assertEqual(spans[0], (4.5, 10.5))
        self.assertEqual(spans[1][0], 16.5)
        self.assertEqual(len(spans), 2)

    def test_policy_never_releases_before_minimum_dwell(self):
        cues = [(0, 1, 'a'), (1, 2, 'b'), (2, 3, 'c')]
        spans = screen_intervals(cues, [look(.9), look(0), look(0)], on=.6, keep=.4, release_s=.5, min_dwell_s=5.0,
                                 delay_s=0)
        self.assertEqual(spans, [(1, 3)])  # still on at the end; closed at the last cue

    def test_interval_scoring_matches_edit_seconds(self):
        analysis = {'profile': {'duration_s': 10.0},
                    'timeline': [{'start': 0, 'end': 5, 'label': 'speaker'},
                                 {'start': 5, 'end': 10, 'label': 'fullscreen_visual'}]}
        perfect = compare_intervals(analysis, [(5, 10)])
        self.assertEqual((perfect['agreement'], perfect['kappa']), (1.0, 1.0))
        always = compare_intervals(analysis, [(0, 10)])
        self.assertEqual((always['agreement'], always['kappa'], always['speaker_time_left_clear']), (.5, 0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
