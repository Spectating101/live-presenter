"""The one-command talk: supplied files become visuals; audio drives them; nothing opens a window."""
import base64
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import zlib

from presenter.attention import MATCH_GROUP, VisualMatcher
from presenter.engine import Store, Studio
from presenter.live_audio import LiveAudio
from presenter.native_output import VisualOutput
from presenter.talk import Capture, capture_command, choose_screen, deck_plan, load_sources, prepare_talk, spoken_phrases


def png(red=0):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    raw = b'\x00'+bytes([red, 40, 40])*4
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b''))


def minimal_pdf(pages):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', None, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for text in pages:
        stream = f'BT /F1 24 Tf 40 300 Td ({text}) Tj ET'.encode()
        objects.append(b'<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream))
        objects.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 640 360] /Contents %d 0 R '
                       b'/Resources << /Font << /F1 3 0 R >> >> >>' % len(objects))
        kids.append(b'%d 0 R' % len(objects))
    objects[1] = b'<< /Type /Pages /Kids [%s] /Count %d >>' % (b' '.join(kids), len(pages))
    out, offsets = b'%PDF-1.4\n', []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n%s\nendobj\n' % (number, body)
    start = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects)+1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    return out + b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects)+1, start)


class Decoder:
    ready = True

    def __init__(self, text='the washing machine in the village'):
        self.text = text
        self.windows = []

    def ensure_ready(self):
        pass

    def recognize(self, pcm):
        self.windows.append(len(pcm))
        return {'text': self.text}

    def reset(self):
        pass

    def close(self):
        pass


class TalkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'machine.png').write_bytes(png(10))
        (self.root/'machine.txt').write_text('the washing machine in the village')
        (self.root/'globe.png').write_bytes(png(200))
        (self.root/'globe.txt').write_text('energy use across the whole world')
        (self.root/'numbers.csv').write_text('Year,Energy_units,People\n2000,12,6\n2020,22,8\n')
        self.paths = [self.root/'machine.png', self.root/'globe.png', self.root/'numbers.csv']

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **values):
        store = Store(self.root/'store')
        studio, pid = prepare_talk(store, self.paths, dwell_s=0, **values)
        return store, studio, pid

    def test_every_supplied_visual_becomes_one_scene_as_supplied(self):
        store, _, pid = self.prepare()
        scenes = store.read(pid)['approval']['package']['scenes']
        renderable = [s for s in scenes if s['kind'] in {'image', 'chart'}]
        self.assertEqual(sorted(s['kind'] for s in renderable), ['chart', 'chart', 'image', 'image'])
        self.assertTrue(all(s['review_status'] == 'presenter_approved' for s in scenes))

    def test_a_large_deck_is_accepted(self):
        for i in range(30):
            (self.root/f's{i}.png').write_bytes(png(i))
        sources = load_sources([self.root/f's{i}.png' for i in range(30)])
        store = Store(self.root/'big')
        p = store.create(title='Deck', brief='Deck', audience='Room', sources=sources, provider='outline')
        self.assertEqual(len(deck_plan(p)['concepts']), 30)

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('pdftotext'), 'needs poppler')
    def test_pdf_slides_become_images_cued_by_their_own_words_and_sidecar_lines(self):
        (self.root/'deck.pdf').write_bytes(minimal_pdf(['Mosquito nets save lives', 'Polio cases are falling']))
        (self.root/'deck.txt').write_text('2: eradication campaign\n')
        sources = load_sources([self.root/'deck.pdf'])
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]['asset']['mime'], 'image/jpeg')
        self.assertIn('Mosquito nets', sources[0]['asset']['alt'])
        self.assertIn('eradication campaign', sources[1]['asset']['alt'])
        self.assertIn('Polio cases', sources[1]['asset']['alt'])
        store = Store(self.root/'deck-store')
        plan = deck_plan(store.create(title='Deck', brief='Deck', audience='Room', sources=sources))
        self.assertEqual(sorted(s['kind'] for s in plan['scenes']).count('image'), 2)

    def test_a_repeated_slide_is_one_visual_and_unknown_files_are_refused(self):
        (self.root/'again.png').write_bytes(png(10))
        self.assertEqual(len(load_sources([self.root/'machine.png', self.root/'again.png'])), 1)
        (self.root/'notes.docx').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'PDF slides'):
            load_sources([self.root/'notes.docx'])

    def test_talk_starts_on_the_speaker_then_speech_and_jev_bring_up_the_visual(self):
        store, studio, pid = self.prepare(moment_assessor=lambda words, earlier: {'look': .9})
        p = studio.control(pid, 'start')
        output = VisualOutput()
        output.accept(p)
        self.assertIsNone(output.scene)
        p = studio.transcript(pid, 'the washing machine in the village', 0, generation=p['live']['generation'])
        output.accept(p)
        self.assertEqual(output.scene['kind'], 'image')

    def test_capture_feeds_rolling_windows_and_ends_with_the_recording(self):
        store, studio, pid = self.prepare()
        p = studio.control(pid, 'start')
        decoder = Decoder()
        audio = LiveAudio(studio, decoder)
        # Five seconds of silence, written quickly; ages are measured from the first read.
        recorder = [sys.executable, '-c', "import sys,time\nfor _ in range(5):\n sys.stdout.buffer.write(bytes(32000));sys.stdout.flush();time.sleep(1)"]
        capture = Capture(audio, pid, recorder)
        capture.stream = audio.start(pid, p['live']['generation'])
        capture.start()
        self.assertTrue(capture.finished.wait(15))
        deadline = time.monotonic()+3
        while len(decoder.windows) < 4 and time.monotonic() < deadline:
            time.sleep(.02)
        audio.close()
        self.assertIsNone(capture.error)
        self.assertGreaterEqual(len(decoder.windows), 4)
        self.assertLessEqual(max(decoder.windows), 128000)

    def test_speech_keeps_driving_the_stage_after_a_key_press(self):
        store, studio, pid = self.prepare()
        p = studio.control(pid, 'start')
        decoder = Decoder()
        audio = LiveAudio(studio, decoder)
        session = audio.start(pid, p['live']['generation'])
        def send(seq, stream):
            audio.submit(pid, {'stream_id':stream['stream_id'],'generation':stream['generation'],'seq':seq,
                               'end_sample':(seq+1)*16000,'age_s':0,'pcm':base64.b64encode(bytes(min(seq+1,4)*32000)).decode()})
        def settle(count):
            deadline = time.monotonic()+3
            while len(decoder.windows) < count and time.monotonic() < deadline:
                time.sleep(.01)
            time.sleep(.05)
        send(0, session)
        settle(1)
        studio.control(pid, 'hold')
        rebound = audio.rebind(pid)
        self.assertEqual(rebound['stream_id'], session['stream_id'])
        self.assertEqual(rebound['generation'], store.read(pid)['live']['generation'])
        studio.control(pid, 'resume')
        rebound = audio.rebind(pid)
        self.assertEqual(rebound['status'], 'ready')
        decoder.text = 'energy use across the whole world'
        send(1, rebound)
        settle(2)
        audio.close()
        self.assertEqual(store.read(pid)['live']['transcript'][-1]['text'], decoder.text)

    def test_a_dead_recorder_is_reported_not_raised(self):
        store, studio, pid = self.prepare()
        p = studio.control(pid, 'start')
        audio = LiveAudio(studio, Decoder())
        capture = Capture(audio, pid, [sys.executable, '-c', 'raise SystemExit(3)'])
        capture.stream = audio.start(pid, p['live']['generation'])
        capture.start()
        self.assertTrue(capture.finished.wait(10))
        audio.close()
        self.assertIn('stopped unexpectedly', capture.error)

    def test_rehearsal_audio_uses_real_speed_and_a_microphone_is_never_implied(self):
        command = capture_command(audio_file='talk.wav', offset_s=40, duration_s=90)
        self.assertIn('-re', command)
        self.assertEqual(command[0], 'ffmpeg')
        self.assertEqual(command[-1], '-')

    def test_projector_is_the_last_screen_unless_chosen(self):
        self.assertEqual(choose_screen(['laptop', 'projector'], None), 'projector')
        self.assertEqual(choose_screen(['laptop', 'projector'], 0), 'laptop')
        with self.assertRaises(ValueError):
            choose_screen(['laptop'], 3)

    def test_matcher_sends_pictures_and_maps_the_answer_back_to_the_visual(self):
        class Backend:
            def __init__(self):
                self.calls = []

            async def ask(self, state, questions, assets):
                self.calls.append((questions, assets))
                answer = SimpleNamespace(value='v1', probabilities={'v1':.9, 'none':.1})
                return SimpleNamespace(answers={'pick':answer})
        backend = Backend()
        matcher = VisualMatcher([('a', b'one', 'A'), ('b', b'two', 'B'), ('c', None, 'Energy chart')], backend)
        self.assertEqual(matcher('look at this', ['earlier']), {'scene_id':'b', 'confidence':.9})
        questions, assets = backend.calls[0]
        self.assertEqual(len(assets), 2)
        self.assertIn('earlier look at this', questions['pick']['instructions'])
        self.assertIn('Energy chart', questions['pick']['criteria']['v2'])

    def test_large_decks_are_asked_in_groups_and_the_most_confident_wins(self):
        class Backend:
            async def ask(self, state, questions, assets):
                first = 'v0' if len(assets) == MATCH_GROUP else 'none'
                answer = SimpleNamespace(value=first, probabilities={first:.8})
                return SimpleNamespace(answers={'pick':answer})
        matcher = VisualMatcher([(f's{i}', bytes([i]), str(i)) for i in range(MATCH_GROUP+3)], Backend())
        self.assertEqual(matcher('words')['scene_id'], 's0')

    def test_spoken_phrases_are_short_and_bounded(self):
        phrases = spoken_phrases('Energy use across the whole world grew 22% since 2000 ' * 10)
        self.assertLessEqual(len(phrases), 16)
        self.assertTrue(all(len(p.split()) <= 3 for p in phrases))


if __name__ == '__main__':
    unittest.main()
