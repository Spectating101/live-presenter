"""Durable approval boundary and conservative orchestration of prepared scenes."""
import asyncio
from collections import Counter, defaultdict
from contextlib import contextmanager
import copy
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
import secrets

from research_evidence_v10 import json_hash
from system1_v10 import JevBackend, System1Error
from .materials import ingest
from .planning import CopilotPreparation, PlanError, source_outline


class Conflict(ValueError):
    pass


def fresh_live():
    return {"active": False, "locked": False, "adviser_enabled": False, "current_scene_id": None, "history": [],
            "transcript": [], "last_seq": -1, "generation": uuid.uuid4().hex, "last_change": 0,
            "candidate_id": None, "candidate_count": 0, "decision": {"action": "HOLD", "reason": "Start a rehearsal after approving the material."}}


def reset_live(project):
    """Archive a bounded rehearsal, then create a clean transcript session."""
    previous = project['live']
    if previous.get('transcript'):
        project.setdefault('rehearsals', []).append({
            'stopped_at': time.time(), 'approval_hash': (project.get('approval') or {}).get('package_hash'),
            'transcript': previous['transcript'], 'last_scene_id': previous.get('current_scene_id')})
        project['rehearsals'] = project['rehearsals'][-10:]
    project['live'] = fresh_live()
    project['live']['adviser_enabled'] = previous.get('adviser_enabled', False)


def clear_candidate(live):
    live.update(candidate_id=None, candidate_count=0)
    live.pop('recommendation', None)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.locks = defaultdict(threading.RLock)

    def path(self, pid):
        if not re.fullmatch(r"[0-9a-f]{32}", pid):
            raise KeyError("Unknown presentation.")
        return self.root / (pid + ".json")

    def read(self, pid):
        try:
            return json.loads(self.path(pid).read_text())
        except FileNotFoundError:
            raise KeyError("Unknown presentation.") from None

    def save(self, project):
        path = self.path(project["id"])
        temp = path.with_suffix(".tmp")
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as file:
            file.write(json.dumps(project, ensure_ascii=False, allow_nan=False))
        temp.replace(path)

    @contextmanager
    def change(self, pid):
        with self.locks[pid]:
            project = self.read(pid)
            yield project
            project['state_version'] = project.get('state_version',0) + 1
            project["updated_at"] = time.time()
            self.save(project)

    def create(self, *, title, brief, audience, sources, provider="copilot"):
        if provider not in {"copilot", "outline"}:
            raise ValueError("Unknown preparation provider.")
        if not sources:
            raise ValueError("Add source material first.")
        if len(sources) > 8 or sum(s["characters"] for s in sources) > 130_000:
            raise ValueError("Use at most 8 materials and 130,000 extracted characters per presentation.")
        if len({s['id'] for s in sources}) != len(sources):
            raise ValueError("The same material was supplied twice.")
        project = {"id": uuid.uuid4().hex, "title": title[:120] or "Untitled presentation", "brief": brief[:3000],
                   "audience": audience[:500], "sources": sources, "provider": provider, "revision": 0,
                   "plan_revision": -1, "plan": None, "approval": None, "messages": [],
                   "state_version": 0,
                   "job": {"status": "idle"}, "live": fresh_live(), "updated_at": time.time()}
        self.save(project)
        return project

    def listing(self):
        projects = [json.loads(p.read_text()) for p in self.root.glob("*.json")]
        return [{k: p[k] for k in ("id", "title", "updated_at", "revision")} | {"approved": bool(p["approval"])}
                for p in sorted(projects, key=lambda p: p["updated_at"], reverse=True)]


