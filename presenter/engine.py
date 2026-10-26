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
from .language import tokens
from .reflex import CueIndex
from .selection import choose_scene
from .explanation import focus_target, attention_targets, chart_comparison


class Conflict(ValueError):
    pass


# How a talk balances the speaker and the screen. "persist" keeps the last
# visual until another replaces it (slide-deck behavior). "speaker_led" starts
# on the speaker and returns attention to the speaker once speech stops
# supporting the visual; release_after_s is calibrated against edited talks.
STYLES = {
    'persist': {'open_with_visual': True, 'release_after_s': None},
    'speaker_led': {'open_with_visual': False, 'release_after_s': 6.0},
}


class DeadlineAdviser:
    """At most one outstanding advisory call; late results have no authority."""
    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False

    def ask(self, assessor, package, utterance, timeout):
        with self.lock:
            if self.busy or timeout <= 0:
                raise TimeoutError('Live adviser is busy or its input expired.')
            self.busy = True
        completed, result = threading.Event(), {}
        def request():
            try:
                result['value'] = assessor(package,utterance)
            except Exception as error:
                result['error'] = error
            finally:
                with self.lock:
                    self.busy = False
                completed.set()
        threading.Thread(target=request,daemon=True,name='presenter-advice').start()
        if not completed.wait(timeout):
            raise TimeoutError('Live advice exceeded the current audio deadline.')
        if 'error' in result:
            raise result['error']
        return result['value']


