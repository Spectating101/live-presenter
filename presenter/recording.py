"""Reproducible recorded-talk development experiments, separate from the live UI.

Media stays in ignored local storage. Audio recognition consumes one bounded
chunk at a time, without captions, reference frames or future audio as inputs.
"""
import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import html as html_module
from html.parser import HTMLParser
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from urllib.parse import urlparse
import wave

from research_evidence_v10 import json_hash
from jev_credentials_v10 import load_jev_env
from .engine import Store, Studio, jev_adviser
from .materials import ingest


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as file:
        file.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    temp.replace(path)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def recording_store(path):
    store = Store(path)
    with (store.root / '.server.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another studio or replay process is using this workspace.') from None
        yield store


def download(url, path, limit=500_000_000):
    path = Path(path)
    partial = path.with_suffix(path.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'LivePresenter-Research/1.0'})
    count = 0
    with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as file:
        while block := response.read(1024 * 1024):
            count += len(block)
            if count > limit:
                raise ValueError('Download exceeds the local experiment limit.')
            file.write(block)
    partial.replace(path)


class TedMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.capture = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)


def acquire_ted(url, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read(5_000_001)
    if len(html) > 5_000_000:
        raise ValueError('Source page is too large.')
    parser = TedMetadata()
    parser.feed(html.decode())
    raw = json.loads(''.join(parser.parts))['props']['pageProps']
    video = raw['videoData']['videoPlayerData']
    media = min(video['resources']['h264'], key=lambda v: v['bitrate'])['file']
    original = folder / 'original.mp4'
    if original.exists():
        manifest = json.loads((folder / 'source.json').read_text())
        if manifest['media_url'] != media or manifest['video_sha256'] != file_hash(original):
            raise ValueError('Existing recording does not match this source. Use a fresh experiment folder.')
    else:
        download(media, original)
    for arguments, target in [(['-vn', '-ac', '1', '-ar', '16000'], 'audio.wav'),
                              (['-an', '-c:v', 'copy'], 'video.mp4')]:
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(original), *arguments, str(folder / target)], check=True)
    paragraphs = raw['transcriptData']['translation']['paragraphs']
    prep = ('# ' + video['speaker'] + ': ' + video['title'] + '\n\n'
            'Historical talk claims, not current statistics. Source: ' + video['canonical'] + '\n\n'
            + '\n\n'.join(' '.join(c['text'].replace('\n', ' ') for c in p['cues']) for p in paragraphs))
    (folder / 'preparation.md').write_text(prep)
    save(folder / 'official_reference.json', [
        {'start': c['time'] / 1000, 'text': c['text']} for p in paragraphs for c in p['cues']])
    manifest = {'schema': 'live_presenter.recording_source.v1', 'title': video['title'],
                'speaker': video['speaker'], 'page_url': video['canonical'], 'media_url': media,
                'video_sha256': file_hash(original), 'audio_sha256': file_hash(folder / 'audio.wav'),
                'preparation_sha256': file_hash(folder / 'preparation.md'),
                'preparation_condition': 'same-talk untimed transcript supplied in advance (upper-bound preparation)',
                'reference_only': ['original video frames', 'official caption timing'],
                'distribution': 'Local evaluation only. Media and transcript are not committed or republished.',
                'usage_policy': 'https://www.ted.com/about/our-organization/our-policies-terms/ted-talks-usage-policy'}
    save(folder / 'source.json', manifest)
    return manifest


def audio_chunks(path, chunk_s):
    if not math.isfinite(chunk_s) or not 1 <= chunk_s <= 30:
        raise ValueError('Use an audio chunk duration between 1 and 30 seconds.')
    with wave.open(str(path), 'rb') as file:
        if (file.getnchannels(), file.getsampwidth(), file.getframerate()) != (1, 2, 16000):
            raise ValueError('Recognition input must be mono 16-bit 16 kHz PCM WAV.')
        count, cursor = round(chunk_s * 16000), 0
        while data := file.readframes(count):
            end = cursor + len(data) // 2
            yield cursor / 16000, end / 16000, data
            cursor = end


