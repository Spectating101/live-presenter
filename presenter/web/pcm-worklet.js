// AudioContext supplies mono 16 kHz audio. No microphone samples go to output.
class PresenterPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ring = new Float32Array(64000);
    this.count = 0;
    this.waiting = false;
    this.pending = null;
    this.active = true;
    this.port.onmessage = ({ data }) => {
      if (data.stop) { this.active = false; this.pending = null; this.ring.fill(0); }
      if (data.ack) { this.waiting = false; this.flush(); }
    };
  }
  flush() {
    if (!this.active || this.waiting || !this.pending) return;
    const packet = this.pending; this.pending = null; this.waiting = true;
    this.port.postMessage(packet, [packet.pcm]);
  }
  process(inputs) {
    if (!this.active) return false;
    const mono = inputs[0]?.[0];
    if (!mono) return true;
    for (let i = 0; i < mono.length; i++) {
      this.ring[this.count % 64000] = mono[i];
      this.count++;
      if (this.count % 16000) continue;
      const size = Math.min(this.count, 64000), pcm = new ArrayBuffer(size * 2), view = new DataView(pcm);
      for (let j = 0; j < size; j++) {
        const value = Math.max(-1, Math.min(1, this.ring[(this.count - size + j) % 64000]));
        view.setInt16(j * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
      }
      // While the main thread is busy, replace the pending window in-place.
      this.pending = { seq: this.count / 16000 - 1, end_sample: this.count,
        end_frame: currentFrame + i + 1, pcm };
      this.flush();
    }
    return true;
  }
}
registerProcessor('presenter-pcm', PresenterPCM);
