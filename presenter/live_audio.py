"""Opt-in local PCM recognition. Only the child process imports ASR dependencies."""
import argparse
import base64
import collections
import json
import math
import os
from pathlib import Path
import secrets
import selectors
import subprocess
import sys
import threading
import time

from .engine import Conflict


class SubprocessRecognizer:
    def __init__(self, python, *, timeout_s=2, startup_s=30):
        # Preserve a virtualenv's interpreter symlink so its site-packages load.
        self.python, self.timeout_s, self.startup_s = str(Path(python).absolute()), timeout_s, startup_s
        self.process = None
        self.ready = False
        self.closed = False
        self.lock = threading.Lock()

    def reset(self):
        with self.lock:
            process, self.process, self.ready = self.process, None, False
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            for pipe in (process.stdin, process.stdout):
                pipe.close()

    def close(self):
        self.closed = True
        self.reset()

    def read(self, process, timeout):
        deadline, data = time.monotonic() + timeout, b''
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b'\n' not in data:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError('Local recognition exceeded its time budget.')
                block = os.read(process.stdout.fileno(), 65536)
                if not block:
                    raise RuntimeError('Local recognizer exited.')
                data += block
                if len(data) > 65536:
                    raise RuntimeError('Local recognizer response exceeded its limit.')
        return json.loads(data)

    def ensure_ready(self):
        if self.ready:
            return
        env = {k:v for k,v in os.environ.items() if not k.endswith(('API_KEY', 'TOKEN'))}
        with self.lock:
            if self.closed:
                raise RuntimeError('Local recognizer closed.')
            self.process = process = subprocess.Popen(
                [self.python, '-u', '-m', 'presenter.live_audio', '--child'],
                cwd=Path(__file__).resolve().parent.parent, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        try:
            if self.read(process, self.startup_s) != {'ready': True}:
                raise RuntimeError('Local recognizer could not initialize.')
            with self.lock:
                if self.process is not process or self.closed:
                    raise RuntimeError('Local recognizer was cancelled.')
                self.ready = True
        except Exception:
            self.reset()
            raise

    def recognize(self, pcm):
        process = self.process
        try:
            payload = json.dumps({'pcm': base64.b64encode(pcm).decode()}).encode() + b'\n'
            deadline = time.monotonic()+self.timeout_s
            os.set_blocking(process.stdin.fileno(),False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdin,selectors.EVENT_WRITE)
                view = memoryview(payload)
                while view:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TimeoutError('Local recognition exceeded its time budget.')
                    try:
                        view = view[os.write(process.stdin.fileno(),view):]
                    except BlockingIOError:
                        continue
            return self.read(process, max(0,deadline-time.monotonic()))
        except Exception:
            self.reset()
            raise


class LiveAudio:
    """One active microphone, one decode, one replaceable pending window."""
    def __init__(self, studio, decoder, *, max_age_s=2, clock=time.monotonic):
        self.studio, self.decoder, self.max_age_s, self.clock = studio, decoder, max_age_s, clock
        self.condition = threading.Condition(threading.RLock())
        self.session = None
        self.closed = False
        self.worker = threading.Thread(target=self.run, daemon=True, name='presenter-audio')
        self.worker.start()

    def snapshot(self, pid):
        with self.condition:
            s = self.session
            if not s or s['pid'] != pid:
                return {'status': 'idle'}
            return {k:v for k,v in s.items() if k not in {'pending','rows','pid'}} | {'updates': list(s['rows'])}

    def start(self, pid, generation):
        with self.condition:
            if self.closed:
                raise Conflict('Local audio is shutting down.')
            if self.session and self.session['status'] not in {'stopped','error'}:
                raise Conflict('Stop the current local microphone before starting another.')
            p = self.studio.invalidate_input(pid, generation)
            self.session = {'pid': pid, 'stream_id': secrets.token_hex(16),
                'generation': p['live']['generation'], 'status': 'loading', 'last_seq': -1,
                'received': 0, 'processed': 0, 'dropped': 0, 'rejected': 0, 'timeouts': 0, 'expired': 0,
                'last_seen': self.clock(),
                'pending': None, 'rows': collections.deque(maxlen=120), 'error': None}
            self.condition.notify_all()
            return self.snapshot(pid)

    def bound(self, pid, stream_id, generation=None):
        s = self.session
        if not s or s['pid'] != pid or s['stream_id'] != stream_id:
            raise Conflict('This microphone stream is no longer current.')
        if generation is not None and generation != s['generation']:
            raise Conflict('This audio belongs to an older rehearsal.')
        return s

    def valid(self, s):
        p = self.studio.store.read(s['pid'])
        return p['live']['active'] and p['live']['generation'] == s['generation']

    def submit(self, pid, body):
        with self.condition:
            s = self.bound(pid, body.get('stream_id'), body.get('generation'))
            if body.get('generation') != s['generation']:
                raise Conflict('Include the current microphone generation.')
            if s['status'] not in {'loading','ready','decoding'} or not self.valid(s):
                raise Conflict('Start a new microphone stream for this rehearsal.')
            seq = body.get('seq')
            if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq < 86400:
                raise ValueError('Audio sequence must be an integer between 0 and 86399.')
            if seq <= s['last_seq']:
                raise Conflict('Audio windows must arrive in increasing order.')
            if (isinstance(body.get('end_sample'), bool) or not isinstance(body.get('end_sample'), int)
                    or body.get('end_sample') != (seq+1)*16000):
                raise ValueError('Audio must contain one-second updates at 16 kHz.')
            encoded = body.get('pcm')
            if not isinstance(encoded, str) or len(encoded) > 171000:
                raise ValueError('Send at most four seconds of mono 16-bit PCM.')
            pcm = base64.b64decode(encoded, validate=True)
            if len(pcm) != min((seq+1)*16000,64000)*2:
                raise ValueError('Recognition windows must contain the available past audio, up to four seconds.')
            age = body.get('age_s',0)
            if (isinstance(age,bool) or not isinstance(age,(int,float)) or not math.isfinite(age)
                    or not 0 <= age < self.max_age_s):
                raise ValueError('Captured audio is stale or has an invalid age.')
            if s['pending']:
                s['dropped'] += 1
            s['received'] += 1
            s['last_seen'] = self.clock()
            s['last_seq'] = seq
            s['pending'] = (seq, pcm, self.clock(), age)
            self.condition.notify_all()
            return self.snapshot(pid)

    def stop(self, pid, stream_id):
        with self.condition:
            s = self.bound(pid, stream_id)
            if s['status'] == 'stopped':
                return self.snapshot(pid)
            s['dropped'] += int(s['pending'] is not None)
            s['pending'], s['status'] = None, 'stopped'
            try:
                self.studio.invalidate_input(pid, s['generation'])
            except Conflict:
                pass
            self.condition.notify_all()
            self.decoder.reset()
            return self.snapshot(pid)

    def invalidate(self, pid):
        with self.condition:
            if not self.session or self.session['pid'] != pid:
                return
            stream_id = self.session['stream_id']
        self.stop(pid, stream_id)

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.session and (
                    self.session['status'] == 'loading' or self.session['pending'] is not None), timeout=.5)
                if self.closed:
                    return
                s = self.session
                if not s or s['status'] in {'stopped','error'}:
                    continue
                if s['status'] != 'loading' and self.clock()-s['last_seen'] > 5:
                    self.stop(s['pid'],s['stream_id'])
                    continue
            if not self.decoder.ready:
                try:
                    self.decoder.ensure_ready()
                except Exception:
                    with self.condition:
                        if self.session is s and s['status'] != 'stopped':
                            s.update(status='error', error='Local recognizer unavailable. Check the optional ASR environment.', pending=None)
                    continue
            with self.condition:
                if self.session is not s or s['status'] in {'stopped','error'}:
                    continue
                if s['status'] == 'loading':
                    s['last_seen'] = self.clock()
                s['status'] = 'ready'
                job, s['pending'] = s['pending'], None
                if not job:
                    continue
                seq, pcm, received, age = job
                expires = received+self.max_age_s-age
                if self.clock() > expires or not self.valid(s):
                    s['dropped'] += 1
                    s['expired'] += int(self.clock() > expires)
                    job, pcm = None, b''
                    continue
                s['status'] = 'decoding'
            begun = self.clock()
            try:
                result = self.decoder.recognize(pcm)
                decoded_at = self.clock()
                with self.condition:
                    current = self.session is s and s['status'] != 'stopped' and self.valid(s)
                if not current or decoded_at > expires:
                    with self.condition:
                        s['dropped'] += 1
                        s['expired'] += int(decoded_at > expires)
                        if current:
                            s['status'] = 'ready'
                    continue
                p = self.studio.store.read(s['pid'])
                if result['text'].strip():
                    p = self.studio.transcript(s['pid'], result['text'], None, generation=s['generation'],
                        expires_at=time.time()+expires-decoded_at)
                completed = self.clock()
                with self.condition:
                    if self.session is s and s['status'] != 'stopped' and self.valid(s):
                        s['processed'] += 1
                        s['rejected'] += bool(result.get('rejection'))
                        s['expired'] += int(completed > expires)
                        s['status'] = 'ready'
                        s['rows'].append({'seq': seq, 'text': result['text'], 'rejection': result.get('rejection'),
                            'asr_s': decoded_at-begun, 'received_to_decision_s': completed-received,
                            'capture_age_s':age, 'capture_end_to_decision_estimate_s':completed-received+age,
                            'scene_id': p['live']['current_scene_id'], 'state_version': p['state_version'],
                            'expired': completed > expires})
            except Exception as error:
                with self.condition:
                    if self.session is s and s['status'] != 'stopped':
                        s['dropped'] += 1
                        if isinstance(error, TimeoutError):
                            s['timeouts'] += 1
                            s['status'] = 'loading'
                        elif isinstance(error, Conflict):
                            s['status'] = 'stopped'
                        else:
                            s.update(status='error', error='Local recognition failed. Stop and re-enable the microphone.', pending=None)
            finally:
                job, pcm = None, b''

    def close(self):
        with self.condition:
            if self.closed:
                return
            if self.session and self.session['status'] != 'stopped':
                try:
                    self.studio.invalidate_input(self.session['pid'], self.session['generation'])
                except Conflict:
                    pass
            self.closed = True
            if self.session:
                self.session.update(status='stopped', pending=None)
            self.condition.notify_all()
        self.decoder.close()
        self.worker.join(3)


def child():
    import numpy as np
    import torch
    import whisper
    from .recording import bounded_recognition
    torch.set_num_threads(4)
    model = whisper.load_model('tiny.en', device='cpu')
    bounded_recognition(model, np.zeros(16000,dtype=np.float32), whisper, 48)
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin.buffer:
        if len(line) > 172000:
            raise ValueError('Audio window exceeds limit.')
        pcm = base64.b64decode(json.loads(line)['pcm'], validate=True)
        samples = np.frombuffer(pcm,dtype=np.int16).astype(np.float32)/32768
        result = bounded_recognition(model,samples,whisper,48)
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true',required=True)
    parser.parse_args()
    child()
