export class LocalMicrophone {
  constructor({ api, pid, generation, onProject, onStatus, onError }) {
    Object.assign(this, { api, pid, initialGeneration: generation, onProject, onStatus, onError });
    this.stopped = false; this.generation = null; this.ready = false;
    this.pending = null; this.uploading = false; this.clientSkipped = 0; this.lastFrameSeq = -1;
  }
  path() { return `/api/projects/${this.pid}/audio`; }
  async start() {
    if (this.stopped) return;
    try {
      if (!window.AudioContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Local microphone capture is unavailable in this browser.');
      this.context = new AudioContext({ sampleRate: 16000 });
      await this.context.resume();
      this.media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true }, video: false });
      if (this.stopped) { this.media.getTracks().forEach(track => track.stop()); return; }
      if (this.context.sampleRate !== 16000) throw new Error('This browser cannot capture at 16 kHz. Choose browser speech recognition.');
      this.onStatus('Preparing local speech recognition…');
      const session = await this.api(this.path(), { action: 'start', generation: this.initialGeneration });
      this.streamId = session.stream_id; this.generation = session.generation;
      if (this.stopped) { await this.stopRemote(); return; }
      this.onProject(await this.api(`/api/projects/${this.pid}`));
      const deadline = performance.now() + 35000;
      while (!this.stopped) {
        const state = await this.api(this.path());
        if (state.stream_id !== this.streamId || ['stopped', 'error'].includes(state.status)) throw new Error(state.error || 'Microphone session ended.');
        if (state.status === 'ready') break;
        if (performance.now() > deadline) throw new Error('Local recognition did not become ready in time.');
        await new Promise(resolve => setTimeout(resolve, 150));
      }
      if (this.stopped) return;
      await this.context.audioWorklet.addModule('/pcm-worklet.js');
      if (this.stopped) return;
      this.node = new AudioWorkletNode(this.context, 'presenter-pcm', { numberOfInputs: 1, numberOfOutputs: 1,
        outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit' });
      this.source = this.context.createMediaStreamSource(this.media);
      this.node.port.onmessage = ({ data }) => {
        if (!this.stopped) {
          this.clientSkipped += Math.max(0,data.seq-this.lastFrameSeq-1);
          this.lastFrameSeq = data.seq;
          const age = Math.max(0, this.context.currentTime - data.end_frame / 16000);
          if (age <= 2) {
            if (this.pending) this.clientSkipped++;
            this.pending = { ...data, created: performance.now() - age * 1000 };
            this.drain();
          } else this.clientSkipped++;
          this.node.port.postMessage({ ack: true });
        }
      };
      this.node.onprocessorerror = () => this.fail(new Error('Microphone capture stopped unexpectedly.'));
      this.media.getTracks().forEach(track => { track.onended = () => { if (!this.stopped) this.fail(new Error('Microphone access ended.')); }; });
      this.source.connect(this.node); this.node.connect(this.context.destination);
      this.ready = true;
      this.onStatus('Listening locally · one-second updates · audio stays on this machine.');
      this.statusTimer = setInterval(() => this.refresh(), 750);
    } catch (error) { if (!this.stopped) this.fail(error); }
  }
  async drain() {
    if (this.uploading) return;
    this.uploading = true;
    try {
      while (!this.stopped && this.pending) {
        const packet = this.pending; this.pending = null;
        if (performance.now() - packet.created > 2000) { this.clientSkipped++; continue; }
        const bytes = new Uint8Array(packet.pcm);
        let binary = '';
        for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
        this.uploadAbort = new AbortController();
        const timer = setTimeout(() => this.uploadAbort?.abort(), 2000);
        try {
          await this.api(this.path(), { action: 'chunk', stream_id: this.streamId, generation: this.generation,
            seq: packet.seq, end_sample: packet.end_sample, pcm: btoa(binary),
            age_s: Math.max(0,(performance.now()-packet.created)/1000) }, { signal: this.uploadAbort.signal });
        } finally { clearTimeout(timer); this.uploadAbort = null; }
      }
    } catch (error) { if (!this.stopped) this.fail(error); }
    finally { this.uploading = false; }
  }
  async refresh() {
    if (this.stopped || this.refreshing) return;
    this.refreshing = true;
    try {
      const state = await this.api(this.path());
      if (this.stopped) return;
      if (state.stream_id !== this.streamId || ['error', 'stopped'].includes(state.status)) throw new Error(state.error || 'Local microphone session ended.');
      const last = state.updates.at(-1);
      this.onStatus(`Listening locally · ${last ? `${last.received_to_decision_s.toFixed(2)}s latest processing · ` : ''}${state.dropped + this.clientSkipped} skipped · ${state.timeouts} timeouts`);
    } catch (error) { if (!this.stopped) this.fail(error); }
    finally { this.refreshing = false; }
  }
  fail(error) { this.stop(); this.onError(error.message); }
  async stopRemote() {
    if (!this.streamId) return;
    try { await this.api(this.path(), { action: 'stop', stream_id: this.streamId }); }
    catch { /* Server also expires abandoned streams. */ }
  }
  stop() {
    this.stopped = true; this.ready = false; this.pending = null;
    clearInterval(this.statusTimer); this.uploadAbort?.abort();
    this.node?.port.postMessage({ stop: true });
    this.source?.disconnect(); this.node?.disconnect();
    this.media?.getTracks().forEach(track => track.stop());
    this.context?.close().catch(() => {});
    return this.stopRemote();
  }
}
