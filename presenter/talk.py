"""One command from your own files to a live, speaker-first talk.

    python -m presenter.talk deck.pdf photo.jpg numbers.csv

Each slide, image and numeric column becomes one visual, shown exactly as supplied.
Your microphone drives local speech recognition; the screen stays on you until the
words match a visual and Jev judges the moment one to look at, then returns to you.

Add spoken cue words beside a file: photo.txt for photo.jpg, or lines like
"7: mosquito net trial" in deck.txt for slide 7 of deck.pdf. Keys on the visual
window: Space clear, H hold/resume, N/PageDown next, B/PageUp back, Escape end.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from jev_credentials_v10 import load_jev_env
from system1_v10 import System1Error
from .attention import jev_moment
from .engine import STYLES, Conflict, Store, Studio, jev_adviser
from .live_audio import LiveAudio, SubprocessRecognizer
from .materials import identity, ingest
from .native_output import VisualOutput
from .planning import validate_plan

SLIDE_WIDTH = 1280
MAX_IMAGE_BYTES = 512_000
HEAVY_PACKAGE_BYTES = 10_000_000
WHISPER_MODEL = Path.home()/'.cache'/'whisper'/'tiny.en.pt'


def sidecar_cues(path):
    side = path.with_suffix('.txt')
    return side.read_text(encoding='utf-8-sig') if side.is_file() and side != path else ''


def shrink_image(path, folder):
    """Oversized photos are scaled down, never otherwise changed."""
    out = Path(folder)/(path.stem+'.small.jpg')
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(path),
                    '-vf',f"scale='min({SLIDE_WIDTH},iw)':-2",'-q:v','5',str(out)],check=True,capture_output=True,timeout=30)
    return out


def image_file(path, cues, folder):
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        small = shrink_image(path, folder)
        return ingest(path.stem+'.jpg', small.read_bytes(), cues)
    return ingest(path.name, data, cues)


def slide_sources(path, folder):
    """Render every page; its own words, plus any cue lines, are what the speaker may say."""
    extra = dict((int(n), words.strip()) for n, words in re.findall(r'(?m)^\s*(\d+)\s*:\s*(.+)$', sidecar_cues(path)))
    subprocess.run(['pdftoppm','-jpeg','-jpegopt','quality=72','-scale-to-x',str(SLIDE_WIDTH),'-scale-to-y','-1',
                    str(path),str(Path(folder)/'slide')],check=True,capture_output=True,timeout=120)
    sources = []
    for number, page in enumerate(sorted(Path(folder).glob('slide-*.jpg')), 1):
        words = subprocess.run(['pdftotext','-f',str(number),'-l',str(number),str(path),'-'],
                               capture_output=True,timeout=20,check=True).stdout.decode('utf-8','replace')
        cues = ' '.join(filter(None,[extra.get(number,''),' '.join(words.split())]))
        sources.append(ingest(f'{path.stem}-slide-{number:02d}.jpg', page.read_bytes(), cues))
    return sources


def load_sources(paths):
    sources, seen = [], set()
    with tempfile.TemporaryDirectory(prefix='presenter-talk-') as folder:
        for path in map(Path, paths):
            if not path.is_file():
                raise ValueError(f'{path} is not a file.')
            suffix = path.suffix.lower()
            if suffix == '.pdf':
                pages = Path(folder)/path.stem
                pages.mkdir(exist_ok=True)
                found = slide_sources(path, pages)
            elif suffix in {'.png','.jpg','.jpeg'}:
                found = [image_file(path, sidecar_cues(path), folder)]
            elif suffix in {'.csv','.tsv'}:
                found = [ingest(path.name, path.read_bytes())]
            else:
                raise ValueError(f'{path.name}: use PDF slides, PNG or JPEG images, or CSV/TSV numbers.')
            for source in found:
                if source['id'] not in seen:  # A repeated slide is one visual.
                    seen.add(source['id'])
                    sources.append(source)
    if not sources:
        raise ValueError('Add at least one slide, image or numeric table.')
    return sources


def spoken_phrases(text):
    """Short pieces of a slide that someone could plausibly say aloud."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]+|\d[\d.,%]*", text)
    return [' '.join(words[i:i+3]) for i in range(0, max(len(words)-1, 1), 3)][:16]


