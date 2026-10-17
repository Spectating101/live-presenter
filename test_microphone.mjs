// Unit tests for capture framing and cancellation. These are not browser tests.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function worklet() {
  let Processor;
  const context = vm.createContext({ Float32Array, ArrayBuffer, DataView, Math, currentFrame: 0,
    AudioWorkletProcessor: class { constructor() { this.port = { posted: [], postMessage(packet) { this.posted.push(packet); } }; } },
    registerProcessor(name, value) { assert.equal(name, 'presenter-pcm'); Processor = value; } });
  vm.runInContext(readFileSync('presenter/web/pcm-worklet.js', 'utf8'), context);
  const processor = new Processor();
  function second(value) {
    for (let at = 0; at < 16000; at += 128) {
      const input = new Float32Array(Math.min(128,16000-at)).fill(value);
      processor.process([[input]]); context.currentFrame += input.length;
    }
  }
  return { processor, second };
}

test('worklet emits one-second updates with only the available four seconds of past PCM', () => {
  const { processor:p, second } = worklet();
  for (let i = 1; i <= 5; i++) {
    second(i / 10);
    const packet = p.port.posted.at(-1);
    assert.equal(packet.seq, i-1); assert.equal(packet.end_sample, i*16000);
    assert.equal(packet.end_frame, i*16000);
    assert.equal(packet.pcm.byteLength, Math.min(i,4)*32000);
    const view = new DataView(packet.pcm);
    assert.ok(Math.abs(view.getInt16(0,true)-Math.round(Math.max(1,i-3)/10*32767)) <= 1);
    assert.ok(Math.abs(view.getInt16(packet.pcm.byteLength-2,true)-Math.round(i/10*32767)) <= 1);
    p.port.onmessage({ data: { ack:true } });
  }
});

test('paused main thread retains a single pending window and stop releases it', () => {
  const { processor:p, second } = worklet();
  for (let i = 0; i < 7; i++) second(.2);
  assert.equal(p.port.posted.length,1);
  p.port.onmessage({ data: { ack:true } });
  assert.equal(p.port.posted.length,2);
  assert.equal(p.port.posted[1].seq,6);
  second(.3);
  p.port.onmessage({ data: { stop:true } });
  p.port.onmessage({ data: { ack:true } });
  assert.equal(p.port.posted.length,2);
  assert.equal(p.process([[new Float32Array(128)]]),false);
  assert.ok(p.ring.every(v => v===0));
});

function captureHarness(apiOverride, mediaPromise) {
  let closes = 0, trackStops = 0;
  const calls = [], nodes = [], errors = [];
  const media = { getTracks: () => [{ stop() { trackStops++; } }] };
  const context = vm.createContext({
    window: { AudioContext: true }, navigator: { mediaDevices: { getUserMedia: () => mediaPromise || Promise.resolve(media) } },
    AudioContext: class { constructor() { this.sampleRate = 16000; this.currentTime = 0; this.audioWorklet = { addModule: async () => {} }; }
      resume() { return Promise.resolve(); } close() { closes++; return Promise.resolve(); }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; } },
    AudioWorkletNode: class { constructor() { this.port = { postMessage() {} }; nodes.push(this); } connect() {} disconnect() {} },
    performance, setInterval, clearInterval, setTimeout, clearTimeout, AbortController, Uint8Array, Math,
    btoa: value => Buffer.from(value, 'binary').toString('base64'),
  });
  vm.runInContext(readFileSync('presenter/web/microphone.js','utf8').replace('export class','class')+
    '\nglobalThis.Capture = LocalMicrophone;', context);
  const api = async (path,body) => {
    calls.push(body || { action:'get' });
    if (apiOverride) {
      const value = await apiOverride(path,body);
      if (value !== undefined) return value;
    }
    if (body?.action === 'start') return { stream_id:'stream', generation:'new' };
    return { stream_id:'stream', status:'ready', updates:[], dropped:0, timeouts:0 };
  };
  const capture = new context.Capture({ api,pid:'project',generation:'old',onProject() {},onStatus() {},onError: error => errors.push(error) });
  return { capture,calls,nodes,errors,media,stats: () => ({ closes,trackStops }) };
}

test('stopping during a pending microphone permission request releases tracks without starting a stream', async () => {
  let resolve;
  const h = captureHarness(null, new Promise(r => { resolve=r; }));
  const starting = h.capture.start();
  await new Promise(r => setImmediate(r));
  h.capture.stop(); resolve(h.media); await starting;
  assert.deepEqual(h.stats(), { closes:1,trackStops:1 });
  assert.equal(h.calls.length,0);
});

test('denied microphone permission closes the audio context and never opens a server stream', async () => {
  const h=captureHarness(null,Promise.reject(new Error('Microphone permission denied')));
  await h.capture.start();
  assert.deepEqual(h.stats(),{ closes:1,trackStops:0 });
  assert.deepEqual(h.errors,['Microphone permission denied']);
  assert.equal(h.calls.length,0);
  assert.equal(h.capture.stopped,true);
});

test('late stream-start response is stopped after cancellation', async () => {
  let resolve;
  const h = captureHarness((path,body) => body?.action==='start' ? new Promise(r => { resolve=r; }) : undefined);
  const starting=h.capture.start();
  await new Promise(r => setImmediate(r));
  h.capture.stop(); resolve({ stream_id:'late',generation:'new' }); await starting;
  assert.ok(h.calls.some(body => body.action==='stop' && body.stream_id==='late'));
  assert.equal(h.nodes.length,0);
});

test('uploads coalesce to the latest pending packet and stale captured audio is discarded', async () => {
  let resolveFirst;
  const h = captureHarness((path,body) => body?.action==='chunk' && body.seq===0 ? new Promise(r => { resolveFirst=r; }) : undefined);
  try {
    await h.capture.start();
    const packet = seq => ({ seq,end_sample:(seq+1)*16000,end_frame:(seq+1)*16000,pcm:new ArrayBuffer(32000) });
    for (let seq=0; seq<3; seq++) h.nodes[0].port.onmessage({ data:packet(seq) });
    resolveFirst({ status:'ready' });
    await new Promise(r => setImmediate(r));
    assert.deepEqual(h.calls.filter(b => b.action==='chunk').map(b => b.seq),[0,2]);
    h.capture.context.currentTime=10;
    h.nodes[0].port.onmessage({ data:packet(3) });
    assert.equal(h.calls.filter(b => b.action==='chunk').length,2);
    assert.equal(h.capture.clientSkipped,2);
    assert.deepEqual(h.errors,[]);
  } finally { await h.capture.stop(); }
});
