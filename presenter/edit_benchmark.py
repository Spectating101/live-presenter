"""Measure how edited presentation recordings balance the speaker and visuals.

An edited recording of a live talk is a human oracle for visual assistance: it
shows when the edit cuts to presented content, how long that content stays and
when attention returns to the speaker. This module acquires catalogued
recordings into ignored local storage, detects shot cuts, classifies sampled
frames with Jev and summarizes each recording's balance profile.

Media, frames and per-frame labels stay in ignored artifacts. The edit reflects
one production team's judgment for a video audience; it is a reference, not a
measurement of what the room screen showed or of audience comprehension.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys

from jev_credentials_v10 import load_jev_env
from system1_v10 import JevBackend, System1Error
from .recording import file_hash, save

CATALOG = Path('data/presentation_benchmark_v1.json')
ROOT = Path('artifacts/presentation_benchmark')
FORMAT = 'bv*[height<=480]+ba/b[height<=480]/b'
# English only: a pattern such as en.* also requests every auto-translated track and triggers rate limits.
SUB_LANGS = 'en,en-US,en-GB,en-orig'

# Props and demonstrations are speaker moments: a projector-side assistant cannot show them.
LABELS = {
    'speaker': 'The presenter is the main subject and is not handling an object. No projected screen content '
               'is readable.',
    'speaker_with_object': 'The presenter is the main subject and is holding, pointing at or demonstrating a '
                           'physical object, prop or experiment. No projected screen content is readable.',
    'board': 'Handwriting or drawing on a blackboard, whiteboard or paper is the main subject, with or without '
             'the presenter.',
    'fullscreen_visual': 'The whole frame is presented content: a slide, chart, photo, diagram, video clip or '
                         'computer screen shown edge to edge. No stage, room or projector screen border is visible.',
    'stage_with_screen': 'A shot of the stage or room in which a projector screen showing readable content is '
                         'prominent. The presenter may be small, partly visible or absent.',
    'audience': 'The audience is the main subject.',
    'other': 'A title card, logo, credits, blank or transition frame.',
}
VISUAL = 'fullscreen_visual'
CONTENT = {'fullscreen_visual', 'stage_with_screen'}
STATE = 'Frames sampled from an edited video recording of a live presentation, such as a talk, lecture or keynote.'
LABEL_KEY = hashlib.sha256(json.dumps([STATE, LABELS], sort_keys=True).encode()).hexdigest()[:16]


def load_catalog(path=CATALOG):
    catalog = json.loads(Path(path).read_text())
    for record in catalog['records']:
        missing = {'id', 'genre', 'url', 'rights'} - set(record)
        if missing or not re.fullmatch(r'[a-z0-9_]+', record['id']):
            raise ValueError(f"Invalid catalog record {record.get('id')!r}: {sorted(missing)}")
    return catalog


def acquire(record, root=ROOT, ytdlp='.venv-media/bin/yt-dlp'):
    """Download low-resolution video, English captions and metadata once."""
    folder = Path(root) / record['id']
    video = folder / 'video.mp4'
    if not video.exists() or not (folder / 'video.info.json').exists():
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run([ytdlp, '-q', '--no-progress', '--no-playlist', '-f', FORMAT, '--merge-output-format', 'mp4',
                        '--write-subs', '--write-auto-subs', '--sub-langs', SUB_LANGS, '--sub-format', 'vtt',
                        '--write-info-json', *(['--skip-download'] if video.exists() else []),
                        '-o', str(folder / 'video.%(ext)s'), record['url']], check=True)
    info = json.loads((folder / 'video.info.json').read_text())
    version = subprocess.run([ytdlp, '--version'], capture_output=True, text=True, check=True).stdout.strip()
    source = {'id': record['id'], 'url': record['url'], 'genre': record['genre'], 'rights': record['rights'],
              'extractor': info.get('extractor'), 'media_id': info.get('id'), 'title': info.get('title'),
              'channel': info.get('channel') or info.get('uploader'), 'duration_s': info.get('duration'),
              'video_sha256': file_hash(video), 'yt_dlp': version}
    save(folder / 'source.json', source)
    return folder


def media_duration(video):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(video)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def parse_cuts(showinfo):
    return sorted({round(float(t), 3) for t in re.findall(r'pts_time:([0-9.]+)', showinfo)})


def detect_cuts(video, threshold=0.3):
    """Hard cuts and abrupt slide changes from FFmpeg's scene score."""
    result = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(video), '-an', '-vf',
                             f"select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'],
                            capture_output=True, text=True, check=True)
    return parse_cuts(result.stderr)


