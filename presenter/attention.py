"""Jev's live judgment of whether a moment calls for the screen or the speaker.

The label definitions are shared with the offline evaluation in moment.py so the
benchmark and the live stage ask the same question. Jev can also look at the
presenter's own supplied visuals and say which one the words are about; it can never
invent a visual, and only a confident answer at a "look" moment reaches the stage.
"""
import asyncio
import base64
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


MATCH_GROUP = 24


class VisualMatcher:
    """Asks Jev which supplied visual the speaker is talking about, from the pictures themselves."""
    def __init__(self, visuals, backend=None):
        # visuals: (scene_id, jpeg_bytes or None, title). Pictures are 280-1568 px per side, as Jev requires.
        self.visuals, self.backend = list(visuals), backend

    def question(self, group, words):
        assets, criteria = {}, {'none':'The speaker is not talking about anything shown in these visuals.'}
        for i, (_, jpeg, title) in enumerate(group):
            if jpeg:
                ref = 'img-' + hashlib.sha256(jpeg).hexdigest()[:20]
                assets[ref] = {'type':'image', 'format':'jpg', 'data_base64':base64.b64encode(jpeg).decode()}
                criteria[f'v{i}'] = f'The speaker is talking about what this slide shows: {ref}'
            else:
                criteria[f'v{i}'] = f'The speaker is talking about this chart: {title}'
        return {'pick':{'type':'choice', 'criteria':criteria, 'instructions':
                        f'A presenter has these slides ready. They just said: "{words}". '
                        'Which slide, if any, shows what they are talking about right now?'}}, assets

    async def ask_all(self, words):
        backend = self.backend or JevBackend(timeout_s=1.2)
        groups = [self.visuals[i:i+MATCH_GROUP] for i in range(0, len(self.visuals), MATCH_GROUP)]
        async def one(group):
            questions, assets = self.question(group, words)
            answer = (await backend.ask(STATE, questions, assets)).answers['pick']
            if answer.value == 'none':
                return None, 0.0
            return group[int(answer.value[1:])][0], answer.probabilities.get(answer.value, 0.0)
        return await asyncio.gather(*(one(group) for group in groups))

    def __call__(self, utterance, earlier=()):
        words = ' '.join([*earlier, utterance])
        scene_id, confidence = max(asyncio.run(self.ask_all(words)), key=lambda pick: pick[1])
        return {'scene_id':scene_id, 'confidence':confidence}