def deck_plan(project):
    """Every supplied visual, as supplied. Nothing is generated, so approval is the choice of files."""
    concepts = []
    def add(title, cues, unit, visual):
        taken = {c['title'] for c in concepts}
        title = title if title not in taken else f'{title} · {len(concepts)+1}'
        quote = cues if len(cues) >= 12 and cues in unit['text'] else unit['text'][:1200]
        concepts.append({'title':title,'summary':(cues or title)[:500],'aliases':spoken_phrases(cues or title),
                         'source_refs':[{'unit_id':unit['id'],'quote':' '.join(quote.split())[:1200]}],'visuals':[visual]})
    for source in project['sources']:
        unit = source['units'][0]
        if source.get('asset'):
            cues = source['asset']['alt'] if not source['asset']['alt'].startswith('Supplied image:') else ''
            name = re.sub(r'[-_.]+',' ',Path(source['name']).stem).strip()
            add(' '.join(cues.split()[:8]) or name, cues or name, unit, {'kind':'image','asset_id':source['id']})
        elif source['dataset'] and source['dataset']['numeric_columns']:
            data = source['dataset']
            label = re.sub(r'[-_.]+',' ',Path(source['name']).stem).strip()
            for column in [c for c in data['numeric_columns'] if c != data['columns'][0]][:6]:
                spoken = re.sub(r'[-_]+',' ',column)
                add(f'{spoken} ({label})', f'{spoken} {label} '+' '.join(str(r[data['columns'][0]]) for r in data['rows'][:6]),
                    unit, {'kind':'chart','dataset_id':data['id'],'x':data['columns'][0],'y':column})
    return validate_plan({'title':project['title'],'audience':project['audience'],'takeaway':project['brief'],
                          'understanding':'Your supplied slides, images and tables, shown as supplied.',
                          'questions':[],'concepts':concepts}, project)


class DeckPlanner:
    def prepare(self, project):
        return deck_plan(project)


def prepare_talk(store, paths, *, moment_assessor=None, live_assessor=None, style='speaker_led', title='Live talk', dwell_s=2.5):
    sources = load_sources(paths)
    studio = Studio(store, planner=DeckPlanner(), moment_assessor=moment_assessor, live_assessor=live_assessor, dwell_s=dwell_s)
    # The planner slot takes the deck builder; the "outline" provider would bypass it for the generic outline.
    p = store.create(title=title, brief=title, audience='The people in the room', sources=sources)
    p = studio.prepare(p['id'], background=False)
    p = studio.approve(p['id'], p['revision'], True)
    studio.control(p['id'], 'style', style=style)
    studio.control(p['id'], 'reflex', enabled=True)
    if live_assessor:
        studio.control(p['id'], 'adviser', enabled=True)
    return studio, p['id']


def capture_command(*, audio_file=None, device=None, offset_s=0, duration_s=None):
    if audio_file:  # Same path as a microphone, delivered at real speed.
        return ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-re','-ss',str(offset_s),'-i',str(audio_file),
                *(['-t',str(duration_s)] if duration_s else []),'-ar','16000','-ac','1','-f','s16le','-']
    if shutil.which('arecord'):
        return ['arecord','-q','-f','S16_LE','-r','16000','-c','1','-t','raw',*(['-D',device] if device else [])]
    if shutil.which('pw-record'):
        return ['pw-record','--rate','16000','--channels','1','--format','s16',*(['--target',device] if device else []),'-']
    raise ValueError('No microphone recorder found. Install alsa-utils or pipewire.')