def shots(cuts, duration):
    edges = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]


def sample_times(cuts, duration, max_gap=5.0):
    """Evenly spaced samples inside every shot, never more than max_gap apart.

    Long shots get several samples so slow zooms and dissolves between the
    speaker and the screen are not hidden inside one label."""
    samples = []
    for a, b in shots(cuts, duration):
        n = max(1, math.ceil((b - a) / max_gap))
        samples += [round(a + (i + .5) * (b - a) / n, 3) for i in range(n)]
    return samples


def frame_name(t):
    return f'frame_{round(t * 1000):09d}.jpg'


FRAME_WIDTH = 512  # Jev rejects images with either side under 280 px; 16:9 at 512 gives 288.


def extract_frames(video, times, folder, width=FRAME_WIDTH):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for t in times:
        path = folder / frame_name(t)
        if not path.exists():
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', str(video),
                            '-frames:v', '1', '-vf', f'scale={width}:-2', '-q:v', '4', str(path)], check=True)
    return [folder / frame_name(t) for t in times]


def frame_questions(paths):
    """One Choice question per frame; each question carries its own image."""
    questions, assets = {}, {}
    for i, path in enumerate(paths):
        ref = 'img-' + hashlib.sha256(path.name.encode()).hexdigest()[:20]
        questions[f'f{i}'] = {'type': 'choice', 'criteria': LABELS,
                              'instructions': f'What does this video frame mainly show? Frame: {ref}'}
        assets[ref] = {'type': 'image', 'format': 'jpg', 'data_base64': base64.b64encode(path.read_bytes()).decode()}
    return questions, assets


async def classify_frames(paths, backend, *, cache=None, batch=8, workers=3, retries=3):
    """Label frames with Jev, resuming from a cache keyed by frame name and label set."""
    cache = cache if cache is not None else {}
    todo = [p for p in paths if f'{LABEL_KEY}:{p.name}' not in cache]
    gate = asyncio.Semaphore(workers)
    usage = {'calls': 0, 'input_tokens': 0, 'models': set(), 'failures': 0}

    async def run(group):
        questions, assets = frame_questions(group)
        async with gate:
            for attempt in range(retries):
                try:
                    response = await backend.ask(STATE, questions, assets)
                    break
                except System1Error:
                    usage['failures'] += 1
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
        usage['calls'] += 1
        usage['input_tokens'] += response.input_tokens
        usage['models'].add(response.model)
        for i, path in enumerate(group):
            answer = response.answers[f'f{i}']
            cache[f'{LABEL_KEY}:{path.name}'] = {'label': answer.value, 'confidence': round(answer.confidence, 4),
                                                 'probabilities': {k: round(v, 4) for k, v in answer.probabilities.items()}}

    await asyncio.gather(*(run(todo[i:i + batch]) for i in range(0, len(todo), batch)))
    usage['models'] = sorted(usage['models'])
    return {p.name: cache[f'{LABEL_KEY}:{p.name}'] for p in paths}, usage


def build_timeline(cuts, duration, labelled):
    """Intervals between cuts, split halfway between samples whose labels differ.

    labelled is a time-sorted list of (time, label, confidence)."""
    intervals = []
    for a, b in shots(cuts, duration):
        inside = [s for s in labelled if a <= s[0] < b]
        if not inside:
            continue
        for i, (t, label, confidence) in enumerate(inside):
            start = a if i == 0 else (inside[i - 1][0] + t) / 2
            end = b if i == len(inside) - 1 else (t + inside[i + 1][0]) / 2
            intervals.append({'start': round(start, 3), 'end': round(end, 3), 'label': label,
                              'confidence': confidence, 'cut_at_start': i == 0 and a > 0})
    merged = []
    for item in intervals:
        last = merged[-1] if merged else None
        if last and last['label'] == item['label'] and abs(last['end'] - item['start']) < 1e-6:
            last['end'] = item['end']
            last['content_changes'] += int(item['cut_at_start'])
            last['low_confidence_s'] += (item['end'] - item['start']) * (item['confidence'] < .6)
        else:
            merged.append({'start': item['start'], 'end': item['end'], 'label': item['label'], 'content_changes': 0,
                           'low_confidence_s': (item['end'] - item['start']) * (item['confidence'] < .6)})
    for run in merged:
        run['low_confidence_s'] = round(run['low_confidence_s'], 3)
    return merged


