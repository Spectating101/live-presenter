"""Jev's live judgment of whether a moment calls for the screen or the speaker.

The label definitions are shared with the offline evaluation in moment.py so the
benchmark and the live stage ask the same question. The signal only gates a visual
that already exists; it cannot choose or invent one.
"""
import asyncio
import hashlib
import json

from system1_v10 import JevBackend

MOMENTS = {
    'look': 'The words point the audience at something to see right now: a number, chart, comparison, map, '
            'picture, place, person or object that the speaker is showing or describing concretely.',
    'listen': 'The speaker is telling a story, giving an opinion, joking, addressing the audience or making a '
              'general point. Watching the speaker is enough.',
    'transition': 'A greeting, thanks, filler or a move between topics.',
}
MOMENT_KEY = hashlib.sha256(json.dumps(MOMENTS, sort_keys=True).encode()).hexdigest()[:16]
STATE = 'Captions from a live presentation, heard in order. Only the words so far are known.'


def cue_questions(cues, indices, context=2):
    questions = {}
    for i in indices:
        before = ' '.join(c[2] for c in cues[max(0, i - context):i])
        questions[f'c{i}'] = {'type': 'choice', 'criteria': MOMENTS,
                              'instructions': (f'Earlier: "{before}" ' if before else '')
                              + f'Now the speaker says: "{cues[i][2]}". What does this latest part call for?'}
    return questions


def past_context(transcript, now, spacing_s=4.0, count=2):
    """Earlier words without the overlap of rolling recognition windows.

    Windows arrive every second and each repeats most of the last one, so take
    only entries at least one window apart, newest first."""
    picked, before = [], now - spacing_s
    for row in reversed(transcript):
        if len(picked) == count:
            break
        if row['at'] <= before:
            picked.append(row['text'])
            before = row['at'] - spacing_s
    return picked[::-1]


def jev_moment(utterance, earlier=()):
    cues = [(0, 0, text) for text in [*earlier, utterance]]
    last = len(cues) - 1
    response = asyncio.run(JevBackend(timeout_s=1.2).ask(STATE, cue_questions(cues, [last])))
    answer = response.answers[f'c{last}']
    return {'look': answer.probabilities['look'], 'value': answer.value,
            'model': response.model, 'latency_ms': response.latency_ms}