class Studio:
    def __init__(self, store, *, planner=None, live_assessor=None, dwell_s=2.5):
        self.store = store
        self.planner = planner or CopilotPreparation()
        self.live_assessor = live_assessor
        self.dwell_s = dwell_s
        # Recover interrupted preparation jobs; never resume a public stage after restart.
        for path in store.root.glob("*.json"):
            with store.change(path.stem) as p:
                reset_live(p)
                p['live']['decision'] = {'action':'HOLD','reason':'Rehearsal stopped. Start again when ready.'}
                if p["job"]["status"] == "working":
                    p["job"] = {"status": "error", "error": "Preparation was interrupted by a server restart. Retry to continue."}

    def prepare(self, pid, message="", *, background=True):
        with self.store.change(pid) as p:
            if p["live"]["active"]:
                raise Conflict("Stop the rehearsal before changing the preparation.")
            if p["job"]["status"] == "working":
                raise Conflict("Preparation is already running.")
            if message.strip():
                if p["provider"] == "outline":
                    raise Conflict("Source outline mode does not interpret free-form messages. Choose Conversation mode for discussion.")
                p["messages"].append({"role": "user", "content": message[:5000]})
            p["approval"] = None
            p["revision"] += 1
            p["live"] = fresh_live()
            p["job"] = {"status": "working", "revision": p["revision"], "started_at": time.time()}
            snapshot = copy.deepcopy(p)

        def work():
            try:
                plan = source_outline(snapshot) if snapshot["provider"] == "outline" else self.planner.prepare(snapshot)
                with self.store.change(pid) as current:
                    if current["revision"] != snapshot["revision"]:
                        return
                    current["plan"] = plan
                    current["plan_revision"] = snapshot["revision"]
                    current["messages"].append({"role": "assistant", "content": plan["understanding"]})
                    current["job"] = {"status": "ready"}
            except Exception as e:
                with self.store.change(pid) as current:
                    if current["revision"] == snapshot["revision"]:
                        current["job"] = {"status": "error", "error": str(e)[:700] if isinstance(e, (PlanError, ValueError)) else "Preparation failed. Your sources and conversation are saved."}
        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        return self.store.read(pid)

    def context(self, pid, *, title, brief, audience, provider):
        if provider not in {"copilot", "outline"}:
            raise ValueError("Unknown preparation provider.")
        with self.store.change(pid) as p:
            if p["live"]["active"] or p["job"]["status"] == "working":
                raise Conflict("Stop the rehearsal or wait for preparation before editing the brief.")
            p.update(title=title[:120] or p["title"], brief=brief[:3000], audience=audience[:500], provider=provider,
                     revision=p["revision"] + 1, approval=None, live=fresh_live())
        return self.prepare(pid)

    def approve(self, pid, revision, reviewed):
        with self.store.change(pid) as p:
            if reviewed is not True or not p["plan"] or p["job"]["status"] != "ready":
                raise Conflict("Review a completed preparation before approving it.")
            if p["plan_revision"] != p["revision"] or revision != p["revision"]:
                raise Conflict("The preparation changed. Review the current revision.")
            if any(q["blocking"] for q in p["plan"]["questions"]):
                raise Conflict("Answer the blocking clarification questions before approval.")
            package = copy.deepcopy(p['plan'])
            for scene in package['scenes']:
                scene['review_status'] = 'presenter_approved'
            p["approval"] = {"revision": revision, "package": package,
                             "package_hash": json_hash(package), "source_hash": json_hash(p["sources"]),
                             "approved_at": time.time()}
            p["live"] = fresh_live()
        return self.store.read(pid)

    def add_sources(self, pid, sources):
        with self.store.change(pid) as p:
            if p['live']['active'] or p['job']['status'] == 'working':
                raise Conflict('Stop the rehearsal or wait for preparation before adding material.')
            combined = p['sources'] + sources
            if (len(combined) > 8 or sum(s['characters'] for s in combined) > 130_000
                    or len({s['id'] for s in combined}) != len(combined)):
                raise ValueError('Use at most 8 distinct materials and 130,000 extracted characters.')
            p.update(sources=combined, revision=p['revision'] + 1, approval=None, live=fresh_live())
        return self.prepare(pid)

    @staticmethod
    def package(p):
        a = p["approval"]
        if (not a or a["revision"] != p["revision"] or a["package_hash"] != json_hash(a["package"])
                or a["source_hash"] != json_hash(p["sources"])):
            raise Conflict("This material has no current, intact approval.")
        return a["package"]

    def control(self, pid, action, scene_id=None, enabled=None):
        with self.store.change(pid) as p:
            package = self.package(p)
            live, scenes = p["live"], package["scenes"]
            if action not in {'start','adviser','stop'} and not live['active']:
                raise Conflict('Start the rehearsal before using stage controls.')
            if action == "start":
                if live['active']:
                    return p
                reset_live(p)
                live = p['live']
                live["active"] = True
                live["locked"] = False
                if live["current_scene_id"] is None:
                    self.show(live, scenes[0]["id"], "Presenter started the rehearsal.")
            elif action == "stop":
                reset_live(p)
                live = p['live']
                live['decision'] = {'action':'HOLD','reason':'Rehearsal stopped.'}
            elif action == "hold":
                clear_candidate(live)
                live['generation'] = uuid.uuid4().hex
                live["locked"] = True
                live["decision"] = {"action": "HOLD", "reason": "Stage held by presenter."}
            elif action == "resume":
                clear_candidate(live)
                live["locked"] = False
                live["generation"] = uuid.uuid4().hex
            elif action == 'adviser':
                clear_candidate(live)
                live['adviser_enabled'] = enabled is True
                live['generation'] = uuid.uuid4().hex
            elif action in {"next", "back", "show"}:
                ids = [s["id"] for s in scenes]
                current = next((s for s in scenes if s['id'] == live['current_scene_id']), scenes[0])
                concepts = [c['id'] for c in package['concepts']]
                next_concept = concepts[min(len(concepts) - 1, concepts.index(current['concept_id']) + 1)]
                target = scene_id if action == 'show' else (live['history'].pop() if action == 'back' and live['history'] else
                         next((s['id'] for s in scenes if s['concept_id'] == next_concept), scenes[0]['id']) if action == 'next' else current['id'])
                if target not in ids:
                    raise ValueError("That visual is not in the approved package.")
                clear_candidate(live)
                live['generation'] = uuid.uuid4().hex
                self.show(live, target, "Presenter selected a prepared visual.", remember=action != 'back')
            else:
                raise ValueError("Unknown stage control.")
        return self.store.read(pid)

    @staticmethod
    def show(live, scene_id, reason, *, remember=True):
        if scene_id != live["current_scene_id"]:
            if live["current_scene_id"] and remember:
                live["history"].append(live["current_scene_id"])
                live["history"] = live["history"][-100:]
            live["current_scene_id"] = scene_id
            live["last_change"] = time.time()
        live["decision"] = {"action": "SHOW", "scene_id": scene_id, "reason": reason}

    def transcript(self, pid, utterance, seq, *, final=True, generation=None):
        utterance = utterance.strip()[:3000]
        if not utterance:
            raise ValueError("Add an utterance first.")
        with self.store.change(pid) as p:
            package = copy.deepcopy(self.package(p))
            live = p["live"]
            if not live["active"]:
                raise Conflict("Start the rehearsal first.")
            if generation != live["generation"]:
                raise Conflict("This transcript belongs to an older rehearsal session.")
            if not final or seq <= live["last_seq"]:
                return p
            live["last_seq"] = seq
            live["transcript"].append({"text": utterance, "seq": seq, "at": time.time()})
            live["transcript"] = live["transcript"][-150:]
            session = live["generation"]
            use_adviser = live.get('adviser_enabled', False)
        recommendation = recommend(package, utterance)
        if self.live_assessor and use_adviser:
            try:
                advice = self.live_assessor(package, utterance)
                if (not isinstance(advice,dict) or not isinstance(advice.get('confidence'),(int,float))
                        or not math.isfinite(advice['confidence']) or not 0 <= advice['confidence'] <= 1
                        or (advice.get('scene_id') is not None and not isinstance(advice['scene_id'],str))):
                    raise ValueError('Malformed adviser output')
                recommendation["advice"] = advice
                # Jev can veto/confirm a candidate; it cannot invent a scene or
                # bypass local semantic support, approval, hold or dwell rules.
                scenes = {s['id']: s for s in package['scenes']}
                local = scenes.get(recommendation['scene_id'])
                advised = scenes.get(advice.get('scene_id'))
                if local and advised and advised['concept_id'] == local['concept_id']:
                    recommendation['scene_id'] = advised['id']
                    recommendation['confirmed'] = advice.get('confidence', 0) >= .65
                elif (advised and advised['concept_id'] in recommendation.get('supported_concepts',[])
                      and advice['confidence'] >= .84):
                    # Resolve ambiguity among locally supported, approved ideas.
                    # No lexical support still means HOLD, however confident the adviser is.
                    recommendation['scene_id'] = advised['id']
                    recommendation['confirmed'] = True
                elif advice.get('confidence', 0) >= .65:
                    recommendation['scene_id'] = None
                    recommendation['confirmed'] = False
            except (ValueError,TypeError,AttributeError):
                recommendation['scene_id'] = None
                recommendation['advice'] = {'error':'Live adviser output was invalid; retaining the stage.'}
            except (System1Error, OSError, TimeoutError):
                recommendation["advice"] = {"error": "Live adviser unavailable; using conservative prepared-content matching."}
        with self.store.change(pid) as p:
            self.package(p)
            live = p["live"]
            if live["generation"] != session or seq != live["last_seq"] or not live["active"]:
                return p  # Delayed advice cannot change a newer session/utterance.
            candidate = recommendation["scene_id"]
            live["candidate_count"] = live["candidate_count"] + 1 if candidate == live["candidate_id"] else 1
            live["candidate_id"] = candidate
            live["recommendation"] = recommendation
            reason = ("Several prepared ideas could fit; retaining the stage until the meaning is clearer."
                      if recommendation.get('supported_concepts') else "No supported prepared visual for this utterance; retaining the stage.")
            if live["locked"]:
                reason = "Stage held by presenter; recommendation stays backstage."
            elif candidate and recommendation["score"] >= .45:
                if time.time() - live["last_change"] < self.dwell_s:
                    reason = "Current visual is still inside its minimum display time."
                elif recommendation["confirmed"] or recommendation["score"] >= .88 or live["candidate_count"] >= 2:
                    self.show(live, candidate, "Prepared visual matched the spoken explanation.")
                    return p
                else:
                    reason = "Possible match prepared backstage; waiting for stronger support."
            live["decision"] = {"action": "WARM" if candidate else "HOLD", "reason": reason}
        return self.store.read(pid)


