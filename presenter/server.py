"""Loopback-only local studio. No external hosting or new provider keys required."""
import argparse
import base64
import binascii
import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
import re
from pathlib import Path
import shutil
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from jev_credentials_v10 import load_jev_env
from .engine import Conflict, Store, Studio, jev_adviser
from .materials import ingest
from .live_audio import LiveAudio, SubprocessRecognizer
from .research import LiveResearch
from .research_bridge import ResearchBridge

STATIC = Path(__file__).parent / "web"

EXAMPLE = {"title": "A better cooling loop", "audience": "First-year engineering students",
           "brief": "Explain the cooling loop and the measured trade-off between flow and electrical power in six minutes. Treat these as illustrative lab measurements, not external research.",
           "sources": [{"name": "Cooling loop.md", "text": """# Why a cooling loop?

A closed cooling loop moves heat away from a component. A pump circulates liquid; the liquid absorbs heat at the component, then releases it through a radiator. These notes describe an illustrative teaching apparatus, not a validated commercial product.

## Following the liquid

1. The reservoir supplies liquid to the pump.
2. The pump pushes liquid through the heated component.
3. The radiator releases absorbed heat to the surrounding air.
4. The cooled liquid returns to the reservoir.

## Choosing a setting

The supplied measurements.csv file records three illustrative operating settings. Higher settings deliver more flow and consume more electrical power. The measurements alone do not establish cooling performance: coolant temperature and heat removal were not recorded. Do not claim the high setting is the most efficient.

## The takeaway

The pump maintains circulation while the radiator transfers heat to the air. Select a setting using the actual cooling requirement and measured power, rather than maximizing flow by default.
"""}, {"name": "measurements.csv", "text": "Setting,Flow_L_min,Electrical_power_W\nLow,12,90\nMedium,18,145\nHigh,24,230\n"}]}


def public_project(project):
    # Documents expose extracted text, and supplied raster assets retain their
    # bytes locally. Stage responses include only the approved scene assets.
    return project


