import { renderScene, el } from '/visuals.js';
const root = document.getElementById('projector-stage');
const pid = location.pathname.split('/').filter(Boolean)[1];
const bootstrap = new URLSearchParams(location.hash.slice(1));
if (bootstrap.has('access')) {
  sessionStorage.setItem('presenter_stage_' + pid, bootstrap.get('access'));
  history.replaceState(null, '', location.pathname);
}
let current = '', packageHash = '', cache = new Map(), lastVersion = -1;

async function update() {
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(pid)}/stage?after=${lastVersion}`, { headers: { 'X-Presenter-Key': sessionStorage.getItem('presenter_stage_' + pid) || '' } });
    if (!response.ok) throw new Error('Projector connection unavailable.');
    const state = await response.json();
    const receivedAt = performance.now();
    if ((state.state_version || 0) < lastVersion) return;
    lastVersion = state.state_version || 0;
    document.title = `${state.title} · Projector`;
    root.dataset.reflex = String(!!state.reflex_enabled);
    if (packageHash !== state.package_hash) {
      cache = new Map(state.scenes.map(scene => [scene.id, renderScene(scene)]));
      packageHash = state.package_hash;
      current = '';
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
      // A scheduling opportunity, not proof of physical display/paint latency.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (current !== key) return;
        performance.clearMeasures('presenter-stage-frame-opportunity');
        performance.measure('presenter-stage-frame-opportunity', { start: receivedAt, end: performance.now() });
      }));
    };
    if (!state.reflex_enabled && document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) document.startViewTransition(replace);
    else replace();
  } catch {
    // Keep the last approved visual and retry a dropped long poll.
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}
root.addEventListener('dblclick', () => document.documentElement.requestFullscreen?.());
while (true) await update();
