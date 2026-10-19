"""Explanation goals and attention moves, independent of display templates.

These are inspectable product heuristics informed by the studies in
EXPLANATION_DESIGN.md, not a learned measure of comprehension.
"""
import math
import re


GOALS = {
    'mechanism': ['cutaway', 'annotated_image', 'demonstration_clip'],
    'comparison': ['aligned_comparison', 'sourced_chart', 'annotated_image'],
    'quantity': ['sourced_chart'],
    'location': ['map', 'annotated_image'],
    'sequence': ['demonstration_clip', 'annotated_image', 'timeline'],
    'example': ['documentary_clip', 'annotated_image'],
    'source': ['source_excerpt'],
    'orient': ['annotated_image', 'overview'],
}


def explanation_need(utterance, audience='', *, goal=None):
    """A provisional procurement brief. Unknown intent stays explicit."""
    patterns = [
        ('source', r'\b(?:show|read|quote|cite|open|see)\b.{0,45}\b(?:source|citation|evidence|quote|quotation)\b'),
        ('comparison', r'\b(?:compar\w*|versus|difference|instead of)\b'),
        ('quantity', r'\b(?:how much|how many|trend|measured|measurements|data|chart)\b'),
        ('mechanism', r'\b(?:how .{0,60}works?|why|mechanism|heat transfer|circulat\w*|flow\w*)\b'),
        ('location', r'\b(?:where|location|geograph\w*|map)\b'),
        ('sequence', r'\b(?:sequence|stages|step by step|what happens next)\b'),
        ('example', r'\b(?:show .{0,30}example|demonstrat\w*|what .{0,40}looks like)\b'),
    ]
    if not isinstance(goal, str) or goal not in GOALS:
        goal = next((name for name, pattern in patterns if re.search(pattern, utterance, re.I)), 'orient')
    return {'goal': goal, 'question': utterance[:600], 'audience': audience[:300],
            'preferred_media': list(GOALS[goal]),
            'attention_strategy': 'preserve_context_then_signal_relevant_part',
            'intent_status': 'provisional',
            'avoid': ['decorative_motion', 'unrelated_imagery', 'narration_as_paragraphs'],
            'missing_intent': goal == 'orient'}


def media_query(query, need):
    suffix = {'mechanism': ' mechanism diagram', 'comparison': ' comparison diagram',
              'quantity': ' data chart', 'location': ' map', 'sequence': ' sequence diagram'}
    return query + suffix.get((need or {}).get('goal'), '')


def presentation_fit(scene, need):
    """Relevance alone cannot authorize a fresh result to interrupt a visual.

    Source excerpts remain available backstage. Explicit source requests can
    display them. Semantic pixel checks must precede automatic image display;
    metadata relevance alone cannot establish visual explanatory fitness.
    """
    if not need:  # Existing stored research jobs have no explanation brief.
        return {'automatic': True, 'reason': 'legacy_request_without_explanation_brief'}
    if scene.get('kind') == 'evidence':
        explicit = need['goal'] == 'source'
        return {'automatic': explicit, 'reason': 'requested_source' if explicit else
                'Source found; an explanatory visual is still needed.'}
    if scene.get('kind') in {'image', 'annotated_image'}:
        verified = scene.get('web_source', {}).get('pixels_semantically_verified') is True
        return {'automatic': verified, 'reason': 'Pixel-reviewed supporting visual.' if verified else
                'Image metadata found; pixel-level explanatory fit remains unverified.'}
    return {'automatic': False, 'reason': 'The requested representation needs visual review.'}