STOP = set("a an the of to in is it and or for with this that we you our can are as be from on at by have has what how why now let about explain first then through before after they these those did do does not so which more alone using".split())


def tokens(s):
    words = (t.lower() for t in re.findall(r"[A-Za-z0-9]+", s))
    return {w[:-1] if w.endswith('s') and not w.endswith(('ss','us','is')) else w
            for w in words if len(w) > 2 and w not in STOP}


def recommend(package, utterance):
    query = tokens(utterance)
    frequency = Counter(word for c in package['concepts'] for word in tokens(' '.join([c['title'], *c['aliases'], c['summary']])))
    scores = []
    for c in package["concepts"]:
        cues = [c["title"], *c["aliases"]]
        # A speaker can use the supplied source's language instead of a model's
        # short summary. Quotes supply lexical support, never new live content.
        words = tokens(" ".join([*cues, c['summary'], *(r['quote'] for r in c['source_refs'])]))
        overlap = len(query & words)
        score = overlap / max(1, len(query))
        title_match = len(c['title']) >= 6 and c['title'].lower() in utterance.lower()
        exact = title_match or any(
            len(phrase.strip()) >= 6 and phrase.lower().strip() in utterance.lower()
            and (len(tokens(phrase)) >= 2 or all(frequency[w] == 1 for w in tokens(phrase)))
            for phrase in c['aliases'])
        if exact and overlap >= 1:
            score = max(score, 1.0 if title_match else .9)
        if overlap < 2 and not exact:
            score *= .3
        scores.append((score, c))
    scores.sort(key=lambda pair: pair[0], reverse=True)
    score, concept = scores[0]
    supported = [c['id'] for value,c in scores if value >= .45]
    margin = score - (scores[1][0] if len(scores) > 1 else 0)
    if score < .45 or margin < .10:
        return {"scene_id": None, "score": round(score, 3), "supported_concepts":supported, "confirmed": False, "method": "prepared_cues"}
    scenes = [s for s in package["scenes"] if s["concept_id"] == concept["id"]]
    kind = preferred_kind(utterance)
    scene = next((s for s in scenes if s["kind"] == kind), scenes[0])
    return {"scene_id": scene["id"], "score": round(score, 3), "supported_concepts":supported, "confirmed": False, "method": "prepared_cues"}