def make_server(store, host="127.0.0.1", port=8765, *, planner=None, use_jev=True, dwell_s=2.5, audio_decoder=None, research_backend=None, live_research=False, research_bridge=False):
    writer_lock = (store.root / '.server.lock').open('a')
    try:
        fcntl.flock(writer_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        writer_lock.close()
        raise RuntimeError('Another studio server is using this data directory.') from None
    token_path = store.root / '.operator-key'
    try:
        fd=os.open(token_path,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as file:file.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    access_token=token_path.read_text().strip()
    if len(access_token) < 32:
        writer_lock.close()
        raise RuntimeError('The local operator key is invalid.')

    def stage_token(pid):
        return hmac.new(access_token.encode(),('projector:'+pid).encode(),hashlib.sha256).hexdigest()

    def project_view(p):
        return {**public_project(p),'stage_access':stage_token(p['id'])}

    studio = Studio(store, planner=planner, live_assessor=jev_adviser if use_jev else None, dwell_s=dwell_s)
    audio = LiveAudio(studio, audio_decoder) if audio_decoder else None
    if research_bridge:research_backend=ResearchBridge()
    research = LiveResearch(studio,research_backend) if live_research or research_backend is not None else None
    studio.research = research

    class Handler(BaseHTTPRequestHandler):
        server_version = "LivePresenter/1"

        def log_message(self, fmt, *args):
            # Never log source content, transcripts, provider prompts or keys.
            pass

        def reply(self, status, value, mime="application/json"):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if mime == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed_origin(self):
            allowed = {"127.0.0.1:" + str(self.server.server_port), "localhost:" + str(self.server.server_port)}
            if self.headers.get("Host") not in allowed:
                raise PermissionError("This studio accepts loopback requests only.")
            origin = self.headers.get("Origin")
            if origin and (urlparse(origin).netloc not in allowed or urlparse(origin).scheme != "http"):
                raise PermissionError("Cross-origin requests are not allowed.")

        def do_GET(self):
            try:
                self.allowed_origin()
                path = urlparse(self.path).path
                if path.startswith('/api/'):
                    credential=self.headers.get('X-Presenter-Key','')
                    parts=path.strip('/').split('/')
                    projector=(len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='stage'
                               and hmac.compare_digest(credential,stage_token(parts[2])))
                    if not projector and not hmac.compare_digest(credential,access_token):
                        raise PermissionError('Open the studio URL printed by make studio to access your workspace.')
                if path == "/api/status":
                    return self.reply(200, {"conversation_available": bool(shutil.which(studio.planner.command)) if hasattr(studio.planner, "command") else True,
                                            "live_adviser": "jev" if use_jev else "prepared_cues", 'local_audio': audio is not None,
                                            'live_research':research is not None,
                                            'research_mode':'connected_agent' if research and isinstance(research.backend,ResearchBridge) else 'public_sources',
                                            "formats": ["TXT", "MD", "CSV", "TSV", "PDF", "DOCX", "PNG", "JPEG"]})
                if path == "/api/example":
                    return self.reply(200, EXAMPLE)
                if path=='/api/research/job':
                    if not research or not isinstance(research.backend,ResearchBridge):raise KeyError('No connected research agent mode.')
                    return self.reply(200,{'job':research.backend.snapshot()})
                if path == "/api/projects":
                    return self.reply(200, {"projects": store.listing()})
                parts = path.strip("/").split("/")
                if len(parts) in {3, 4} and parts[:2] == ["api", "projects"]:
                    p = store.read(parts[2])
                    if len(parts) == 4 and parts[3] == 'audio':
                        return self.reply(200, audio.snapshot(p['id']) if audio else {'status':'disabled'})
                    if len(parts) == 4 and parts[3] == "stage":
                        after = parse_qs(urlparse(self.path).query).get('after', [None])[0]
                        if after is not None:
                            if not re.fullmatch(r'-?\d{1,18}', after):
                                return self.reply(400, {'error':'Invalid stage version.'})
                            changed = store.condition(p['id'])
                            with changed:
                                changed.wait_for(lambda: store.read(p['id']).get('state_version',0) > int(after), timeout=15)
                                p = store.read(p['id'])
                        try:
                            package = studio.package(p)
                        except Conflict:
                            package = None
                        scene = next((s for s in package["scenes"] if s["id"] == p["live"]["current_scene_id"]), None) if package and p['live']['active'] else None
                        if package and p['live']['active'] and p['live'].get('research_enabled') and p['live'].get('research_scene'):
                            scene=p['live']['research_scene']
                        return self.reply(200, {"title": package["title"] if package else p["title"], "scene": scene,
                                                'reflex_enabled':p['live'].get('reflex_enabled',False),
                                                "state_version": p.get('state_version',0),
                                                "package_hash": p["approval"]["package_hash"] if package else None,
                                                "scenes": package["scenes"] if package else []})
                    if len(parts) == 3:
                        return self.reply(200, project_view(p))
                    raise KeyError("Unknown route.")
                file = "stage.html" if path.startswith("/stage/") else "index.html" if path == "/" else path.lstrip("/")
                # Fixed allowlist prevents exposing source files or saved project data.
                if file not in {"index.html", "stage.html", "studio.js", "visuals.js", "stage.js", "style.css", 'microphone.js', 'pcm-worklet.js'}:
                    raise KeyError("Unknown page.")
                target = STATIC / file
                return self.reply(200, target.read_bytes(), mimetypes.guess_type(file)[0] or "text/plain")
            except (KeyError, FileNotFoundError):
                self.reply(404, {"error": "Presentation or page not found."})
            except PermissionError as e:
                self.reply(403, {"error": str(e)})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            try:
                self.allowed_origin()
                if not hmac.compare_digest(self.headers.get('X-Presenter-Key',''),access_token):
                    raise PermissionError('Operator access is required for this action.')
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Send application/json.")
                size = int(self.headers.get("Content-Length", 0))
                if size <= 0 or size > 6_000_000:
                    raise ValueError("Request must contain JSON and be under 6 MB.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object.")
                path = urlparse(self.path).path
                if path == "/api/projects":
                    sources = []
                    for s in body.get("sources", []):
                        data = base64.b64decode(s["base64"], validate=True) if "base64" in s else s.get("text", "").encode()
                        sources.append(ingest(s.get("name", "Notes.md"), data, s.get('description','')))
                    p = store.create(title=str(body.get("title", "")), brief=str(body.get("brief", "")),
                                     audience=str(body.get("audience", "")), sources=sources, provider=body.get("provider", "copilot"))
                    return self.reply(201, project_view(studio.prepare(p["id"])))
                if path=='/api/research/result':
                    if not research or not isinstance(research.backend,ResearchBridge):raise KeyError('No connected research agent mode.')
                    research.backend.supply(str(body.get('job_id','')),body.get('sources'),body.get('status','ready'))
                    return self.reply(200,{'accepted':True})
                parts = path.strip("/").split("/")
                if len(parts) != 4 or parts[:2] != ["api", "projects"]:
                    raise KeyError("Unknown route.")
                pid, action = parts[2:]
                if action == "chat":
                    result = studio.prepare(pid, str(body.get("message", "")))
                elif action == "context":
                    result = studio.context(pid, title=str(body.get("title", "")), brief=str(body.get("brief", "")),
                                            audience=str(body.get("audience", "")), provider=body.get("provider", "copilot"))
                elif action == 'sources':
                    sources=[]
                    for s in body.get('sources', []):
                        data=base64.b64decode(s['base64'],validate=True) if 'base64' in s else s.get('text','').encode()
                        sources.append(ingest(s.get('name','Notes.md'),data,s.get('description','')))
                    result=studio.add_sources(pid,sources)
                elif action == "approve":
                    result = studio.approve(pid, body.get("revision"), body.get("reviewed"))
                elif action == 'default-scene':
                    result = studio.default_scene(pid,body.get('scene_id'))
                elif action == "control":
                    result = studio.control(pid, body.get("action"), body.get("scene_id"), body.get('enabled'))
                    if research and body.get('action')!='start':research.invalidate(pid)
                    if audio:
                        audio.invalidate(pid)
                        result = store.read(pid)
                elif action=='research':
                    if not research:raise Conflict('Live research is disabled in this studio.')
                    current=store.read(pid)['live']
                    if not current['active'] or not current.get('research_enabled') or current['locked']:
                        raise Conflict('Start following, enable live research and release Hold before researching a new topic.')
                    query=str(body.get('query','')).strip()
                    if not query:raise ValueError('Describe the related topic to research.')
                    research.observe(pid,query,{},force=True)
                    result=store.read(pid)
                elif action == 'audio':
                    if not audio:
                        raise Conflict('Local audio is disabled. Start the studio with --asr-python.')
                    if body.get('action') == 'start':
                        result = audio.start(pid,body.get('generation'))
                    elif body.get('action') == 'chunk':
                        result = audio.submit(pid,body)
                    elif body.get('action') == 'stop':
                        result = audio.stop(pid,body.get('stream_id'))
                    else:
                        raise ValueError('Unknown microphone action.')
                    return self.reply(200,result)
                elif action == "transcript":
                    if isinstance(body.get("seq"), bool) or not isinstance(body.get("seq"), int):
                        raise ValueError("Transcript sequence must be an integer.")
                    result = studio.transcript(pid, str(body.get("text", "")), body["seq"],
                                               final=body.get("final") is True, generation=body.get("generation"))
                else:
                    raise KeyError("Unknown route.")
                return self.reply(200, project_view(result))
            except KeyError:
                self.reply(404, {"error": "Presentation, required field or route not found."})
            except PermissionError as e:
                self.reply(403, {"error": str(e)})
            except Conflict as e:
                self.reply(409, {"error": str(e)})
            except (ValueError, TypeError, binascii.Error) as e:
                self.reply(400, {"error": str(e)[:500]})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.reply(500, {"error": "The local studio could not complete that request. Your saved presentation is retained."})

    class LocalServer(ThreadingHTTPServer):
        def server_close(self):
            if research:research.close()
            if audio:
                audio.close()
            super().server_close()
            if not writer_lock.closed:writer_lock.close()
    try:
        server = LocalServer((host, port), Handler)
    except Exception:
        if research:research.close()
        if audio:
            audio.close()
        writer_lock.close()
        raise
    server.studio = studio
    server.access_token = access_token
    server.stage_token = stage_token
    server.audio = audio
    server.research = research
    server.daemon_threads = True
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", type=Path, default=Path("artifacts/studio"))
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--env-file")
    ap.add_argument('--asr-python', type=Path, help='Enable local PCM recognition with this optional ASR Python environment')
    ap.add_argument('--research',action='store_true',help='Enable the optional background live source-procurement worker (uses existing Jev credentials).')
    ap.add_argument('--research-bridge',action='store_true',help='Connect an active research agent through the authenticated research job/result API.')
    args = ap.parse_args()
    load_jev_env(args.env_file)
    enabled = not args.no_jev and bool(os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY"))
    server = make_server(Store(args.data_dir), port=args.port, use_jev=enabled,
                         audio_decoder=SubprocessRecognizer(args.asr_python) if args.asr_python else None,live_research=args.research,research_bridge=args.research_bridge)
    print(f"Live Presenter studio: http://127.0.0.1:{server.server_port}/#access={server.access_token}", flush=True)
    print("Sources, conversations and approval packages stay in " + str(args.data_dir.resolve()), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
