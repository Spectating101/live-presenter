import { el, renderScene } from '/visuals.js';
import { LocalMicrophone } from '/microphone.js';

const $ = id => document.getElementById(id);
const bootstrap = new URLSearchParams(location.hash.slice(1));
if (bootstrap.has('access')) {
  sessionStorage.setItem('presenter_access', bootstrap.get('access'));
  history.replaceState(null, '', bootstrap.has('p') ? `/#p=${bootstrap.get('p')}` : '/');
}
let activeId = '', project = null, panel = 'prepare', preparationKey = '', lastRevision = -1;
let recognition = null, micWanted = false, utteranceQueue = [], processingUtterances = false;
let polling = false, utterancePending = false;
let adviserAvailable = false;
let researchAvailable = false, researchKey = '', researchMode = 'public_sources';
let localAudioAvailable = false, localMicrophone = null;

function notify(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { $('toast').hidden = true; }, 7000);
}

async function api(path, body, extra = {}) {
  const options = { ...extra, headers: { 'X-Presenter-Key': sessionStorage.getItem('presenter_access') || '' } };
  if (body !== undefined) Object.assign(options, { method: 'POST', body: JSON.stringify(body), headers: { ...options.headers, 'Content-Type': 'application/json' } });
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The local studio could not complete the request.');
  return result;
}

async function action(name, body) {
  const p = await api(`/api/projects/${activeId}/${name}`, body);
  if (p.id === activeId) accept(p);
  return p;
}

async function refreshLibrary() {
  const { projects } = await api('/api/projects');
  $('project-list').replaceChildren();
  projects.forEach(p => {
    const button = el('button', `project-link${p.id === activeId ? ' selected' : ''}`);
    button.append(el('span', 'project-symbol', p.approved ? '◈' : '◇'), el('span', '', p.title));
    button.addEventListener('click', () => load(p.id).catch(e => notify(e.message)));
    $('project-list').append(button);
  });
}

async function load(id) {
  stopMicrophone();
  activeId = id; project = null; preparationKey = ''; lastRevision = -1;
  location.hash = `p=${id}`;
  accept(await api(`/api/projects/${id}`));
  await refreshLibrary();
}

function accept(p) {
  // A slower load from the previously selected project must never replace the
  // operator's current project or its approval/control context.
  if (p.id !== activeId) return;
  if (project?.id === p.id && (p.state_version || 0) < (project.state_version || 0)) return;
  project = p;
  if (localMicrophone?.ready && localMicrophone.generation !== p.live.generation) stopMicrophone();
  $('welcome').hidden = true; $('project').hidden = false;
  $('breadcrumb').textContent = 'Studio / ' + p.title;
  $('project-title').textContent = p.plan?.title || p.title;
  const busy = p.job.status === 'working';
  $('project-status').textContent = busy ? 'Preparing your story…' : p.approval ? 'Approved · ready to rehearse' : 'Draft · review together';
  $('project-status').className = `pill${p.approval ? ' approved' : ''}`;
  $('open-stage').disabled = !p.approval;
  $('tab-rehearse').disabled = !p.approval;
  $('tab-rehearse').querySelector('.tiny-lock').hidden = !!p.approval;
  $('send-message').disabled = busy || p.live.active;
  $('message').disabled = busy || p.live.active || p.provider === 'outline';
  $('add-material').disabled = busy || p.live.active;
  $('edit-context').disabled = busy || p.live.active;
  $('provider-label').textContent = p.provider === 'copilot' ? 'Conversation · existing Copilot account' : 'Source outline · no AI calls';
  $('send-message').textContent = p.provider === 'outline' ? 'Refresh outline ↗' : 'Discuss ↗';
  $('message').placeholder = p.provider === 'outline' ? 'Source outline is extractive. Edit the brief, add material, or switch to Conversation for discussion.' : '“Focus on why this works. The audience is new to the subject…”';
  const key = `${p.plan_revision}:${p.revision}:${p.messages.length}:${p.job.status}:${!!p.approval}`;
  if (key !== preparationKey) {
    preparationKey = key;
    renderPreparation(p);
  }
  if (lastRevision !== p.revision) { $('reviewed').checked = false; lastRevision = p.revision; }
  $('approve').disabled = !$('reviewed').checked || busy || !!p.plan?.questions.some(q => q.blocking);
  if (!p.approval && panel === 'rehearse') selectPanel('prepare');
  if (p.approval) renderLive(p);
  if (!p.live.active && micWanted) stopMicrophone();
}