def preferred_kind(utterance):
    words = tokens(utterance)
    for kind, cues in [('evidence', {'evidence','source','citation','quote'}),
                       ('comparison', {'compare','versus','difference'}),
                       ('chart', {'chart','data','measured','trend'})]:
        if words & cues:
            return kind
    return None


def jev_adviser(package, utterance):
    choices = {c['id']: c['title'] + ': ' + c['summary'] for c in package['concepts']}
    choices['hold'] = 'The utterance is off-topic or does not clearly match a prepared idea.'
    hints = {'definition':'Explain or define an idea.', 'flow':'Trace a process or sequence.',
             'comparison':'Compare options side by side.', 'chart':'Show numeric patterns or measurements.',
             'metric':'Emphasize one number.', 'evidence':'Explicitly request or quote source evidence.'}
    questions = {
        'concept': {'type':'choice', 'instructions':'Which prepared IDEA is the speaker explaining? Choose hold for off-topic or ambiguous speech. Ignore which visual form is available.', 'criteria':choices},
        'representation': {'type':'choice', 'instructions':'Which visual form would support the way the speaker is explaining the idea? Evidence is for explicit source requests, not every factual claim.',
                           'criteria': {k:v for k,v in hints.items() if any(s['kind'] == k for s in package['scenes'])}}}
    state = {"utterance": utterance, "prepared_concepts": package["concepts"]}
    response = asyncio.run(JevBackend(timeout_s=1.2).ask(state, questions))
    answer, representation = response.answers['concept'], response.answers['representation']
    scenes = [s for s in package['scenes'] if s['concept_id'] == answer.value]
    # Concept confidence must not be diluted across several equally valid
    # visual alternatives. Representation selection stays inside that idea.
    kind = preferred_kind(utterance) or (representation.value if representation.confidence >= .55 else None)
    scene = next((s for s in scenes if s['kind'] == kind), scenes[0] if scenes else None)
    return {"scene_id": scene['id'] if scene else None, "confidence": answer.confidence,
            'concept_id':answer.value, 'representation':representation.value,
            'representation_confidence':representation.confidence,
            "model": response.model, "latency_ms": response.latency_ms}
