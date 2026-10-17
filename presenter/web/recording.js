// Bundled with the app's scene renderer into a private local comparison file.
const recording = JSON.parse(document.getElementById('recording-data').textContent);
const audio = document.getElementById('audio');
const referenceVideo = document.getElementById('reference-video');
const modeSelect = document.getElementById('mode');
const reportStage = document.getElementById('replay-stage');
let shownScene = '';
function timestamp(seconds) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
function activeRecording() { return recording.results[modeSelect.value]; }
function seekTo(seconds) { audio.currentTime = seconds; updateRecording(); }
function updateRecording() {
  const result = activeRecording(), at = audio.currentTime;
  const event = result.events.filter(e => e.at <= at).at(-1);
  const row = result.rows.filter(r => r.decision_completed_at <= at).at(-1);
  const scene = result.package.scenes.find(s => s.id === event?.scene_id);
  const key = result.package_hash + ':' + scene?.id;
  if (key !== shownScene) {
    shownScene = key;
    reportStage.replaceChildren(scene ? renderScene(scene) : el('p', '', 'Waiting for the opening visual.'));
  }
  const chapter = recording.reference.spans.find(s => s.start <= at && s.end > at);
  document.getElementById('chapter').textContent = chapter ? `${chapter.label} · ${chapter.original_visual}` : 'Reference outside the scored argument sections.';
  document.getElementById('heard').textContent = row ? `${timestamp(row.window_start ?? row.start)}–${timestamp(row.end)}: ${row.text || '(no recognized speech)'}` : 'No audio chunk has completed recognition yet.';
  document.getElementById('decision').textContent = row ? `${row.decision.action} · ${row.decision.reason}` : 'Approved opening visual.';
  if (referenceVideo.readyState && Math.abs(referenceVideo.currentTime - at) > .35) referenceVideo.currentTime = Math.min(at, referenceVideo.duration || at);
}
function drawRecordingSummary() {
  const mode = modeSelect.value, result = activeRecording(), metrics = recording.metrics[mode];
  document.getElementById('summary').textContent = `${result.rows.length} audio chunks · ${metrics.visual_changes_during_audio} visual changes · ${metrics.ideas_displayed_during_audio}/${metrics.prepared_ideas} prepared ideas displayed`;
  const changes = document.getElementById('changes'); changes.replaceChildren();
  result.events.forEach(event => {
    const scene = result.package.scenes.find(s => s.id === event.scene_id);
    const button = el('button', '', `${timestamp(event.at)} · ${scene.title} · ${scene.kind}`);
    button.onclick = () => seekTo(event.at + .05); changes.append(button);
  });
  const table = el('table');
  const header = el('tr');
  ['Coarse argument section', 'Local alignment', 'Jev-assisted alignment'].forEach(v => header.append(el('th', '', v)));
  table.append(header);
  metrics.chapters.forEach((chapter, i) => {
    const row = el('tr');
    row.append(el('td', '', chapter.label));
    ['local', 'jev'].forEach(m => row.append(el('td', '', `${(100 * recording.metrics[m].chapters[i].fraction).toFixed(1)}%`)));
    table.append(row);
  });
  const total = el('tr'); total.append(el('th', '', 'Time-weighted alignment within scored sections'));
  ['local', 'jev'].forEach(m => total.append(el('th', '', `${(100 * recording.metrics[m].development_chapter_alignment).toFixed(1)}%`)));
  table.append(total);
  const latency = el('tr'); latency.append(el('td', '', 'Chunk end → decision, median / p95'));
  ['local', 'jev'].forEach(m => {
    const stats = recording.metrics[m]; latency.append(el('td', '', `${stats.chunk_end_to_decision_p50_s.toFixed(2)}s / ${stats.chunk_end_to_decision_p95_s.toFixed(2)}s`));
  });
  table.append(latency);
  const worst = el('tr'); worst.append(el('td', '', 'Chunk end → decision, maximum'));
  ['local','jev'].forEach(m => {
    const value = recording.metrics[m].chunk_end_to_decision_max_s;
    worst.append(el('td', '', value == null ? 'Not recorded' : `${value.toFixed(2)}s`));
  });
  table.append(worst);
  const skipped = el('tr'); skipped.append(el('td', '', 'Stale windows skipped / processed outputs rejected'));
  ['local','jev'].forEach(m => {
    const stats = recording.metrics[m];
    skipped.append(el('td', '', `${stats.dropped_windows || 0} / ${stats.rejected_windows || 0}`));
  });
  table.append(skipped);
  const mistakes = el('tr'); mistakes.append(el('td', '', 'Visual changes outside coarse section expectations'));
  ['local','jev'].forEach(m => mistakes.append(el('td', '', recording.metrics[m].misaligned_changes_within_scored_sections?.length || 0)));
  table.append(mistakes);
  const calls = el('tr'); calls.append(el('td', '', 'Adviser calls / unavailable calls'));
  ['local','jev'].forEach(m => calls.append(el('td', '', `${recording.metrics[m].adviser_calls} / ${recording.metrics[m].adviser_failures}`)));
  table.append(calls);
  document.getElementById('metrics').replaceChildren(table, el('p', 'metric-note', `Alignment excludes ${recording.reference.boundary_exclusion_s} seconds on each side of coarse chapter boundaries. This reference is not independent and does not score visual quality. Processing times exclude waiting for a ${result.asr.chunk_s}-second chunk to fill.`));
  updateRecording();
}
recording.reference.spans.forEach(span => {
  const button = el('button', '', `${timestamp(span.start)} · ${span.label}`);
  button.onclick = () => seekTo(span.start); document.getElementById('chapters').append(button);
});
activeRecording().limitations.forEach(text => document.getElementById('limitations').append(el('li', '', text)));
modeSelect.onchange = drawRecordingSummary;
audio.addEventListener('timeupdate', updateRecording);
audio.addEventListener('seeking', updateRecording);
audio.addEventListener('play', () => { updateRecording(); referenceVideo.play().catch(() => {}); });
audio.addEventListener('pause', () => referenceVideo.pause());
audio.addEventListener('ratechange', () => { referenceVideo.playbackRate = audio.playbackRate; });
referenceVideo.addEventListener('loadedmetadata', updateRecording);
drawRecordingSummary();
