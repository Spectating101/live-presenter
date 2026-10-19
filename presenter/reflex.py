"""Compile finite cues from an approved package and its bound source passages.

This is a lexical fast path, not a semantic correctness or confidence estimator.
The ordinary controller still owns approval, hold, dwell and stale-result checks.
"""
from collections import Counter
import math
from .language import sequence, tokens
from .selection import choose_scene

FILLER = set('look here there just will would could really very say said yes know everyone something thing also got get all even well right like when where who want tell told today'.split())


def cue_tokens(text):
    return tokens(text) - FILLER


def phrases(text):
    ordered = [w for w in sequence(text) if w not in FILLER]
    return {tuple(ordered[i:i+n]) for n in (2,3,4) for i in range(len(ordered)-n+1)}


class CueIndex:
    def __init__(self, package, sources):
        units = {u['id']: u['text'] for s in sources for u in s['units']}
        self.source_phrases = {}
        for uid,text in units.items():
            for phrase in phrases(text):
                self.source_phrases.setdefault(phrase,set()).add(uid)
        self.rows = []
        self.package = package
        for c in package['concepts']:
            core = [c['title'], c['summary'], *c['aliases'], *(r['quote'] for r in c['source_refs'])]
            linked = [units[r['unit_id']] for r in c['source_refs'] if r['unit_id'] in units]
            self.rows.append({'concept_id':c['id'], 'core':cue_tokens(' '.join(core)),
                              'linked':cue_tokens(' '.join(linked)),
                              'unit_ids':{r['unit_id'] for r in c['source_refs']},
                              'explicit':set().union(*(phrases(t) for t in [c['title'],*c['aliases']])),
                              'phrases':set().union(*(phrases(t) for t in [*core,*linked]))})
        self.frequency = Counter(w for row in self.rows for w in row['core'] | row['linked'])
        self.phrase_frequency = Counter(p for row in self.rows for p in row['phrases'])
        self.weights = {w:1 + math.log((len(self.rows)+1)/(count+1)) for w,count in self.frequency.items()}

    def match(self, utterance, preferred=None):
        query, query_phrases = cue_tokens(utterance), phrases(utterance)
        denominator = sum(self.weights.get(w, 2.5) for w in query) or 1
        ranked = []
        for row in self.rows:
            overlap = query & (row['core'] | row['linked'])
            distinct = {w for w in overlap if self.frequency[w] <= max(1,len(self.rows)//2)}
            score = sum(self.weights[w] * (1 if w in row['core'] else .65) for w in overlap) / denominator
            cue = any(self.phrase_frequency[p] == 1 and any(w in distinct for w in p)
                      and (p in row['explicit'] or self.source_phrases.get(p,set()) <= row['unit_ids'])
                      for p in query_phrases & row['phrases'])
            if len(overlap) < 2 or not distinct:
                score = 0
            elif cue and score >= .3:
                score = max(score, .92)
            ranked.append((score,row,cue))
        ranked.sort(key=lambda r:r[0], reverse=True)
        score,row,cue = ranked[0]
        margin = score - (ranked[1][0] if len(ranked)>1 else 0)
        supported = [r['concept_id'] for value,r,_ in ranked if value >= .45]
        chosen = score >= .45 and margin >= .12
        scene = choose_scene(self.package,row['concept_id'],preferred)
        return {'scene_id':scene['id'] if chosen else None,'score':round(score,3),
                'supported_concepts':supported,'confirmed':chosen and cue and score >= .88 and margin >= .2,
                'method':'compiled_source_cues','margin':round(margin,3),
                'cue_observed':cue,'reflex_ready':chosen and cue and score >= .88 and margin >= .2}