def transcribe_audio(audio, output, *, model_name='tiny.en', chunk_s=6, threads=4):
    # Optional local dependency; importing the studio itself never imports Torch.
    import numpy as np
    import torch
    import whisper
    torch.set_num_threads(threads)
    ready = time.perf_counter()
    model = whisper.load_model(model_name, device='cpu')
    model.transcribe(np.zeros(16000, dtype=np.float32), language='en', fp16=False,
                     temperature=0, condition_on_previous_text=False)
    result = {'schema': 'live_presenter.chunk_asr.v1', 'audio_sha256': file_hash(audio),
              'model': model_name, 'recognizer': 'openai-whisper ' + importlib.metadata.version('openai-whisper'),
              'device': 'cpu', 'threads': threads, 'chunk_s': chunk_s,
              'model_ready_s': time.perf_counter() - ready, 'complete': False,
              'future_audio_visible': False, 'official_captions_visible': False, 'chunks': []}
    for start, end, data in audio_chunks(audio, chunk_s):
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768
        begun = time.perf_counter()
        recognized = model.transcribe(samples, language='en', fp16=False, temperature=0,
                                     condition_on_previous_text=False, verbose=None)
        row = {'start': start, 'end': end, 'asr_s': time.perf_counter() - begun,
               'text': recognized['text'].strip()}
        result['chunks'].append(row)
        save(output, result)
        print(f'Audio {end:.1f}s · recognition {row["asr_s"]:.2f}s · {row["text"][:100]}', flush=True)
    result['complete'] = True
    save(output, result)
    return result


def prepare_recording(folder, provider='copilot'):
    with recording_store(Path(folder) / 'studio') as store:
        return _prepare_recording(Path(folder), provider, store)


def _prepare_recording(folder, provider, store):
    folder = Path(folder)
    folder.chmod(0o700)
    source = json.loads((folder / 'source.json').read_text())
    if source['preparation_sha256'] != file_hash(folder / 'preparation.md'):
        raise ValueError('Preparation material changed after acquisition.')
    studio = Studio(store)
    project = store.create(title=source['title'], audience='General adult audience', provider=provider,
        brief=('Prepare this historical talk for an audio-only recorded rehearsal. Preserve the speaker\'s '
               'argument and historic dates; do not treat old statistics as current. Provide useful spoken aliases. '
               'Cover the main ideas in order, including numeric comparisons and the concluding explanation. '
               'Do not invent data or reconstruct a dataset from prose. The original video is reference-only.'),
        sources=[ingest('Supplied talk material.md', (folder / 'preparation.md').read_bytes())])
    p = studio.prepare(project['id'], background=False)
    save(folder / 'project.json', {'project_id': p['id'], 'job': p['job']})
    return p


class ReplayClock:
    """Advance an audio clock without sleeping, retaining measured processing time."""
    def __init__(self):
        self.base = 0
        self.begun = time.perf_counter()

    def set(self, value):
        self.base, self.begun = value, time.perf_counter()

    def __call__(self):
        return self.base + time.perf_counter() - self.begun


def validate_chunks(asr):
    if asr.get('complete') is not True or asr.get('schema') != 'live_presenter.chunk_asr.v1':
        raise ValueError('Use a completed bounded-chunk ASR recording.')
    previous = 0
    for row in asr['chunks']:
        if (any(isinstance(row[k], bool) or not isinstance(row[k], (int, float))
                or not math.isfinite(row[k]) for k in ('start','end','asr_s'))
                or row['start'] != previous or row['end'] <= row['start'] or row['asr_s'] < 0
                or not isinstance(row['text'], str)):
            raise ValueError('ASR chunks must be finite, contiguous and in audio order.')
        previous = row['end']
    if not asr['chunks'] or asr.get('future_audio_visible') is not False or asr.get('official_captions_visible') is not False:
        raise ValueError('Recognition must exclude future audio and official captions.')


def replay(folder, asr_path, *, mode='local', output=None):
    if mode not in {'local','jev'}:
        raise ValueError('Unknown replay mode.')
    with recording_store(Path(folder) / ('replay-' + mode)) as store:
        return _replay(folder, asr_path, mode=mode, output=output, store=store)