class Capture(threading.Thread):
    """Reads one second at a time and offers the latest four seconds to recognition."""
    def __init__(self, audio, pid, command):
        super().__init__(daemon=True, name='presenter-capture')
        self.audio, self.pid, self.command = audio, pid, command
        self.process = None
        self.stream = None
        self.finished = threading.Event()
        self.error = None

    def run(self):
        try:
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            pcm, seq, origin = b'', 0, time.monotonic()
            while True:
                second = self.process.stdout.read(32000)
                if len(second) < 32000:
                    break
                pcm = (pcm+second)[-128000:]
                age = max(0, time.monotonic()-(origin+seq+1))
                stream = self.stream
                if stream and age < self.audio.max_age_s:
                    try:
                        self.audio.submit(self.pid, {'stream_id':stream['stream_id'],'generation':stream['generation'],'seq':seq,
                                                     'end_sample':(seq+1)*16000,'age_s':age,'pcm':base64.b64encode(pcm).decode()})
                    except Conflict:
                        pass  # The stage reset this stream; the next one takes over.
                seq += 1
            if self.process.wait() and not self.stopped():
                self.error = 'The microphone recorder stopped unexpectedly.'
        except OSError as error:
            self.error = str(error)
        finally:
            if self.process:
                self.process.stdout.close()
            self.finished.set()

    def stopped(self):
        return self.process is not None and self.process.returncode is not None and self.process.returncode < 0

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


def preflight(args, *, asr_python, qt_screens=None):
    """Everything that can quietly ruin a talk, checked before it starts."""
    rows = []
    def check(name, ok, detail, required=True):
        rows.append({'check':name,'ok':bool(ok),'required':required,'detail':detail})
    python_ok = Path(asr_python).exists()
    if python_ok:
        probe = subprocess.run([str(asr_python),'-c','import whisper,torch'],capture_output=True,timeout=120)
        python_ok = probe.returncode == 0
    check('Speech recognition', python_ok, str(asr_python) if python_ok else 'Run make talk-setup.')
    check('Speech model', WHISPER_MODEL.exists(), str(WHISPER_MODEL) if WHISPER_MODEL.exists() else 'Downloaded on first use; needs internet once.', required=False)
    try:
        command = capture_command(audio_file=getattr(args,'audio_file',None), device=getattr(args,'mic_device',None))
        check('Audio input', True, command[0])
    except ValueError as error:
        check('Audio input', False, str(error))
    for tool, reason in [('ffmpeg','oversized images'),('pdftoppm','PDF slides'),('pdftotext','PDF slide words')]:
        check(tool, shutil.which(tool), 'found' if shutil.which(tool) else 'Needed for '+reason, required=False)
    if getattr(args,'no_jev',False):
        check('Jev timing', False, 'Turned off; the screen follows prepared topics only.', required=False)
    elif not load_jev_env(getattr(args,'env_file',None)):
        check('Jev timing', False, 'No key found; the screen follows prepared topics only.', required=False)
    else:
        try:
            begun = time.perf_counter()
            jev_moment('Look at this chart of the numbers.')
            check('Jev timing', True, f'{(time.perf_counter()-begun)*1000:.0f} ms round trip')
        except (System1Error, OSError, KeyError) as error:
            check('Jev timing', False, type(error).__name__+'; the screen falls back to prepared topics.', required=False)
    if qt_screens is not None:
        names = ', '.join(f'{i}: {s.name()} {s.size().width()}x{s.size().height()}' for i,s in enumerate(qt_screens))
        check('Display', bool(qt_screens), names or 'No display found.')
    return rows


def print_preflight(rows):
    for row in rows:
        mark = 'ok  ' if row['ok'] else ('FAIL' if row['required'] else 'warn')
        print(f"{mark}  {row['check']}: {row['detail']}", flush=True)
    return all(row['ok'] or not row['required'] for row in rows)


def choose_screen(screens, wanted):
    """An attached projector is normally the last screen; say --screen to choose another."""
    if wanted is None:
        return screens[-1]
    if not 0 <= wanted < len(screens):
        raise ValueError(f'Choose a screen from 0 to {len(screens)-1}.')
    return screens[wanted]


