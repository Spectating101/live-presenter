"""Small real-network HTTP procurement probe; outputs stay in ignored artifacts/."""
import argparse
import html
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

from jev_credentials_v10 import load_jev_env
from presenter.engine import Store
from presenter.recording import file_hash, save
from presenter.server import make_server


NOTES = ('A pump circulates liquid through a hot component and a radiator. '
         'The radiator transfers heat to surrounding air. These notes describe a pumped cooling loop.')
QUERY = 'What about heat pipes and phase change instead of this pumped cooling loop?'
CODE = ('engine.py', 'research.py', 'research_sources.py', 'research_bridge.py', 'server.py')


def write_report(result, destination):
    """Static inspection artifact, not a measurement of the browser renderer."""
    scene = result['stage_scene']
    origin = scene.get('web_source', {})
    esc = lambda value: html.escape(str(value), quote=True)
    picture = ''
    if scene['kind'] == 'image':
        picture = f'<img alt="{esc(scene["asset"]["alt"])}" src="{esc(scene["asset"]["data_url"])}">'
    refs = ''.join(f'<blockquote>{esc(ref["quote"])}<footer>{esc(ref["source_name"])}</footer></blockquote>'
                   for ref in scene['source_refs'])
    credits = ''
    if origin:
        credits = f'<p><a href="{esc(origin["url"])}">Retrieved source</a> · not presenter-reviewed</p>'
        if origin.get('image_url'):
            credits += f'<p><a href="{esc(origin["image_url"])}">{esc(origin.get("artist", ""))} · {esc(origin.get("image_license", ""))}</a></p>'
    destination.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Live research pilot</title>
<style>body{{font:18px/1.5 system-ui;max-width:1100px;margin:3rem auto;padding:0 1.5rem;color:#173a30;background:#f5f6f0}}
section{{background:white;padding:1.5rem;margin:1rem 0;border:1px solid #dce3dc;border-radius:12px}}
img{{display:block;max-width:100%;max-height:520px;margin:auto;object-fit:contain}}blockquote{{border-left:3px solid #2d6657;padding-left:1rem}}
footer,small{{color:#526359}}a{{color:#235f80}}</style>
<h1>Unprepared material: live research pilot</h1>
<p>Actual HTTP/source retrieval; static report. Browser paint and physical audio were not measured.</p>
<section><h2>Prepared notes</h2><p>{esc(result['prepared_material'])}</p>
<h2>New spoken topic, submitted as text</h2><p>{esc(result['unprepared_utterance'])}</p></section>
<section><h2>Observed result: {esc(result['status'])}</h2>
<p>Transcript HTTP return: {result['transcript_http_return_s']*1000:.2f} ms · research: {result['research_elapsed_s']:.2f} s</p>
<h3>{esc(scene['title'])}</h3>{picture}{refs}{credits}</section>
<p>Prepared approval unchanged: {esc(result['approval_unchanged'])}. Zero stage dwell in this probe.
Retrieval may fail or arrive too late; this single development observation is not a reliability estimate.</p>
<small>See result.json for provenance and code fingerprints; LIVE_RESEARCH.md for all retained outcomes.</small></html>''', encoding='utf-8')


def run(folder):
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (folder / 'result.json').exists():
        raise ValueError('Preserving the recorded result; choose a new output directory.')
    load_jev_env()
    server = make_server(Store(folder / 'studio'), port=0, use_jev=False, live_research=True, dwell_s=0)
    service = threading.Thread(target=server.serve_forever, daemon=True)
    service.start()
    pid = None

    def call(path, body=None, stage=False):
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Presenter-Key': server.stage_token(pid) if stage else server.access_token,
                     'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.loads(response.read())

    try:
        project = call('/api/projects', {'title':'A pumped cooling loop',
            'brief':'Explain cooling, liquid circulation and the radiator.', 'audience':'Engineering students',
            'provider':'outline', 'sources':[{'name':'Cooling notes.md','text':NOTES}]})
        pid = project['id']
        url = '/api/projects/' + pid
        deadline = time.monotonic() + 5
        while project['job']['status'] != 'ready':
            if time.monotonic() > deadline:
                raise TimeoutError('Local source preparation did not finish.')
            time.sleep(.02)
            project = call(url)
        project = call(url + '/approve', {'revision':project['revision'], 'reviewed':True})
        approval = project['approval']['package_hash']
        project = call(url + '/control', {'action':'start'})
        project = call(url + '/control', {'action':'research', 'enabled':True})
        begun = time.monotonic()
        project = call(url + '/transcript', {'text':QUERY, 'seq':0, 'final':True,
                                            'generation':project['live']['generation']})
        immediate = time.monotonic() - begun
        while project['live']['research'].get('status') not in {'ready','error','no_match','no_results','limit'}:
            if time.monotonic() - begun > 30:
                raise TimeoutError('The coordinator did not settle within the pilot budget.')
            time.sleep(.05)
            project = call(url)
        elapsed = time.monotonic() - begun
        stage = call(url + '/stage', stage=True)
        assert project['approval']['package_hash'] == approval and len(project['sources']) == 1
        result = {'schema':'live_presenter.live_research_demo.v1', 'mode':'builtin_public_sources',
            'prepared_material':NOTES, 'unprepared_utterance':QUERY,
            'prepared_material_sha256':project['sources'][0]['sha256'], 'package_hash':approval,
            'transcript_http_return_s':immediate, 'research_elapsed_s':elapsed,
            'status':project['live']['research']['status'], 'research':project['live']['research'],
            'stage_scene':stage['scene'], 'research_history':project.get('research_history',[]),
            'approval_unchanged':True, 'source_material_count':1, 'browser_used':False,
            'physical_audio_used':False, 'stage_dwell_s':0, 'independent_review':False,
            'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'code_fingerprints':{name:file_hash(Path('presenter') / name) for name in CODE}}
        save(folder / 'result.json', result)
        write_report(result, folder / 'index.html')
        return {'status':result['status'], 'transcript_return_s':immediate, 'research_elapsed_s':elapsed,
                'retrieved':bool(stage['scene'].get('web_source')), 'report':str(folder / 'index.html')}
    finally:
        server.shutdown()
        server.server_close()
        service.join(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True, help='New ignored artifact directory')
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir)), flush=True)


if __name__ == '__main__':
    main()
