"""Decide from the speaker's words when the audience should look at the screen.

A speaker-led talk keeps attention on the person and brings in a visual only
for moments that need one. Jev labels each caption cue as a moment to look, to
listen or a transition, using only that cue and the cues before it. A simple
hysteresis policy turns those labels into screen-on intervals, which are scored
against an edited recording's cuts to presented content.

Captions are an upper-bound text stream (exact words, no recognition errors);
live use must repeat this on past-only speech recognition windows.
"""
import argparse
import asyncio
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

from jev_credentials_v10 import load_jev_env
from system1_v10 import JevBackend, System1Error
from .edit_benchmark import CATALOG, ROOT, compare_intervals, load_catalog
from .recording import save

MOMENTS = {
    'look': 'The words point the audience at something to see right now: a number, chart, comparison, map, '
            'picture, place, person or object that the speaker is showing or describing concretely.',
    'listen': 'The speaker is telling a story, giving an opinion, joking, addressing the audience or making a '
              'general point. Watching the speaker is enough.',
    'transition': 'A greeting, thanks, filler or a move between topics.',
}
MOMENT_KEY = hashlib.sha256(json.dumps(MOMENTS, sort_keys=True).encode()).hexdigest()[:16]
STATE = 'Captions from a live presentation, heard in order. Only the words so far are known.'


def parse_vtt(text):
    """Caption cues as (start_s, end_s, text), skipping empty cues and repeated rolling lines."""
    cues, blocks = [], []
    # A cue runs from its timing line to the next; YouTube puts whitespace-only lines inside cues.
    for line in text.replace('\r', '').split('\n'):
        if '-->' in line:
            blocks.append([line])
        elif blocks and line.strip():
            blocks[-1].append(line)
    for timing_line, *text in blocks:
        start, end = (stamp(part.strip().split(' ')[0]) for part in timing_line.split('-->'))
        # Rolling automatic captions repeat the previous line; word-timed (<c>) lines are the new speech.
        if any('<c>' in line for line in text):
            text = [line for line in text if '<c>' in line]
        words = ' '.join(re.sub(r'<[^>]+>', '', line).strip() for line in text).strip()
        if words and end - start >= .05 and not (cues and cues[-1][2] == words):
            cues.append((start, end, words))
    return cues


def stamp(value):
    parts = [float(p) for p in value.replace(',', '.').split(':')]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def cue_questions(cues, indices, context=2):
    questions = {}
    for i in indices:
        before = ' '.join(c[2] for c in cues[max(0, i - context):i])
        questions[f'c{i}'] = {'type': 'choice', 'criteria': MOMENTS,
                              'instructions': (f'Earlier: "{before}" ' if before else '')
                              + f'Now the speaker says: "{cues[i][2]}". What does this latest part call for?'}
    return questions


async def classify_cues(cues, backend, *, cache=None, batch=20, workers=3, retries=3):
    cache = cache if cache is not None else {}
    key = lambda i: f'{MOMENT_KEY}:{cues[i][0]:.3f}:{hashlib.sha256(cues[i][2].encode()).hexdigest()[:12]}'
    todo = [i for i in range(len(cues)) if key(i) not in cache]
    gate = asyncio.Semaphore(workers)

    async def run(group):
        async with gate:
            for attempt in range(retries):
                try:
                    response = await backend.ask(STATE, cue_questions(cues, group))
                    break
                except System1Error:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
        for i in group:
            answer = response.answers[f'c{i}']
            cache[key(i)] = {k: round(v, 4) for k, v in answer.probabilities.items()}

    await asyncio.gather(*(run(todo[i:i + batch]) for i in range(0, len(todo), batch)))
    return [cache[key(i)] for i in range(len(cues))]


def screen_intervals(cues, probabilities, *, on=.6, keep=.4, release_s=4.0, min_dwell_s=3.0, delay_s=.5):
    """Causal hysteresis: decide at each cue's end (plus decision delay).

    Show when P(look) >= on. While shown, a cue with P(look) >= keep renews the
    visual; release after release_s without renewal, never before min_dwell_s."""
    spans, since, last = [], None, None
    for (start, end, _), p in zip(cues, probabilities):
        t, look = end + delay_s, p.get('look', 0)
        if since is not None and t - last >= release_s and t - since >= min_dwell_s and look < keep:
            spans.append((since, t))
            since = None
        if since is None and look >= on:
            since = last = t
        elif since is not None and look >= keep:
            last = t
    if since is not None:
        spans.append((since, cues[-1][1] + delay_s))
    return spans


GRID = {'on': [.5, .6, .7, .8], 'keep': [.3, .4, .5], 'release_s': [2.0, 4.0, 6.0, 8.0], 'min_dwell_s': [3.0]}


def calibrate(talks, grid=GRID):
    """Choose the policy with the best mean kappa over the calibration talks."""
    best = None
    for values in itertools.product(*grid.values()):
        params = dict(zip(grid, values))
        if params['keep'] > params['on']:
            continue
        scores = [compare_intervals(a, screen_intervals(c, p, **params))['kappa'] or 0 for a, c, p in talks]
        mean = sum(scores) / len(scores)
        if best is None or mean > best[0]:
            best = (round(mean, 4), params)
    return best


def load_talk(folder, backend):
    folder = Path(folder)
    vtt = folder / 'video.en.vtt'
    cues = parse_vtt(vtt.read_text())
    cache_path = folder / 'moments.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    try:
        probabilities = asyncio.run(classify_cues(cues, backend, cache=cache))
    finally:
        save(cache_path, cache)
    return json.loads((folder / 'analysis.json').read_text()), cues, probabilities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--calibrate', nargs='+', required=True, help='Catalog ids used to choose the policy.')
    parser.add_argument('--evaluate', nargs='*', default=[], help='Held-out catalog ids scored with that policy.')
    parser.add_argument('--model', default='jev-preview')
    parser.add_argument('--env-file')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    known = {r['id'] for r in load_catalog(args.catalog)['records']}
    if not set(args.calibrate + args.evaluate) <= known or set(args.calibrate) & set(args.evaluate):
        parser.error('Use known, disjoint catalog ids for calibration and evaluation.')
    if not load_jev_env(args.env_file):
        parser.error('No Jev credential: set JEV_API_KEY or pass --env-file.')
    backend = JevBackend(model=args.model, timeout_s=60)
    talks = {i: load_talk(args.root / i, backend) for i in args.calibrate + args.evaluate}
    score, params = calibrate([talks[i] for i in args.calibrate])
    result = {'moment_key': MOMENT_KEY, 'moments': MOMENTS, 'text_stream': 'official captions (upper bound)',
              'policy': params, 'calibration_mean_kappa': score, 'talks': {}}
    for i, (analysis, cues, probabilities) in talks.items():
        result['talks'][i] = {'role': 'calibration' if i in args.calibrate else 'held_out', 'cues': len(cues),
                              **compare_intervals(analysis, screen_intervals(cues, probabilities, **params))}
    print(json.dumps(result, indent=2))
    if args.out:
        save(args.out, result)


if __name__ == '__main__':
    sys.exit(main())