def spread(values):
    if not values:
        return None
    ordered = sorted(values)
    q = statistics.quantiles(ordered, n=4, method='inclusive') if len(ordered) > 1 else [ordered[0]] * 3
    return {'n': len(ordered), 'median': round(q[1], 2), 'p25': round(q[0], 2), 'p75': round(q[2], 2),
            'max': round(ordered[-1], 2), 'total': round(sum(ordered), 2)}


def episodes(timeline, labels):
    """Contiguous runs whose labels are all in `labels`."""
    runs = []
    for item in timeline:
        if item['label'] in labels:
            if runs and abs(runs[-1]['end'] - item['start']) < 1e-6:
                runs[-1]['end'] = item['end']
                runs[-1]['content_changes'] += item['content_changes'] + 1
            else:
                runs.append({'start': item['start'], 'end': item['end'], 'content_changes': item['content_changes']})
    return runs


def profile(timeline, duration):
    minutes = duration / 60
    seconds = {label: 0.0 for label in LABELS}
    for item in timeline:
        seconds[item['label']] += item['end'] - item['start']
    full = episodes(timeline, {VISUAL})
    content = episodes(timeline, CONTENT)
    # Speaker time between two content episodes: how long the edit returns to the person.
    returns = [b['start'] - a['end'] for a, b in zip(content, content[1:])]
    return {
        'duration_s': round(duration, 2),
        'share': {label: round(s / duration, 4) for label, s in seconds.items()},
        'content_share': round(sum(seconds[label] for label in CONTENT) / duration, 4),
        'full_visual_episodes': spread([e['end'] - e['start'] for e in full]),
        'full_visual_per_min': round(len(full) / minutes, 2),
        'content_episodes': spread([e['end'] - e['start'] for e in content]),
        'content_per_min': round(len(content) / minutes, 2),
        'returns_between_content': spread(returns),
        'changes_within_full_visuals_per_visual_min': round(
            sum(e['content_changes'] for e in full) / max(seconds[VISUAL] / 60, 1e-9), 2) if full else 0,
        'low_confidence_share': round(sum(i['low_confidence_s'] for i in timeline) / duration, 4),
    }


def seconds_on(intervals, duration):
    """Per-second booleans: was any interval active at the middle of each second."""
    marks = [False] * int(duration)
    for start, end in intervals:
        for s in range(max(0, math.ceil(start - .5)), min(len(marks), math.ceil(end - .5))):
            marks[s] = True
    return marks


def stage_intervals(events, duration):
    """Visible-visual intervals from a replay's stage events (scene_id None means the speaker)."""
    spans = []
    for event, nxt in zip(events, [*events[1:], {'at': duration}]):
        if event['scene_id'] and nxt['at'] > event['at']:
            spans.append((event['at'], nxt['at']))
    return spans


def compare_replay(analysis, replay, offset_s=0.0):
    """Score a recorded replay's stage; offset_s maps replay audio time onto the video (video = replay + offset)."""
    duration = analysis['profile']['duration_s']
    result = compare_intervals(analysis, [(a + offset_s, b + offset_s)
                                          for a, b in stage_intervals(replay['events'], duration)])
    result['offset_s'] = offset_s
    result['stage_changes'] = sum(1 for a, b in zip(replay['events'], replay['events'][1:])
                                  if a['scene_id'] != b['scene_id'])
    return result


def compare_intervals(analysis, intervals):
    """Second-by-second agreement between screen-on intervals and the edit's cuts to presented content."""
    duration = analysis['profile']['duration_s']
    edit = seconds_on([(t['start'], t['end']) for t in analysis['timeline'] if t['label'] in CONTENT], duration)
    full = seconds_on([(t['start'], t['end']) for t in analysis['timeline'] if t['label'] == VISUAL], duration)
    shown = seconds_on(intervals, duration)
    n = len(edit)
    both = sum(e and s for e, s in zip(edit, shown))
    neither = sum(not e and not s for e, s in zip(edit, shown))
    agree = (both + neither) / n
    p_edit, p_shown = sum(edit) / n, sum(shown) / n
    chance = p_edit * p_shown + (1 - p_edit) * (1 - p_shown)
    edit_runs = episodes([{'start': i, 'end': i + 1, 'label': 'on', 'content_changes': 0}
                          for i, on in enumerate(full) if on], {'on'})
    covered = [r for r in edit_runs if any(shown[int(r['start']):int(r['end'])])]
    return {'seconds': n, 'edit_content_share': round(p_edit, 4),
            'stage_visual_share': round(p_shown, 4), 'agreement': round(agree, 4),
            'kappa': round((agree - chance) / (1 - chance), 4) if chance < 1 else None,
            'speaker_time_left_clear': round(neither / max(1, n - sum(edit)), 4),
            'edit_fullscreen_episodes_covered': f'{len(covered)}/{len(edit_runs)}',
            'stage_visual_episodes': spread([b - a for a, b in intervals])}


