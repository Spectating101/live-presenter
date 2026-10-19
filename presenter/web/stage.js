import { renderScene, el } from '/visuals.js';
const root = document.getElementById('projector-stage');
const fullscreenButton = document.getElementById('projector-fullscreen');
const fullscreenStatus = document.getElementById('projector-fullscreen-status');
function fullscreenChanged() {
  root.dataset.fullscreen = document.fullscreenElement ? 'active' : 'windowed';
  fullscreenButton.textContent = document.fullscreenElement ? 'Exit full screen' : 'Full screen';
}
async function toggleFullscreen() {
  root.dataset.fullscreenAttempts = String(Number(root.dataset.fullscreenAttempts || 0) + 1);
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
    delete root.dataset.fullscreenError;
    fullscreenStatus.textContent = '';
    fullscreenChanged();
  } catch (error) {
    root.dataset.fullscreen = 'unavailable';
    root.dataset.fullscreenError = error.name;
    fullscreenStatus.textContent = 'Full screen is unavailable here. Use your browser’s full screen command.';
  }
}
fullscreenButton.addEventListener('click', toggleFullscreen);
document.addEventListener('fullscreenchange', fullscreenChanged);
fullscreenChanged();
const pid = location.pathname.split('/').filter(Boolean)[1];
const bootstrap = new URLSearchParams(location.hash.slice(1));
if (bootstrap.has('access')) {
  sessionStorage.setItem('presenter_stage_' + pid, bootstrap.get('access'));
  history.replaceState(null, '', location.pathname);
}
let current = '', packageHash = '', cache = new Map(), lastVersion = -1;
let renderSamples = [];

async function update() {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(pid)}/stage?after=${lastVersion}`, { headers: { 'X-Presenter-Key': sessionStorage.getItem('presenter_stage_' + pid) || '' } });
    if (!response.ok) throw new Error('Projector connection unavailable.');
    const state = await response.json();
    const receivedAt = performance.now();
    const receivedEpochMs = Date.now();
    if ((state.state_version || 0) < lastVersion) return;
    const initialPacket = lastVersion < 0;
    lastVersion = state.state_version || 0;
    document.title = `${state.title} · Projector`;
    root.dataset.reflex = String(!!state.reflex_enabled);
    if (packageHash !== state.package_hash) {
      cache = new Map(state.scenes.map(scene => [scene.id, renderScene(scene)]));
      packageHash = state.package_hash;
      current = '';
    }
    if (state.scene && !cache.has(state.scene.id)) cache.set(state.scene.id, renderScene(state.scene));
    const preparedIds = new Set(state.scenes.map(scene => scene.id));
    while (cache.size > preparedIds.size + 8) {
      const old = [...cache.keys()].find(id => !preparedIds.has(id) && id !== state.scene?.id);
      if (!old) break;
      cache.delete(old);
    }
    const key = `${state.package_hash || ''}:${state.scene?.id || ''}`;
    if (current === key) return;
    current = key;
    const replace = () => {
      if (state.scene) root.replaceChildren(cache.get(state.scene.id).cloneNode(true));
      else {
        const standby = el('div', 'stage-standby');
        standby.append(el('span', 'brand-mark', '↗'), el('h1', '', state.title), el('p', '', 'Ready when you are.'));
        root.replaceChildren(standby);
      }
      performance.clearMeasures('presenter-stage-dom');
      performance.measure('presenter-stage-dom', { start: receivedAt, end: performance.now() });
      const sample = {state_version: state.state_version, scene_id: state.scene?.id || null,
        initial_packet: initialPacket,
        received_epoch_ms: receivedEpochMs, dom_epoch_ms: Date.now(),
        dom_ms: performance.now() - receivedAt, frame_opportunity_ms: null,
        visibility: document.visibilityState, focused: document.hasFocus()};
      renderSamples.push(sample); renderSamples = renderSamples.slice(-48);
      // Bounded DOM-backed diagnostics for browser verification, without
      // exposing preparation text, transcript, capabilities or provider keys.
      root.dataset.renderSamples = JSON.stringify(renderSamples);
      // A scheduling opportunity, not proof of physical display/paint latency.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (current !== key) return;
        performance.clearMeasures('presenter-stage-frame-opportunity');
        performance.measure('presenter-stage-frame-opportunity', { start: receivedAt, end: performance.now() });
        sample.frame_opportunity_ms = performance.now() - receivedAt;
        sample.frame_epoch_ms = Date.now();
        sample.frame_visibility = document.visibilityState;
        root.dataset.renderSamples = JSON.stringify(renderSamples);
      }));
    };
    if (!state.reflex_enabled && document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) document.startViewTransition(replace);
    else replace();
  } catch {
    // Keep the last approved visual and retry a dropped long poll.
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}
root.addEventListener('dblclick', toggleFullscreen);
while (true) await update();