def validate_annotations(values, refs):
    if not isinstance(values, list) or not 1 <= len(values) <= 8:
        raise ValueError('An annotated image needs 1–8 source-linked attention targets.')
    targets, ids = [], set()
    for raw in values:
        aid = raw.get('id', '')
        if not isinstance(aid, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', aid) or aid in ids:
            raise ValueError('Attention target IDs must be distinct, short lowercase identifiers.')
        ids.add(aid)
        target = {'id': aid}
        for key in ('x', 'y', 'label_x', 'label_y'):
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Attention coordinates must be finite fractions between zero and one.')
            target[key] = value
        label = ' '.join(str(raw.get('label', '')).split())
        if not label or len(label) > 80:
            raise ValueError('Use a short, directly attached attention label (1–80 characters).')
        quote = ' '.join(str(raw.get('quote', '')).split())
        if len(quote) < 12 or not any(quote in ref['quote'] for ref in refs):
            raise ValueError('Each attention label needs an exact quotation from the concept source refs.')
        cues = raw.get('cue_phrases', [])
        if not isinstance(cues, list) or not 1 <= len(cues) <= 8:
            raise ValueError('Each attention target needs 1–8 distinctive spoken cue phrases.')
        phrases = []
        for cue in cues:
            if not isinstance(cue, str) or not 2 <= len(re.findall(r'\w+', cue)) <= 12 or len(cue) > 100:
                raise ValueError('Attention cues must be phrases of 2–12 words, at most 100 characters.')
            phrases.append(' '.join(cue.lower().split()))
        target.update(label=label, quote=quote, cue_phrases=list(dict.fromkeys(phrases)))
        targets.append(target)
    return targets


def attention_targets(scene):
    if not scene:
        return []
    if scene.get('kind') == 'annotated_image':
        return scene['annotations']
    if scene.get('kind') == 'chart':
        axis = scene['x'].replace('_', ' ').lower()
        targets = []
        for i, row in enumerate(scene['data']):
            label = row['label'].strip()
            cues = [label + ' ' + axis, axis + ' ' + label]
            if len(label.split()) >= 2 or label.lower() not in {'low','medium','high','other','total','yes','no'}:
                cues.append(label)
            targets.append({'id':f'datum_{i}','label':label,'cue_phrases':cues})
        return targets
    return []


def focus_target(scene, utterance):
    """Unambiguous prepared phrases only; this does not infer audience cognition."""
    spoken = ' '.join(re.findall(r'\w+', utterance.lower()))
    matches = set()
    for target in attention_targets(scene):
        for phrase in target['cue_phrases']:
            words = ' '.join(re.findall(r'\w+', phrase.lower()))
            if not words:
                continue
            for match in re.finditer(r'(?<!\w)' + re.escape(words) + r'(?!\w)', spoken):
                before = spoken[:match.start()].split()[-3:]
                if not set(before) & {'not', 'ignore', 'skip', 'dont'}:
                    matches.add(target['id'])
    return next(iter(matches)) if len(matches) == 1 else None


def chart_comparison(scene, utterance):
    """Compute an explicitly requested pairwise comparison from approved data.

    Never treat 'twice' or another spoken numerical claim as the answer.
    Three categories, duplicate labels and unclear requests abstain.
    """
    if not scene or scene.get('kind') != 'chart':
        return None
    spoken = ' '.join(re.findall(r'\w+', utterance.lower()))
    if not re.search(r'\b(?:compare|comparison|difference between)\b', spoken):
        return None
    if re.search(r'\b(?:not|dont|don t|skip|ignore)\b.{0,20}\bcompar\w*', spoken):
        return None
    hits = []
    for index, row in enumerate(scene['data']):
        words = ' '.join(re.findall(r'\w+', row['label'].lower()))
        match = re.search(r'(?<!\w)' + re.escape(words) + r'(?!\w)', spoken) if words else None
        if match:
            hits.append((match.start(), index, row))
    if len(hits) != 2 or hits[0][2]['label'].lower() == hits[1][2]['label'].lower():
        return None
    hits.sort(key=lambda hit:hit[0])
    (_, a, first), (_, b, second) = hits
    delta=second['value']-first['value']
    if not math.isfinite(delta):
        return None
    ratio=second['value']/first['value'] if first['value']>0 and second['value']>=0 else None
    if ratio is not None and not math.isfinite(ratio):
        ratio=None
    return {'target_ids':[f'datum_{a}',f'datum_{b}'], 'first_index':a, 'second_index':b,
            'delta':delta, 'ratio':ratio,
            'derivation':'arithmetic_from_approved_chart_values'}