def _replay(folder, asr_path, *, mode, output, store):
    folder, asr_path = Path(folder), Path(asr_path)
    controller_hash = file_hash(Path(__file__).with_name('engine.py'))
    runner_hash = file_hash(__file__)
    asr = json.loads(asr_path.read_text())
    validate_chunks(asr)
    if asr['audio_sha256'] != file_hash(folder / 'audio.wav'):
        raise ValueError('ASR does not belong to this recording.')
    source = json.loads((folder / 'source.json').read_text())
    if (source['audio_sha256'] != asr['audio_sha256']
            or source['preparation_sha256'] != file_hash(folder / 'preparation.md')):
        raise ValueError('Source acquisition or preparation binding changed.')
    pid = json.loads((folder / 'project.json').read_text())['project_id']
    original = Store(folder / 'studio').read(pid)
    Studio.package(original)  # Never silently approve the generated package.
    if len(original['sources']) != 1 or original['sources'][0]['sha256'] != source['preparation_sha256']:
        raise ValueError('The approved package belongs to different preparation material.')
    # Evaluation copies the approved project, never modifies an active workspace.
    store.save(copy.deepcopy(original))
    clock = ReplayClock()
    studio = Studio(store, live_assessor=jev_adviser if mode == 'jev' else None, clock=clock)
    p = studio.control(pid, 'start')
    if mode == 'jev':
        if not load_jev_env():
            raise ValueError('No existing Jev credential is available. Use local mode or configure JEV_ENV_FILE.')
        p = studio.control(pid, 'adviser', enabled=True)
    clock.set(0)
    events = [{'at': 0, 'scene_id': p['live']['current_scene_id'], 'reason': 'Approved opening visual.'}]
    rows, asr_available, stage_available = [], 0, 0
    for seq, chunk in enumerate(asr['chunks']):
        # ASR and stage are separate serial workers. No complete chunk is
        # available until its audio end, then measured recognition finishes.
        asr_started = max(chunk['end'], asr_available)
        asr_available = asr_started + chunk['asr_s']
        started = max(asr_available, stage_available)
        clock.set(started)
        before = p['live']['current_scene_id']
        if chunk['text'].strip():
            p = studio.transcript(pid, chunk['text'], seq, generation=p['live']['generation'])
        stage_available = clock()
        row = {**chunk, 'seq': seq, 'asr_available_at': asr_available, 'decision_started_at': started,
               'decision_completed_at': stage_available, 'audio_to_decision_s': stage_available - chunk['end'],
               'scene_id': p['live']['current_scene_id'], 'decision': copy.deepcopy(p['live']['decision']),
               'recommendation': copy.deepcopy(p['live'].get('recommendation')) if chunk['text'].strip() else None}
        rows.append(row)
        if p['live']['current_scene_id'] != before:
            events.append({'at': stage_available, 'scene_id': p['live']['current_scene_id'], 'reason': p['live']['decision']['reason']})
        print(f'Replay {chunk["end"]:.0f}s → {row["decision"]["action"]} · delay {row["audio_to_decision_s"]:.2f}s', flush=True)
    result = {'schema': 'live_presenter.recorded_replay.v1', 'mode': mode, 'complete': True,
              'source': source,
              'controller_sha256': controller_hash,
              'runner_sha256': runner_hash,
              'dwell_s': studio.dwell_s,
              'asr': {k:v for k,v in asr.items() if k != 'chunks'}, 'asr_sha256': file_hash(asr_path),
              'package_hash': original['approval']['package_hash'], 'package': original['approval']['package'],
              'duration_s': asr['chunks'][-1]['end'], 'rows': rows, 'events': events,
              'limitations': ['Accelerated serial-worker simulation with measured ASR and adviser time; no browser rendering or device latency.',
                              'Same-talk transcript supplied in advance: an upper-bound preparation condition.',
                              'Original video is a reference, not the only valid visual design or a gold editorial trace.',
                              'One development talk; no held-out accuracy or audience-usefulness claim.']}
    save(output or folder / ('result-' + mode + '.json'), result)
    return result


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))] if ordered else None