def fresh_live():
    return {"active": False, "locked": False, "adviser_enabled": False, "reflex_enabled": False, "current_scene_id": None, "history": [],
            'research_enabled':False,'research_scene':None,'research':{},'attention':None,'last_focus_change':0,
            'style':'persist','last_support':0,
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
    project['live']['reflex_enabled'] = previous.get('reflex_enabled', False)
    project['live']['research_enabled'] = previous.get('research_enabled',False)
    project['live']['style'] = previous.get('style','persist')


def clear_candidate(live):
    live.update(candidate_id=None, candidate_count=0)
    live.pop('recommendation', None)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.locks = defaultdict(threading.RLock)
        self.conditions = {}

    def condition(self, pid):
        self.path(pid)
        return self.conditions.setdefault(pid, threading.Condition(self.locks[pid]))

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
            self.condition(pid).notify_all()

    def create(self, *, title, brief, audience, sources, provider="copilot"):
        if provider not in {"copilot", "outline"}:
            raise ValueError("Unknown preparation provider.")
        if not sources:
            raise ValueError("Add source material first.")
        if len(sources) > 8 or sum(s["characters"] for s in sources) > 130_000:
            raise ValueError("Use at most 8 materials and 130,000 extracted characters per presentation.")
        if len({s['id'] for s in sources}) != len(sources):
            raise ValueError("The same material was supplied twice.")
        if sum(len(s.get('asset',{}).get('data_url','')) for s in sources) > 2_000_000:
            raise ValueError('Keep supplied images under 1.5 MB combined before encoding.')
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
    def __init__(self, store, *, planner=None, live_assessor=None, dwell_s=2.5, clock=None):
        self.store = store
        self.planner = planner or CopilotPreparation()
        self.live_assessor = live_assessor
        self.deadline_adviser = DeadlineAdviser()
        self.dwell_s = dwell_s
        self.clock = clock or time.time
        self.cue_indexes = {}
        self.cue_lock = threading.RLock()
        self.research = None
        self.preparation_research = None
        # Recover interrupted preparation jobs; never resume a public stage after restart.
        for path in store.root.glob("*.json"):
            with store.change(path.stem) as p:
                reset_live(p)
                p['live']['decision'] = {'action':'HOLD','reason':'Rehearsal stopped. Start again when ready.'}
                if p["job"]["status"] == "working":
                    p["job"] = {"status": "error", "error": "Preparation was interrupted by a server restart. Retry to continue."}

    def prepare(self, pid, message="", *, background=True, research_refresh=False):
        if research_refresh and self.preparation_research is None:
            raise Conflict('Start the studio with online preparation research enabled first.')
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
                if self.preparation_research and (research_refresh or self.preparation_research.needs(snapshot)):
                    enriched=self.preparation_research.enrich(snapshot)
                    snapshot.update(sources=enriched['sources'],preparation_research=enriched['preparation_research'])
                    with self.store.change(pid) as current:
                        if current['revision']!=snapshot['revision']:return
                        current.update(sources=copy.deepcopy(snapshot['sources']),preparation_research=copy.deepcopy(snapshot['preparation_research']))
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
                if scene.get('web_source'):scene['web_source']['presenter_reviewed']=True
            p["approval"] = {"revision": revision, "package": package,
                             "package_hash": json_hash(package), "source_hash": json_hash(p["sources"]),
                             "approved_at": time.time()}
            p["live"] = fresh_live()
        return self.store.read(pid)

    def default_scene(self, pid, scene_id):
        with self.store.change(pid) as p:
            if p['live']['active'] or p['job']['status'] != 'ready' or not p['plan']:
                raise Conflict('Stop the rehearsal and finish preparation before choosing a default visual.')
            scene = next((s for s in p['plan']['scenes'] if s['id'] == scene_id), None)
            if not scene:
                raise ValueError('Choose an existing prepared visual.')
            concept = next(c for c in p['plan']['concepts'] if c['id'] == scene['concept_id'])
            concept['default_scene_id'] = scene_id
            p['revision'] += 1
            p['plan_revision'] = p['revision']
            p['approval'] = None
            p['live'] = fresh_live()
            p['messages'].append({'role':'user','content':f'Use “{scene["title"]}” ({scene["kind"]}) as the default visual for “{concept["title"]}”.'})
        return self.store.read(pid)

    def add_sources(self, pid, sources):
        with self.store.change(pid) as p:
            if p['live']['active'] or p['job']['status'] == 'working':
                raise Conflict('Stop the rehearsal or wait for preparation before adding material.')
            combined = p['sources'] + sources
            if (len(combined) > 8 or sum(s['characters'] for s in combined) > 130_000
                    or len({s['id'] for s in combined}) != len(combined)):
                raise ValueError('Use at most 8 distinct materials and 130,000 extracted characters.')
            if sum(len(s.get('asset',{}).get('data_url','')) for s in combined) > 2_000_000:
                raise ValueError('Keep supplied images under 1.5 MB combined before encoding.')
            p.update(sources=combined, revision=p['revision'] + 1, approval=None, live=fresh_live())
        return self.prepare(pid)

    @staticmethod
    def package(p):
        a = p["approval"]
        if (not a or a["revision"] != p["revision"] or a["package_hash"] != json_hash(a["package"])
                or a["source_hash"] != json_hash(p["sources"])):
            raise Conflict("This material has no current, intact approval.")
        return a["package"]

    def control(self, pid, action, scene_id=None, enabled=None, annotation_id=None, style=None):
        with self.store.change(pid) as p:
            package = self.package(p)
            live, scenes = p["live"], package["scenes"]
            if action not in {'start','adviser','reflex','research','stop','style'} and not live['active']:
                raise Conflict('Start the rehearsal before using stage controls.')
            if action == "start":
                if live['active']:
                    return p
                reset_live(p)
                live = p['live']
                live["active"] = True
                self.cue_index(p)
                live["locked"] = False
                if STYLES[live.get('style','persist')]['open_with_visual']:
                    self.show(live, choose_scene(package,package['concepts'][0]['id'])["id"], "Presenter started the rehearsal.")
                else:
                    live['decision'] = {'action':'HOLD','reason':'The speaker has the stage until a visual is needed.'}
            elif action == "stop":
                reset_live(p)
                live = p['live']
                live['decision'] = {'action':'HOLD','reason':'Rehearsal stopped.'}
            elif action == 'style':
                if style not in STYLES:
                    raise ValueError('Choose a known presentation style.')
                clear_candidate(live)
                live['style'] = style
                live['generation'] = uuid.uuid4().hex
            elif action == 'clear':
                clear_candidate(live)
                live['generation'] = uuid.uuid4().hex
                self.release(live, 'Presenter returned attention to the speaker.')
            elif action == "hold":
                clear_candidate(live)
                live['generation'] = uuid.uuid4().hex
                live["locked"] = True
                live["decision"] = {"action": "HOLD", "reason": "Stage held by presenter."}
            elif action == "resume":
                clear_candidate(live)
                live["locked"] = False
                live["generation"] = uuid.uuid4().hex
            elif action in {'adviser','reflex','research'}:
                if action=='research' and self.research is None:
                    raise Conflict('Start the studio with live research enabled first.')
                clear_candidate(live)
                live[action + '_enabled'] = enabled is True
                if action=='research':
                    live['research'].update(request_id='',status='idle')
                    if not enabled:live['research_scene']=None
                if action == 'reflex' and enabled is True:
                    self.cue_index(p)
                live['generation'] = uuid.uuid4().hex
            elif action=='research-show':
                scene=next((s for s in live.get('research',{}).get('items',[]) if s['id']==scene_id),None)
                if not scene or not live.get('research_enabled'):
                    raise ValueError('Choose a retrieved visual from this rehearsal.')
                clear_candidate(live);live['generation']=uuid.uuid4().hex
                live['research_scene']=copy.deepcopy(scene);live['last_change']=self.clock()
                live['attention']=None
                live['decision']={'action':'SHOW_RESEARCH','scene_id':scene['id'],'reason':'Presenter selected a retrieved web source.'}
            elif action == 'focus':
                scene = next((s for s in scenes if s['id'] == live['current_scene_id']), None)
                if not scene or not attention_targets(scene) or live.get('research_scene'):
                    raise Conflict('Focus needs the current prepared illustration or chart.')
                if annotation_id is not None and annotation_id not in {a['id'] for a in attention_targets(scene)}:
                    raise ValueError('Choose a prepared attention target.')
                clear_candidate(live);live['generation']=uuid.uuid4().hex
                self.focus(live, scene, annotation_id, 'Presenter directed attention within the current visual.')
            elif action in {"next", "back", "show"}:
                ids = [s["id"] for s in scenes]
                current = next((s for s in scenes if s['id'] == live['current_scene_id']), scenes[0])
                concepts = [c['id'] for c in package['concepts']]
                next_concept = concepts[min(len(concepts) - 1, concepts.index(current['concept_id']) + 1)]
                target = scene_id if action == 'show' else (live['history'].pop() if action == 'back' and live['history'] else
                         choose_scene(package,next_concept)['id'] if action == 'next' else current['id'])
                if target not in ids:
                    raise ValueError("That visual is not in the approved package.")
                clear_candidate(live)
                live['generation'] = uuid.uuid4().hex
                self.show(live, target, "Presenter selected a prepared visual.", remember=action != 'back')
            else:
                raise ValueError("Unknown stage control.")
            if action!='start':
                live.setdefault('research',{}).update(request_id='',status='idle')
        return self.store.read(pid)

    def show(self, live, scene_id, reason, *, remember=True):
        if live.get('research_scene') or scene_id != live['current_scene_id']:
            live['attention'] = None
            live['last_focus_change'] = 0
        live['research_scene']=None
        if scene_id != live["current_scene_id"]:
            if live["current_scene_id"] and remember:
                live["history"].append(live["current_scene_id"])
                live["history"] = live["history"][-100:]
            live["current_scene_id"] = scene_id
            live["last_change"] = self.clock()
        live["decision"] = {"action": "SHOW", "scene_id": scene_id, "reason": reason}

    def release(self, live, reason):
        """Clear the screen so attention returns to the speaker."""
        if live['current_scene_id']:
            live['history'].append(live['current_scene_id'])
            live['history'] = live['history'][-100:]
        live.update(current_scene_id=None, research_scene=None, attention=None, last_focus_change=0,
                    last_change=self.clock())
        live['decision'] = {'action':'CLEAR', 'reason':reason}

    def focus(self, live, scene, annotation_id, reason):
        live['attention'] = {'scene_id': scene['id'], 'annotation_id': annotation_id}
        live['last_focus_change'] = self.clock()
        live['decision'] = {'action':'FOCUS', 'scene_id':scene['id'], 'annotation_id':annotation_id, 'reason':reason}

    def cue_index(self, project):
        key = (project['approval']['package_hash'], project['approval']['source_hash'])
        with self.cue_lock:
            if key not in self.cue_indexes:
                # Compile before speech starts; reuse the bound finite index.
                if len(self.cue_indexes) >= 8:
                    self.cue_indexes.pop(next(iter(self.cue_indexes)))
                self.cue_indexes[key] = CueIndex(self.package(project), project['sources'])
            return self.cue_indexes[key]

    def invalidate_input(self, pid, generation):
        """Cancel pending input without changing the presenter's chosen visual."""
        with self.store.change(pid) as p:
            self.package(p)
            if not p['live']['active'] or p['live']['generation'] != generation:
                raise Conflict('This input belongs to an older rehearsal.')
            clear_candidate(p['live'])
            p['live']['generation'] = uuid.uuid4().hex
        return self.store.read(pid)

    def transcript(self, pid, utterance, seq, *, final=True, generation=None, expires_at=None):
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
            if expires_at is not None and self.clock() > expires_at:
                raise Conflict('This audio has expired.')
            if seq is None:
                seq = live['last_seq'] + 1  # Internal PCM worker allocates under the project lock.
            if not final or seq <= live["last_seq"]:
                return p
            live["last_seq"] = seq
            live["transcript"].append({"text": utterance, "seq": seq, "at": self.clock()})
            live["transcript"] = live["transcript"][-150:]
            session = live["generation"]
            use_adviser = live.get('adviser_enabled', False)
            index = self.cue_index(p) if live.get('reflex_enabled', False) else None
            current = next((s for s in package['scenes'] if s['id']==live['current_scene_id']),None)
            context = {'current_concept_id':current['concept_id'] if current else None,
                       'recent_utterances':[r['text'] for r in live['transcript'][-4:-1]
                                            if self.clock()-r['at'] <= 8]}
        recommendation = index.match(utterance, preferred_kind(utterance)) if index else recommend(package, utterance)
        if self.research:
            self.research.observe(pid,utterance,recommendation,generation=session,seq=seq)
        if self.live_assessor and use_adviser and (not index or (
                not recommendation.get('reflex_ready') and recommendation.get('supported_concepts'))):
            try:
                advice_package = {**package,'_live_context':context} if index else package
                if expires_at is None:
                    advice = self.live_assessor(advice_package, utterance)
                else:
                    advice = self.deadline_adviser.ask(self.live_assessor,advice_package,utterance,
                        min(1.2,max(0,expires_at-self.clock()-.02)))
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
            if expires_at is not None and self.clock() > expires_at:
                clear_candidate(live)
                live['recommendation'] = {**recommendation, 'expired': True}
                live['decision'] = {'action':'HOLD', 'reason':'Audio expired before matching completed; retaining the stage.'}
                return p
            candidate = recommendation["scene_id"]
            live["candidate_count"] = live["candidate_count"] + 1 if candidate == live["candidate_id"] else 1
            live["candidate_id"] = candidate
            live["recommendation"] = recommendation
            current_scene = next((s for s in package['scenes'] if s['id'] == live['current_scene_id']), None)
            candidate_scene = next((s for s in package['scenes'] if s['id'] == candidate), None)
            if current_scene and (current_scene['concept_id'] in recommendation.get('supported_concepts', [])
                                  or (candidate_scene and candidate_scene['concept_id'] == current_scene['concept_id'])):
                live['last_support'] = self.clock()
            reason = ("Several prepared ideas could fit; retaining the stage until the meaning is clearer."
                      if recommendation.get('supported_concepts') else "No supported prepared visual for this utterance; retaining the stage.")
            if live["locked"]:
                reason = "Stage held by presenter; recommendation stays backstage."
            elif (current_scene and attention_targets(current_scene) and not live.get('research_scene')
                  and (not candidate or candidate == live['current_scene_id'])):
                comparison = chart_comparison(current_scene, utterance)
                if comparison and self.clock() - live.get('last_focus_change',0) >= self.dwell_s:
                    live['attention'] = {'scene_id':current_scene['id'], 'annotation_id':None,
                        'target_ids':comparison['target_ids'], 'comparison':comparison}
                    live['last_focus_change'] = self.clock()
                    live['decision'] = {'action':'COMPARE','scene_id':current_scene['id'],
                        'reason':'Comparing the requested categories using approved data values.'}
                    return p
                target = focus_target(current_scene, utterance)
                previous = (live.get('attention') or {}).get('annotation_id')
                if target and target != previous and self.clock() - live.get('last_focus_change', 0) >= self.dwell_s:
                    self.focus(live, current_scene, target, 'Prepared spoken cue directed attention within the same visual.')
                    return p
                if candidate == live['current_scene_id']:
                    live['decision'] = {'action':'HOLD', 'reason':'Retaining the current illustration and attention.'}
                    return p
            if not live['locked'] and candidate and recommendation["score"] >= .45:
                if self.clock() - live["last_change"] < self.dwell_s:
                    reason = "Current visual is still inside its minimum display time."
                elif recommendation["confirmed"] or (not index and (
                        recommendation["score"] >= .88 or live["candidate_count"] >= 2)):
                    self.show(live, candidate, "Prepared visual matched the spoken explanation.")
                    return p
                else:
                    reason = "Possible match prepared backstage; waiting for stronger support."
            release_after = STYLES[live.get('style','persist')]['release_after_s']
            if (not live['locked'] and release_after is not None and (live['current_scene_id'] or live.get('research_scene'))
                    and self.clock() - max(live.get('last_support', 0), live['last_change']) >= release_after):
                self.release(live, 'Speech moved on from the visual; attention returns to the speaker.')
                return p
            live["decision"] = {"action": "WARM" if candidate else "HOLD", "reason": reason}
        return self.store.read(pid)


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
    kind = preferred_kind(utterance)
    scene = choose_scene(package,concept['id'],kind)
    return {"scene_id": scene["id"], "score": round(score, 3), "supported_concepts":supported, "confirmed": False, "method": "prepared_cues"}


def preferred_kind(utterance):
    # Talking about the amount/quality of evidence is not asking to see a quote.
    # Require a source-display request before selecting the quotation view.
    if re.search(r'\b(?:show|display|read|quote|cite|open|see)\b.{0,45}\b(?:evidence|source|citation|quote|quotation)\b|\b(?:source|citation|quote|quotation)\s+please\b',utterance,re.I):
        return 'evidence'
    words = tokens(utterance)
    for kind, cues in [('comparison', {'compare','versus','difference'}),
                       ('chart', {'chart','data','measured','trend'})]:
        if words & cues:
            return kind
    return None


def jev_adviser(package, utterance):
    choices = {c['id']: c['title'] + ': ' + c['summary'] for c in package['concepts']}
    choices['hold'] = 'The utterance is off-topic or does not clearly match a prepared idea.'
    hints = {'definition':'Explain or define an idea.', 'flow':'Trace a process or sequence.',
             'comparison':'Compare options side by side.', 'chart':'Show numeric patterns or measurements.',
             'metric':'Emphasize one number.', 'evidence':'Explicitly request or quote source evidence.',
             'image':'Show a supplied image that supports this idea.'}
    questions = {
        'concept': {'type':'choice', 'instructions':'Which prepared IDEA is the speaker explaining? Choose hold for off-topic or ambiguous speech. Ignore which visual form is available.', 'criteria':choices},
        'representation': {'type':'choice', 'instructions':'Which visual form would support the way the speaker is explaining the idea? Evidence is for explicit source requests, not every factual claim.',
                           'criteria': {k:v for k,v in hints.items() if any(s['kind'] == k for s in package['scenes'])}}}
    state = {"utterance": utterance, "prepared_concepts": package["concepts"]}
    if '_live_context' in package:
        state.update(recent_past=package['_live_context'], context_rule=
            'Classify the latest utterance in light of recent past. Do not move to a new idea solely because earlier context mentioned it.')
    response = asyncio.run(JevBackend(timeout_s=1.2).ask(state, questions))
    answer, representation = response.answers['concept'], response.answers['representation']
    scenes = [s for s in package['scenes'] if s['concept_id'] == answer.value]
    # Concept confidence must not be diluted across several equally valid
    # visual alternatives. Representation selection stays inside that idea.
    scene = choose_scene(package,answer.value,preferred_kind(utterance),
                         representation.value if representation.confidence >= .55 else None)
    return {"scene_id": scene['id'] if scene else None, "confidence": answer.confidence,
            'concept_id':answer.value, 'representation':representation.value,
            'representation_confidence':representation.confidence,
            "model": response.model, "latency_ms": response.latency_ms}
