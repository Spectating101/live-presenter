"""Offline checks for edit-timeline extraction: cuts, sampling, timelines, profiles and labelling."""
import asyncio
from pathlib import Path
import tempfile
import unittest

from presenter.edit_benchmark import (LABEL_KEY, LABELS, build_timeline, classify_frames, episodes, load_catalog,
                                      parse_cuts, profile, sample_times)
from system1_v10 import System1Error, System1Response, parse_answers


class FakeBackend:
    def __init__(self, labels, fail_first=0):
        self.labels, self.fail_first, self.calls = labels, fail_first, []

    async def ask(self, state, questions, assets=None):
        self.calls.append((questions, assets))
        if self.fail_first:
            self.fail_first -= 1
            raise System1Error('busy')
        raw = {}
        for name, question in questions.items():
            ref = question['instructions'].rsplit(' ', 1)[-1]
            label = self.labels[ref]
            raw[name] = {'type': 'choice', 'choice': label, 'confidence': .9,
                         'probabilities': {k: (.9 if k == label else .025) for k in LABELS}}
        return System1Response('fake', 'jev-test', parse_answers(raw), 1.0, input_tokens=10)


class EditBenchmarkTests(unittest.TestCase):
    def test_catalog_is_valid_and_ids_are_unique(self):
        records = load_catalog()['records']
        self.assertEqual(len({r['id'] for r in records}), len(records))
        self.assertIn('no_slides_control', {r['genre'] for r in records})

    def test_parse_cuts_reads_showinfo_times(self):
        text = '[Parsed_showinfo_1] n:0 pts:1 pts_time:36.820133 pos:1\n[Parsed_showinfo_1] n:1 pts_time:45.7 x'
        self.assertEqual(parse_cuts(text), [36.82, 45.7])

    def test_long_shots_get_several_samples(self):
        self.assertEqual(sample_times([2.0], 14.0, max_gap=5.0), [1.0, 4.0, 8.0, 12.0])

    def test_timeline_splits_between_differing_samples_and_merges_equal_ones(self):
        # Shots: [0,10) speaker, [10,20) a slide that changes at 15, [20,30) zoom from screen back to speaker.
        cuts = [10.0, 15.0, 20.0]
        labelled = [(5, 'speaker', .9), (12.5, 'fullscreen_visual', .9), (17.5, 'fullscreen_visual', .9), (22, 'fullscreen_visual', .9),
                    (28, 'speaker', .5)]
        timeline = build_timeline(cuts, 30.0, labelled)
        self.assertEqual([(t['start'], t['end'], t['label']) for t in timeline],
                         [(0.0, 10.0, 'speaker'), (10.0, 25.0, 'fullscreen_visual'), (25.0, 30.0, 'speaker')])
        self.assertEqual(timeline[1]['content_changes'], 2)  # slide change at 15 and the cut at 20
        self.assertEqual(timeline[2]['low_confidence_s'], 5.0)

    def test_profile_measures_returns_to_the_speaker(self):
        timeline = [{'start': 0, 'end': 20, 'label': 'speaker', 'content_changes': 0, 'low_confidence_s': 0},
                    {'start': 20, 'end': 26, 'label': 'fullscreen_visual', 'content_changes': 1, 'low_confidence_s': 0},
                    {'start': 26, 'end': 50, 'label': 'speaker', 'content_changes': 0, 'low_confidence_s': 0},
                    {'start': 50, 'end': 54, 'label': 'stage_with_screen', 'content_changes': 0, 'low_confidence_s': 0},
                    {'start': 54, 'end': 60, 'label': 'fullscreen_visual', 'content_changes': 0, 'low_confidence_s': 0}]
        result = profile(timeline, 60.0)
        self.assertEqual(result['share']['speaker'], round(44 / 60, 4))
        self.assertEqual(result['content_share'], round(16 / 60, 4))
        self.assertEqual(result['full_visual_episodes']['n'], 2)
        self.assertEqual(result['content_episodes']['n'], 2)  # 50-54 and 54-60 form one content episode
        self.assertEqual(result['returns_between_content']['median'], 24)
        self.assertEqual(episodes(timeline, {'fullscreen_visual', 'stage_with_screen'})[1]['content_changes'], 1)

    def test_classification_sends_one_image_per_question_retries_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for i in range(3):
                path = Path(temp) / f'frame_{i:09d}.jpg'
                path.write_bytes(bytes([i]) * 8)
                paths.append(path)
            backend = FakeBackend({}, fail_first=1)

            async def run(cache):
                return await classify_frames(paths, backend, cache=cache, batch=2, workers=1, retries=2)

            # Map each image reference to a label after building the questions once.
            from presenter.edit_benchmark import frame_questions
            questions, assets = frame_questions(paths)
            refs = [q['instructions'].rsplit(' ', 1)[-1] for q in questions.values()]
            backend.labels = dict(zip(refs, ['speaker', 'fullscreen_visual', 'audience']))
            cache = {}
            labels, usage = asyncio.run(run(cache))
            self.assertEqual([labels[p.name]['label'] for p in paths], ['speaker', 'fullscreen_visual', 'audience'])
            self.assertEqual((usage['calls'], usage['failures']), (2, 1))
            sent_questions, sent_assets = backend.calls[-1]
            self.assertEqual(len(sent_questions), len(sent_assets))
            self.assertTrue(all(k.startswith(f'{LABEL_KEY}:') for k in cache))
            calls = len(backend.calls)
            asyncio.run(run(cache))
            self.assertEqual(len(backend.calls), calls)  # fully cached: no new requests


if __name__ == '__main__':
    unittest.main()