def describe(project, scene_id):
    plan = project['approval']['package']
    scene = next((s for s in plan['scenes'] if s['id'] == scene_id), None)
    return scene['title'] if scene else 'speaker'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('materials', nargs='*', type=Path, help='PDF slides, PNG/JPEG images, CSV/TSV numbers')
    parser.add_argument('--check', action='store_true', help='Check this machine and exit; opens no window and does not record.')
    parser.add_argument('--title', default='Live talk')
    parser.add_argument('--style', choices=sorted(STYLES), default='speaker_led')
    parser.add_argument('--screen', type=int, help='Which display shows the visuals; defaults to the last one.')
    parser.add_argument('--mic-device', help='Recorder device name; defaults to the system microphone.')
    parser.add_argument('--no-jev', action='store_true')
    parser.add_argument('--env-file', help='Existing credentials file holding the Jev key.')
    parser.add_argument('--asr-python', type=Path, default=Path('.venv-asr/bin/python'))
    parser.add_argument('--data-dir', type=Path, default=Path('artifacts/talks'))
    parser.add_argument('--audio-file', type=Path, help='Rehearse from a recording at real speed instead of a microphone.')
    parser.add_argument('--offset-s', type=float, default=0)
    parser.add_argument('--duration-s', type=float)
    parser.add_argument('--export', type=Path, help='Run offscreen from --audio-file; save each visual change and a report here.')
    args = parser.parse_args()
    if args.export and not args.audio_file:
        parser.error('--export needs --audio-file; it never records a microphone.')
    if args.export or args.check and 'DISPLAY' not in os.environ and 'WAYLAND_DISPLAY' not in os.environ:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from .native import qt_types
    QApplication, VisualSurface, QTimer = qt_types()
    from PySide6.QtCore import QEvent, QObject, Qt
    app = QApplication([])
    rows = preflight(args, asr_python=args.asr_python, qt_screens=app.screens())
    ready = print_preflight(rows)
    if args.check:
        return 0 if ready else 1
    if not ready:
        return 1
    if not args.materials:
        parser.error('Name at least one slide deck, image or table.')
    jev_ok = any(r['check'] == 'Jev timing' and r['ok'] for r in rows)
    store = Store(args.data_dir/time.strftime('%Y%m%d-%H%M%S'))
    studio, pid = prepare_talk(store, args.materials, title=args.title, style=args.style,
                               moment_assessor=jev_moment if jev_ok else None, live_assessor=jev_adviser if jev_ok else None)
    scenes = store.read(pid)['approval']['package']['scenes']
    print(f'{len(scenes)} visuals ready. The screen is on you until one is needed.', flush=True)
    # Decision time grows with the saved package (about 190 ms at 4 MB on the development machine).
    if store.path(pid).stat().st_size > HEAVY_PACKAGE_BYTES:
        print('warn  This deck is large, so visuals may react more slowly. Smaller or fewer images help.', flush=True)
    audio = LiveAudio(studio, SubprocessRecognizer(args.asr_python))
    output = VisualOutput()
    surface = VisualSurface(animate=not args.export)
    if args.export:
        surface.resize(1280, 720)
        args.export.mkdir(parents=True, exist_ok=True)
    capture = None
    events, origin, previous_mtime = [], None, None

    def act(action, **values):
        try:
            studio.control(pid, action, **values)
        except (Conflict, ValueError) as error:
            print('Stage: '+str(error), flush=True)

    class Keys(QObject):
        def eventFilter(self, _, event):
            if event.type() != QEvent.Type.KeyPress:
                return False
            key = event.key()
            if key == Qt.Key.Key_Space:
                act('clear')
            elif key == Qt.Key.Key_H:
                act('resume' if store.read(pid)['live']['locked'] else 'hold')
            elif key in {Qt.Key.Key_N, Qt.Key.Key_PageDown, Qt.Key.Key_Right}:
                act('next')
            elif key in {Qt.Key.Key_B, Qt.Key.Key_PageUp, Qt.Key.Key_Left}:
                act('back')
            else:
                return False
            return True
    keys = Keys()
    surface.installEventFilter(keys)

    def begin_stream():
        p = store.read(pid)
        capture.stream = audio.start(pid, p['live']['generation'])

    def finish():
        if capture:
            capture.close()
        audio.close()
        p = store.read(pid)
        report = {'schema':'live_presenter.talk.v1','materials':[m.name for m in args.materials],'style':args.style,
                  'jev_timing':jev_ok,'audio_file':str(args.audio_file) if args.audio_file else None,
                  'duration_s':time.monotonic()-origin if origin else 0,'preflight':rows,'events':events,
                  'audio':audio.snapshot(pid),'moment_stats':p['live'].get('moment_stats'),'transcript':p['live']['transcript']}
        (store.root/'talk-report.json').write_text(json.dumps(report, indent=2, default=str))
        if args.export:
            (args.export/'report.json').write_text(json.dumps(report, indent=2, default=str))
        print('Saved '+str(store.root/'talk-report.json'), flush=True)

    def tick():
        nonlocal previous_mtime
        try:
            if origin is None:
                return  # Still warming up; the stage cannot change until audio starts.
            state = audio.snapshot(pid)
            if state.get('status') == 'error':
                print('Speech recognition failed; restarting it. Keys still work.', flush=True)
                audio.stop(pid, capture.stream['stream_id'])
                begin_stream()
            if capture.finished.is_set():
                if capture.error:
                    print('Audio stopped: '+capture.error+' Keys still work.', flush=True)
                    capture.error = None
                if args.audio_file:
                    app.quit()
                    return
            stamp = store.path(pid).stat().st_mtime_ns
            if stamp == previous_mtime:
                return
            previous_mtime = stamp
            p = store.read(pid)
            received = time.perf_counter()
            if output.accept(p):
                surface.present(output, received)
                at = time.monotonic()-origin
                row = {'at_s':round(at,2),'scene_id':(output.scene or {}).get('id'),'visual':describe(p, (output.scene or {}).get('id')),
                       'attention':output.attention,'decision':p['live']['decision'],
                       'moment':(p['live'].get('recommendation') or {}).get('moment'),
                       'heard':[r['text'] for r in p['live']['transcript'][-1:]]}
                events.append(row)
                print(f"{at:7.1f}s  {row['visual']}  ({p['live']['decision']['reason']})", flush=True)
                if args.export:
                    app.processEvents()
                    surface.grab().save(str(args.export/f'{len(events):03d}-{at:07.1f}s.png'))
        except (ValueError, OSError, KeyError) as error:
            # Status belongs in the terminal; nothing ever covers the visual.
            print('Output retained: '+type(error).__name__, file=sys.stderr, flush=True)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(20)
    screen = choose_screen(app.screens(), args.screen)
    surface.setScreen(screen)
    surface.setGeometry(screen.geometry() if not args.export else surface.geometry())
    if args.export:
        surface.show()
    else:
        surface.showFullScreen()
        print(f'Visuals on {screen.name()}. Space clear, H hold, N next, B back, Escape end.', flush=True)
    studio.control(pid, 'start')
    capture = Capture(audio, pid, capture_command(audio_file=args.audio_file, device=args.mic_device,
                                                  offset_s=args.offset_s, duration_s=args.duration_s))
    begin_stream()
    print('Warming up speech recognition…', flush=True)
    warm = time.monotonic()
    while audio.snapshot(pid)['status'] != 'ready':
        if audio.snapshot(pid)['status'] == 'error' or time.monotonic()-warm > 60:
            finish()
            print('Speech recognition did not start. Check with: python -m presenter.talk --check', flush=True)
            return 1
        app.processEvents()
        time.sleep(.02)
    origin = time.monotonic()
    capture.start()
    print('Listening.', flush=True)
    code = app.exec()
    finish()
    return code


if __name__ == '__main__':
    sys.exit(main())