def score_replay(result, reference):
    if json_hash(result['package']) != result['package_hash']:
        raise ValueError('Prepared package content no longer matches its recorded hash.')
    if reference['package_hash'] != result['package_hash']:
        raise ValueError('Reference was written for a different prepared package.')
    scenes = {s['id']: s for s in result['package']['scenes']}
    events = result['events']
    duration = result['duration_s']
    if (any(e['scene_id'] not in scenes for e in events)
            or any(not math.isfinite(e['at']) or e['at'] < 0 for e in events)
            or any(a['at'] > b['at'] for a,b in zip(events, events[1:]))):
        raise ValueError('Stage trace contains an unknown scene or invalid timing.')
    if any(row['scene_id'] not in scenes for row in result['rows']):
        raise ValueError('A decision names an unknown prepared scene.')
    chapters, total, correct = [], 0, 0
    exclusion = reference['boundary_exclusion_s']
    for span in reference['spans']:
        start, end = span['start'] + exclusion, min(duration, span['end'] - exclusion)
        if end <= start:
            continue
        aligned = 0
        first = None
        for i, event in enumerate(events):
            stop = events[i + 1]['at'] if i + 1 < len(events) else duration
            if scenes[event['scene_id']]['concept_id'] not in span['acceptable_concept_ids']:
                continue
            aligned += max(0, min(end, stop) - max(start, event['at']))
            if min(span['end'], stop) > max(span['start'], event['at']):
                first = max(span['start'], event['at']) if first is None else first
        total += end - start
        correct += aligned
        chapters.append({'label': span['label'], 'scored_s': end - start, 'aligned_s': aligned,
                         'fraction': aligned / (end - start),
                         'first_matching_visual_lag_s': first - span['start'] if first is not None else None,
                         'original_visual': span['original_visual']})
    rows = result['rows']
    latencies = [r['audio_to_decision_s'] for r in rows]
    adviser = [r['recommendation']['advice'] for r in rows
               if r.get('recommendation') and 'advice' in r['recommendation']]
    return {'development_chapter_alignment': correct / total if total else None,
            'scored_s': total, 'aligned_s': correct, 'chapters': chapters,
            'visual_changes_during_audio': sum(0 < e['at'] <= duration for e in events),
            'ideas_displayed_during_audio': len({scenes[e['scene_id']]['concept_id'] for e in events if e['at'] <= duration}),
            'prepared_ideas': len(result['package']['concepts']),
            'asr_processing_s': sum(r['asr_s'] for r in rows),
            'asr_processing_real_time_factor': sum(r['asr_s'] for r in rows) / duration,
            'chunk_end_to_decision_p50_s': percentile(latencies, .5),
            'chunk_end_to_decision_p95_s': percentile(latencies, .95),
            'adviser_calls': len(adviser), 'adviser_failures': sum('error' in a for a in adviser),
            'adviser_models': sorted({a['model'] for a in adviser if 'model' in a}),
            'causality_violations': sum(r['decision_completed_at'] < r['asr_available_at'] or r['asr_available_at'] < r['end'] for r in rows),
            'scope': 'Coarse within-talk development reference, authored by the implementation operator. Not independent accuracy or audience usefulness.'}


def build_report(folder):
    folder = Path(folder)
    reference = json.loads((folder / 'reference.json').read_text())
    results = {mode: json.loads((folder / ('result-' + mode + '.json')).read_text()) for mode in ('local','jev')}
    if len({(r['package_hash'], r['asr_sha256'], r['controller_sha256']) for r in results.values()}) != 1:
        raise ValueError('Comparison requires the same prepared package, ASR trace and controller.')
    metrics = {mode: score_replay(r, reference) for mode,r in results.items()}
    save(folder / 'comparison.json', {'schema':'live_presenter.recording_comparison.v1',
        'reference_sha256': file_hash(folder / 'reference.json'), 'reference':reference, 'metrics':metrics})
    assets = Path(__file__).with_name('web')
    css = (assets / 'style.css').read_text() + (assets / 'recording.css').read_text()
    renderer = (assets / 'visuals.js').read_text().replace('export function ', 'function ')
    script = (assets / 'recording.js').read_text()
    payload = json.dumps({'results':results,'metrics':metrics,'reference':reference}, ensure_ascii=False).replace('<', '\\u003c')
    title = html_module.escape(results['local']['source']['title'])
    speaker = html_module.escape(results['local']['source'].get('speaker', 'See source'))
    page_url = results['local']['source'].get('page_url', '')
    if urlparse(page_url).scheme not in {'https','http'}:
        raise ValueError('The reference source needs an HTTP(S) page URL.')
    source_link = html_module.escape(page_url, quote=True)
    chunk_s = results['local']['asr']['chunk_s']
    visual_notes = html_module.escape(reference.get('visual_comparison_notes',
        'Compare the original visual forms against the prepared alternatives. Topic alignment does not score visual design.'))
    jev_stats = metrics['jev']
    onset = [c['first_matching_visual_lag_s'] for c in jev_stats['chapters'] if c['first_matching_visual_lag_s']]
    findings = (f"Jev-assisted matching displayed {jev_stats['ideas_displayed_during_audio']}/{jev_stats['prepared_ideas']} prepared ideas. "
                f"Local matching displayed {metrics['local']['ideas_displayed_during_audio']}/{metrics['local']['prepared_ideas']}. "
                + (f"First matching visuals for later sections lagged their coarse section starts by {min(onset):.0f}–{max(onset):.0f} seconds. " if onset else '')
                + f"Adviser failures: {jev_stats['adviser_failures']}/{jev_stats['adviser_calls']}. "
                + 'Visual quality and audience usefulness are not scored.')
    markup = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — recorded-talk comparison</title><style>{css}</style>