function renderPreparation(p) {
  $('materials').replaceChildren();
  p.sources.forEach(source => {
    const details = el('details', 'source-chip');
    details.append(el('summary', '', '▤ ' + source.name));
    const content = el('div', 'source-excerpt');
    content.append(el('strong', '', `${source.units.length} source units · ${source.characters.toLocaleString()} characters`));
    source.units.slice(0, 10).forEach(u => content.append(el('p', '', u.text)));
    details.append(content); $('materials').append(details);
  });
  $('messages').replaceChildren();
  if (!p.messages.length) {
    const message = el('div', 'message assistant');
    message.append(el('span', 'message-label', 'YOUR PREPARATION PARTNER'), el('p', '', 'I’ll read your material, establish the explanation and prepare visual options. We’ll resolve the important questions before anything reaches the stage.'));
    $('messages').append(message);
  }
  p.messages.forEach(m => {
    const message = el('div', 'message ' + m.role);
    message.append(el('span', 'message-label', m.role === 'user' ? 'YOU' : p.provider === 'outline' ? 'SOURCE OUTLINE' : 'PREPARATION PARTNER'));
    m.content.split(/\n+/).forEach(line => message.append(el('p', '', line)));
    $('messages').append(message);
  });
  $('messages').scrollTop = $('messages').scrollHeight;
  $('job-status').hidden = !['working', 'error'].includes(p.job.status);
  $('job-status').className = `job-status ${p.job.status}`;
  $('job-status').replaceChildren();
  if (p.job.status === 'working') {
    $('job-status').append(el('span', 'thinking-dot'), el('span', '', 'Reading, connecting and preparing… This can take a minute or two.'));
  } else if (p.job.status === 'error') {
    const retry = el('button', 'text-button', 'Retry preparation ↗');
    retry.onclick = () => action('chat', { message: '' }).catch(e => notify(e.message));
    $('job-status').append(el('p', '', p.job.error), retry);
  }
  $('approval').hidden = !p.plan || p.job.status !== 'ready' || !!p.approval;
  if (!p.plan) {
    $('plan-content').replaceChildren(el('div', 'empty-plan', 'Your prepared explanation will appear here. We’ll keep the sources within reach.'));
    $('visual-count').textContent = '';
    return;
  }
  const plan = p.plan;
  $('visual-count').textContent = `${plan.concepts.length} ideas · ${plan.scenes.length} visuals`;
  const content = $('plan-content'); content.replaceChildren();
  const intent = el('div', 'intent-card');
  intent.append(el('span', 'eyebrow', 'THE SHARED INTENT'), el('p', 'takeaway', plan.takeaway || p.brief), el('span', 'audience-line', 'For ' + (plan.audience || p.audience)));
  content.append(intent);
  if (plan.questions.length) {
    const questions = el('div', 'questions');
    questions.append(el('h3', '', 'Let’s make this clear'));
    plan.questions.forEach(q => {
      const button = el('button', 'question', q.text + (q.blocking ? ' · Answer before approval' : ''));
      button.addEventListener('click', () => { $('message').value = `About “${q.text}”: `; $('message').focus(); });
      questions.append(button);
    });
    content.append(questions);
  }
  plan.concepts.forEach((concept, index) => {
    const card = el('section', 'concept-card');
    const heading = el('div', 'concept-heading');
    heading.append(el('span', 'concept-number', String(index + 1).padStart(2, '0')), el('h3', '', concept.title));
    card.append(heading, el('p', 'concept-summary', concept.summary));
    const grid = el('div', 'visual-grid');
    plan.scenes.filter(s => s.concept_id === concept.id).forEach(scene => {
      const option = el('div', 'visual-option');
      const button = el('button', 'visual-thumbnail');
      button.setAttribute('aria-label', `Preview ${scene.title} · ${scene.kind}`);
      button.append(renderScene(scene, true));
      button.addEventListener('click', () => { $('full-preview').replaceChildren(renderScene(scene)); $('visual-dialog').showModal(); });
      const isDefault = scene.id === concept.default_scene_id;
      const choose = el('button', 'text-button default-visual', isDefault ? '✓ Default visual' : 'Use as default');
      choose.disabled = isDefault || p.live.active || p.job.status !== 'ready';
      choose.onclick = () => action('default-scene', { scene_id: scene.id }).catch(e => notify(e.message));
      option.append(button,choose); grid.append(option);
    });
    const evidence = el('details', 'source-links');
    evidence.append(el('summary', '', 'View source support'));
    concept.source_refs.forEach(ref => {
      const quote = el('blockquote'); quote.append(el('p', '', ref.quote), el('cite', '', ref.source_name)); evidence.append(quote);
    });
    card.append(grid, evidence); content.append(card);
  });
  content.append(el('p', 'grounding-note', plan.grounding_note));
}