def analyze(folder, backend, *, threshold=0.3, max_gap=5.0, batch=8, workers=3):
    folder = Path(folder)
    video = folder / 'video.mp4'
    duration = media_duration(video)
    cuts = detect_cuts(video, threshold)
    times = sample_times(cuts, duration, max_gap)
    paths = extract_frames(video, times, folder / 'frames')
    cache_path = folder / 'labels.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    try:
        labels, usage = asyncio.run(classify_frames(paths, backend, cache=cache, batch=batch, workers=workers))
    finally:
        save(cache_path, cache)
    labelled = [(t, labels[p.name]['label'], labels[p.name]['confidence']) for t, p in zip(times, paths)]
    timeline = build_timeline(cuts, duration, labelled)
    result = {'source': json.loads((folder / 'source.json').read_text()), 'label_key': LABEL_KEY, 'labels': LABELS,
              'method': {'cut_threshold': threshold, 'max_sample_gap_s': max_gap, 'cuts': len(cuts),
                         'frames': len(paths), 'frame_width': FRAME_WIDTH, 'classifier_usage': usage},
              'profile': profile(timeline, duration), 'timeline': timeline}
    save(folder / 'analysis.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['acquire', 'analyze', 'compare', 'summarize'])
    parser.add_argument('--replay', type=Path, help='compare: a recorded replay result JSON')
    parser.add_argument('--out', type=Path, help='summarize: write the compact results record here')
    parser.add_argument('--offset-s', type=float, default=0.0, help='compare: video time = replay time + offset')
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--ids', nargs='*', help='Catalog ids; default all.')
    parser.add_argument('--ytdlp', default='.venv-media/bin/yt-dlp')
    parser.add_argument('--model', default='jev-preview')
    parser.add_argument('--env-file', help='Existing credential file; read as data, never executed.')
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    records = [r for r in load_catalog(args.catalog)['records'] if not args.ids or r['id'] in args.ids]
    if args.ids and len(records) != len(set(args.ids)):
        parser.error('Unknown catalog id.')
    if args.command == 'acquire':
        failed = []
        for record in records:
            try:
                print(record['id'], acquire(record, args.root, args.ytdlp), flush=True)
            except subprocess.CalledProcessError:
                failed.append(record['id'])
                print(record['id'], 'FAILED; rerun acquire to retry', flush=True)
        return 1 if failed else 0
    if args.command == 'summarize':
        rows = []
        for record in records:
            path = args.root / record['id'] / 'analysis.json'
            if not path.exists():
                rows.append({'id': record['id'], 'genre': record['genre'], 'status': 'not analyzed'})
                continue
            analysis = json.loads(path.read_text())
            rows.append({'id': record['id'], 'genre': record['genre'], 'status': 'analyzed',
                         'media': {k: analysis['source'][k] for k in ('extractor', 'media_id', 'channel', 'video_sha256')},
                         'method': {k: v for k, v in analysis['method'].items() if k != 'classifier_usage'},
                         'classifier_models': analysis['method']['classifier_usage']['models'],
                         'profile': analysis['profile']})
        summary = {'schema': 'live_presenter.presentation_benchmark_results.v1', 'label_key': LABEL_KEY,
                   'labels': LABELS, 'content_labels': sorted(CONTENT), 'recordings': rows}
        if args.out:
            save(args.out, summary)
        print(json.dumps(summary, indent=2))
        return 0
    if args.command == 'compare':
        if len(records) != 1 or not args.replay:
            parser.error('compare needs exactly one --ids value and --replay.')
        analysis = json.loads((args.root / records[0]['id'] / 'analysis.json').read_text())
        print(json.dumps(compare_replay(analysis, json.loads(args.replay.read_text()), args.offset_s), indent=2))
        return
    if not load_jev_env(args.env_file):
        parser.error('No Jev credential: set JEV_API_KEY or pass --env-file.')
    backend = JevBackend(model=args.model, timeout_s=60)
    failed = []
    for record in records:
        try:
            result = analyze(args.root / record['id'], backend, batch=args.batch, workers=args.workers)
        except (OSError, ValueError, subprocess.CalledProcessError, System1Error) as error:
            failed.append(record['id'])
            print(json.dumps({'id': record['id'], 'error': f'{type(error).__name__}: {error}'}), flush=True)
            continue
        print(json.dumps({'id': record['id'], **result['profile']}), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