<main class="recording-report"><p class="eyebrow">LIVE PRESENTER · RECORDED AUDIO EXPERIMENT</p>
<h1>{title}</h1><p class="report-intro">Original presentation on the left. The actual prepared-scene renderer on the right, selected from bounded audio recognition. Local development replay; no browser/device timing claim.</p>
<p class="report-findings">{html_module.escape(findings)}</p>
<div class="report-controls"><label>Follower <select id="mode"><option value="local">Local prepared matching</option><option value="jev" selected>Jev-assisted matching</option></select></label><span id="summary"></span></div>
<div class="comparison-panels"><section><h2>Original visual reference</h2><video id="reference-video" src="video.mp4" muted playsinline preload="metadata"></video><p id="chapter"></p></section>
<section><h2>Live Presenter output</h2><div id="replay-stage"></div><p id="decision"></p></section></div>
<audio id="audio" controls preload="metadata" src="audio.wav"></audio>
<p class="audio-note">Audio controls both views. {chunk_s:g}-second recognition chunks introduce up to {chunk_s:g} seconds of waiting before processing. Seeking reconstructs the saved result; it does not rerun inference.</p>
<div class="heard"><span class="eyebrow">LAST PROCESSED AUDIO CHUNK</span><p id="heard">Start playback to compare.</p></div>
<h2>Jump to an argument section</h2><nav id="chapters"></nav>
<h2>Where the saved stage actually changed</h2><nav id="changes"></nav>
<h2>Development comparison</h2><div id="metrics"></div>
<details><summary>What this test measures and leaves unresolved</summary><ul id="limitations"></ul>
<p>{visual_notes}</p><p>Chapter alignment is a coarse operator-authored reference, not a gold standard for visual quality. The opening visual is preselected and contributes scored time. Comparison-player layout and media synchronization have not been browser-verified.</p>
<p>Preparation received the same talk’s complete untimed transcript in advance. The live follower received only the current recognized chunk and the approved package. Original video frames and caption timing were held out from the follower.</p>
<p>Local media and transcript remain outside Git. Original talk: {speaker}. <a href="{source_link}" target="_blank" rel="noopener">View source and attribution</a>. No TED endorsement is implied.</p></details>
</main><script type="application/json" id="recording-data">{payload}</script><script>{renderer}\n{script}</script></html>'''
    (folder / 'comparison.html').write_text(markup)
    (folder / 'comparison.html').chmod(0o600)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    acquire = sub.add_parser('acquire-ted')
    acquire.add_argument('url')
    acquire.add_argument('--folder', type=Path, required=True)
    transcribe = sub.add_parser('transcribe')
    transcribe.add_argument('audio', type=Path)
    transcribe.add_argument('--out', type=Path, required=True)
    transcribe.add_argument('--model', default='tiny.en')
    transcribe.add_argument('--chunk-s', type=float, default=6)
    transcribe.add_argument('--threads', type=int, default=4)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--folder', type=Path, required=True)
    prepare.add_argument('--provider', choices=['copilot','outline'], default='copilot')
    approve = sub.add_parser('approve')
    approve.add_argument('--folder', type=Path, required=True)
    approve.add_argument('--revision', type=int, required=True)
    approve.add_argument('--reviewed', action='store_true', required=True)
    approve.add_argument('--reviewer', default='Development operator')
    run = sub.add_parser('run')
    run.add_argument('--folder', type=Path, required=True)
    run.add_argument('--asr', type=Path, required=True)
    run.add_argument('--mode', choices=['local','jev'], default='local')
    report = sub.add_parser('report')
    report.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'acquire-ted':
        print(json.dumps(acquire_ted(args.url, args.folder), indent=2))
    elif args.command == 'transcribe':
        transcribe_audio(args.audio, args.out, model_name=args.model, chunk_s=args.chunk_s, threads=args.threads)
    elif args.command == 'prepare':
        p = prepare_recording(args.folder, args.provider)
        print(json.dumps({'project_id':p['id'], 'revision':p['revision'], 'job':p['job'], 'plan':p['plan']}, indent=2))
    elif args.command == 'run':
        replay(args.folder, args.asr, mode=args.mode)
    elif args.command == 'approve':
        with recording_store(args.folder / 'studio') as store:
            pid = json.loads((args.folder / 'project.json').read_text())['project_id']
            studio = Studio(store)
            p = studio.approve(pid, args.revision, args.reviewed)
            with store.change(pid) as p:
                p['evaluation_only'] = True
                p['approval']['reviewed_by'] = args.reviewer
        print('Approved for development replay:', p['approval']['package_hash'])
    elif args.command == 'report':
        print(json.dumps(build_report(args.folder), indent=2))


if __name__ == '__main__':
    main()