let livePackageKey = '', liveSceneKey = '';
function renderLive(p) {
  const a = p.approval;
  if (livePackageKey !== a.package_hash) {
    livePackageKey = a.package_hash; liveSceneKey = '';
    $('live-library').replaceChildren();
    a.package.scenes.forEach(scene => {
      const button = el('button', 'library-scene');
      button.dataset.sceneId = scene.id;
      button.append(renderScene(scene, true));
      button.setAttribute('aria-label', 'Show ' + scene.title + ' · ' + scene.kind);
      button.onclick = () => action('control', { action: 'show', scene_id: scene.id }).catch(e => notify(e.message));
      $('live-library').append(button);
    });
  }
  const scene = p.live.research_scene || a.package.scenes.find(s => s.id === p.live.current_scene_id);
  if (liveSceneKey !== (scene?.id || 'standby')) {
    liveSceneKey = scene?.id || 'standby';
    if (scene) $('stage-preview').replaceChildren(renderScene(scene));
    else {
      const standby = el('div', 'stage-standby');
      standby.append(el('span', 'brand-mark', '↗'), el('h2', '', 'Ready when you are.'), el('p', '', 'Start the rehearsal to bring your story onto the stage.'));
      $('stage-preview').replaceChildren(standby);
    }
  }
  $('live-library').querySelectorAll('button').forEach(b => b.classList.toggle('current', b.dataset.sceneId === scene?.id));
  $('start').hidden = p.live.active;
  $('stop').disabled = !p.live.active;
  $('hold').disabled = !p.live.active;
  $('back').disabled = !p.live.active;
  $('next').disabled = !p.live.active;
  $('live-library').querySelectorAll('button').forEach(b => { b.disabled = !p.live.active; });
  $('hold').textContent = p.live.locked ? 'Resume following' : 'Hold stage';
  $('hold').classList.toggle('held', p.live.locked);
  $('microphone').disabled = !p.live.active;
  $('submit-utterance').disabled = !p.live.active || utterancePending;
  $('utterance').disabled = !p.live.active;
  $('live-decision').textContent = p.live.decision.reason;
  $('use-adviser').disabled = !adviserAvailable;
  $('use-adviser').checked = !!p.live.adviser_enabled;
  $('use-reflex').checked = !!p.live.reflex_enabled;
  $('adviser-status').textContent = p.live.adviser_enabled && adviserAvailable ? 'Utterances and approved context are sent to Jev.' : 'Prepared content matching · local';
  $('use-research').disabled = !researchAvailable;
  $('use-research').checked = !!p.live.research_enabled;
  $('research-form').hidden = !p.live.research_enabled;
  $('research-disclosure').hidden = !p.live.research_enabled;
  $('research-disclosure').textContent = researchMode === 'connected_agent' ?
    'A connected research agent must be running. It receives the topic and presentation context and can search the broader web.' :
    'Topic context is sent to Jev; supporting material is retrieved from Wikipedia, Wikimedia Commons and Crossref. New results can appear automatically.';
  $('research-query').disabled = !p.live.active || p.live.locked;
  $('research-submit').disabled = !p.live.active || p.live.locked;
  const research = p.live.research || {};
  $('research-status').textContent = p.live.research_enabled ? (research.message || 'Related topics can trigger online research. Queries and topic context are sent to Jev and public source services.') : 'Online research is off.';
  const nextResearchKey = `${p.id}:${research.request_id}:${research.status}:${(research.items || []).map(s => s.id).join(',')}:${p.live.active}`;
  if (nextResearchKey !== researchKey) {
    researchKey = nextResearchKey;
    const results = $('research-results'); results.replaceChildren();
    (research.items || []).forEach(found => {
      const button = el('button', 'library-scene');
      button.disabled = !p.live.active || !p.live.research_enabled;
      button.append(renderScene(found, true));
      button.setAttribute('aria-label', 'Show retrieved source: ' + found.title);
      button.onclick = () => action('control', { action: 'research-show', scene_id: found.id }).catch(e => notify(e.message));
      results.append(button);
    });
    (research.papers || []).forEach(paper => {
      const link = el('a', 'research-paper', paper.title + ' ↗');
      if (/^https:\/\//i.test(paper.url)) { link.href = paper.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
      results.append(link);
    });
  }
  $('live-decision').classList.toggle('held', p.live.locked);
  $('live-transcript').replaceChildren(...p.live.transcript.slice(-25).map(row => el('p', '', row.text)));
}

function selectPanel(name) {
  if (name === 'rehearse' && !project?.approval) return;
  panel = name;
  $('preparation').hidden = name !== 'prepare'; $('rehearsal').hidden = name !== 'rehearse';
  $('tab-prepare').setAttribute('aria-selected', String(name === 'prepare'));
  $('tab-rehearse').setAttribute('aria-selected', String(name === 'rehearse'));
}

async function filePayload(file) {
  if (file.size > 4_000_000) throw new Error(`${file.name} exceeds the 4 MB material limit.`);
  if (/\.(png|jpe?g)$/i.test(file.name) && file.size > 512_000) throw new Error(`Resize ${file.name} to at most 512 KB before attaching it.`);
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return { name: file.name, base64: btoa(binary) };
}

function openCreate() { $('create-dialog').showModal(); }
['new-project', 'welcome-new'].forEach(id => { $(id).onclick = openCreate; });
$('close-create').onclick = () => $('create-dialog').close();
$('new-files').onchange = () => { $('file-names').textContent = [...$('new-files').files].map(f => f.name).join(' · '); };
$('create-form').onsubmit = async event => {
  event.preventDefault(); $('create').disabled = true;
  try {
    const sources = await Promise.all([...$('new-files').files].map(filePayload));
    if ($('new-notes').value.trim()) sources.unshift({ name: 'Presenter notes.md', text: $('new-notes').value });
    const p = await api('/api/projects', { title: $('new-title').value, audience: $('new-audience').value,
      brief: $('new-brief').value, provider: $('new-provider').value, sources });
    $('create-dialog').close(); $('create-form').reset(); await load(p.id); selectPanel('prepare');
  } catch (e) { notify(e.message); }
  finally { $('create').disabled = false; }
};
$('example').onclick = async () => {
  $('example').disabled = true;
  try {
    const example = await api('/api/example');
    const p = await api('/api/projects', { ...example, provider: 'outline' });
    await load(p.id);
    notify('Worked example opened in Source outline mode. Switch the preparation partner to Conversation to discuss and refine it.');
  } catch (e) { notify(e.message); }
  finally { $('example').disabled = false; }
};
$('chat-form').onsubmit = async event => {
  event.preventDefault();
  const message = $('message').value.trim();
  if (!message && project?.provider !== 'outline') return;
  try { await action('chat', { message }); $('message').value = ''; }
  catch (e) { notify(e.message); }
};
$('edit-context').onclick = () => {
  $('context-title').value = project.title; $('context-audience').value = project.audience;
  $('context-brief').value = project.brief; $('context-provider').value = project.provider;
  $('context-dialog').showModal();
};
$('close-context').onclick = () => $('context-dialog').close();
$('context-form').onsubmit = async event => {
  event.preventDefault();
  try {
    await action('context', { title: $('context-title').value, audience: $('context-audience').value,
      brief: $('context-brief').value, provider: $('context-provider').value });
    $('context-dialog').close();
  } catch (e) { notify(e.message); }
};
$('add-material').onclick = () => $('more-files').click();
$('more-files').onchange = async () => {
  try {
    const sources = await Promise.all([...$('more-files').files].map(filePayload));
    if (sources.length) await action('sources', { sources });
  } catch (e) { notify(e.message); }
  $('more-files').value = '';
};
$('reviewed').onchange = () => { $('approve').disabled = !$('reviewed').checked || !!project?.plan?.questions.some(q => q.blocking); };
$('approve').onclick = async () => {
  try { await action('approve', { revision: project.revision, reviewed: $('reviewed').checked }); selectPanel('rehearse'); await refreshLibrary(); }
  catch (e) { notify(e.message); }
};
$('tab-prepare').onclick = () => selectPanel('prepare');
$('tab-rehearse').onclick = () => selectPanel('rehearse');
$('open-stage').onclick = () => window.open(`/stage/${activeId}#access=${project.stage_access}`, '_blank', 'noopener');
$('close-visual').onclick = () => $('visual-dialog').close();
['start', 'stop', 'back', 'next'].forEach(id => { $(id).onclick = () => action('control', { action: id }).catch(e => notify(e.message)); });
$('hold').onclick = () => action('control', { action: project.live.locked ? 'resume' : 'hold' }).catch(e => notify(e.message));
$('use-adviser').onchange = () => action('control', { action: 'adviser', enabled: $('use-adviser').checked }).catch(e => notify(e.message));
$('use-reflex').onchange = () => action('control', { action: 'reflex', enabled: $('use-reflex').checked }).catch(e => notify(e.message));
$('use-research').onchange = () => action('control', { action: 'research', enabled: $('use-research').checked }).catch(e => notify(e.message));
$('research-form').onsubmit = async event => {
  event.preventDefault();
  const query = $('research-query').value.trim();
  if (query) { try { await action('research', { query }); } catch (e) { notify(e.message); } }
};

function sendUtterance(text) {
  return new Promise(resolve => {
    while (utteranceQueue.length >= 2) utteranceQueue.shift().resolve();
    utteranceQueue.push({ text, pid: activeId, generation: project.live.generation, created: performance.now(), resolve });
    drainUtterances();
  });
}
async function drainUtterances() {
  if (processingUtterances) return;
  processingUtterances = true;
  while (utteranceQueue.length) {
    const { text, pid, generation, created, resolve } = utteranceQueue.shift();
    if (pid !== activeId || generation !== project?.live.generation || !project?.live.active || performance.now() - created > 4000) { resolve(); continue; }
    utterancePending = true; renderLive(project);
    try {
      const p = await api(`/api/projects/${pid}/transcript`, { text, seq: project.live.last_seq + 1, final: true, generation });
      if (pid === activeId) accept(p);
    } catch (e) { notify(e.message); }
    finally { utterancePending = false; if (project?.approval) renderLive(project); resolve(); }
  }
  processingUtterances = false;
}
$('utterance-form').onsubmit = async event => {
  event.preventDefault(); const text = $('utterance').value.trim();
  if (!text) return;
  if (localMicrophone) {
    const pid = activeId;
    await stopMicrophone();
    try { const p = await api(`/api/projects/${pid}`); if (pid === activeId) accept(p); else return; }
    catch (e) { notify(e.message); return; }
  }
  $('utterance').value = ''; await sendUtterance(text);
};
function stopMicrophone() {
  micWanted = false;
  const stopped = localMicrophone?.stop(); localMicrophone = null;
  $('microphone-mode').disabled = false;
  recognition?.stop(); recognition = null;
  $('microphone').textContent = '◉ Enable microphone'; $('mic-status').textContent = 'Typed rehearsal is always available.';
  $('interim').textContent = '';
  return stopped;
}
$('microphone').onclick = () => {
  if (micWanted) { stopMicrophone(); return; }
  if ($('microphone-mode').value === 'local') {
    if (!localAudioAvailable) { notify('Start the studio with local speech recognition enabled to use this mode.'); return; }
    micWanted = true;
    $('microphone').textContent = '■ Stop microphone';
    $('microphone-mode').disabled = true;
    localMicrophone = new LocalMicrophone({ api, pid: activeId, generation: project.live.generation,
      onProject: accept, onStatus: message => { $('mic-status').textContent = message; },
      onError: message => { stopMicrophone(); notify(message); } });
    localMicrophone.start();
    return;
  }
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Speech) { notify('This browser does not expose speech recognition. Use Chrome with speech recognition enabled, or the typed rehearsal.'); return; }
  const r = new Speech(); recognition = r; micWanted = true;
  r.continuous = true; r.interimResults = true; r.lang = navigator.language || 'en-US';
  $('microphone').textContent = '■ Stop microphone';
  $('mic-status').textContent = 'Browser speech recognition · your browser may use an online speech service.';
  r.onresult = event => {
    if (!micWanted || recognition !== r || !project?.live.active) return;
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) sendUtterance(event.results[i][0].transcript);
      else interim += event.results[i][0].transcript;
    }
    $('interim').textContent = interim;
  };
  r.onerror = event => { stopMicrophone(); notify('Microphone: ' + event.error + '. Typed rehearsal remains available.'); };
  r.onend = () => { if (micWanted && project?.live.active && recognition === r) { try { r.start(); } catch { stopMicrophone(); } } };
  try { r.start(); } catch (e) { stopMicrophone(); notify(e.message); }
};

async function poll() {
  if (!activeId || polling) return;
  polling = true;
  const id = activeId;
  try { const p = await api(`/api/projects/${id}`); if (id === activeId) accept(p); }
  catch { /* Retain the visible draft if the local server is temporarily unavailable. */ }
  finally { polling = false; }
}
try {
  const status = await api('/api/status');
  adviserAvailable = status.live_adviser === 'jev';
  researchAvailable = !!status.live_research;
  researchMode = status.research_mode || 'public_sources';
  localAudioAvailable = !!status.local_audio;
  $('local-microphone-option').disabled = !localAudioAvailable;
  if (localAudioAvailable) $('microphone-mode').value = 'local';
  if (!status.conversation_available) $('new-provider').value = 'outline';
  await refreshLibrary();
  const match = location.hash.match(/^#p=([a-f0-9]{32})$/);
  if (match) await load(match[1]);
} catch (e) { notify(e.message); }
setInterval(poll, 1000);
window.addEventListener('beforeunload', stopMicrophone);
