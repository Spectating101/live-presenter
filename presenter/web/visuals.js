export function el(tag, className = '', value = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== '') node.textContent = value;
  return node;
}

const labels = { definition: 'THE IDEA', flow: 'HOW IT WORKS', comparison: 'A CLOSER LOOK', metric: 'BY THE NUMBERS', chart: 'THE MEASUREMENTS', evidence: 'THE SOURCE', image: 'THE VISUAL', annotated_image: 'A CLOSER LOOK' };

export function renderScene(scene, compact = false) {
  const root = el('article', `scene kind-${scene.kind}${compact ? ' compact' : ''}`);
  root.dataset.sceneId = scene.id;
  root.dataset.objectId = scene.object_id;
  const head = el('div', 'scene-header');
  const displayTitle = scene.web_source && scene.kind === 'image' ? scene.title.replace(/\.(svg|png|jpe?g)$/i, '').replaceAll('_', ' ') : scene.title;
  head.append(el('span', 'scene-kicker', scene.web_source ? (scene.web_source.presenter_reviewed ? 'RESEARCHED SOURCE' : 'RETRIEVED ONLINE') : labels[scene.kind]), el('h2', '', displayTitle));
  root.append(head);
  const content = el('div', 'scene-content');
  if (scene.kind === 'flow') {
    const flow = el('div', 'flow-grid');
    scene.nodes.forEach((text, i) => {
      const step = el('div', 'flow-step');
      step.append(el('span', 'step-number', String(i + 1).padStart(2, '0')), el('p', '', text));
      flow.append(step);
    });
    content.append(flow);
  } else if (scene.kind === 'comparison') {
    const columns = el('div', 'comparison-grid');
    scene.columns.forEach(column => {
      const card = el('section', 'comparison-column');
      card.append(el('h3', '', column.label));
      const list = el('ul');
      column.items.forEach(item => list.append(el('li', '', item)));
      card.append(list); columns.append(card);
    });
    content.append(columns);
  } else if (scene.kind === 'metric') {
    content.append(el('div', 'metric-value', scene.value), el('p', 'metric-label', scene.label));
  } else if (scene.kind === 'chart') {
    content.append(chart(scene));
  } else if (scene.kind === 'annotated_image') {
    content.append(annotatedImage(scene));
  } else if (scene.kind === 'image') {
    const picture = el('img', 'supplied-image');
    picture.alt = scene.asset.alt;
    picture.width = scene.asset.width;
    picture.height = scene.asset.height;
    picture.decoding = 'async';
    picture.src = scene.asset.data_url;
    content.append(picture);
  } else if (scene.kind === 'evidence') {
    scene.source_refs.slice(0, 2).forEach(ref => {
      const quote = el('blockquote');
      quote.append(el('p', '', ref.quote.length > 580 ? ref.quote.slice(0, 580) + '…' : ref.quote), el('cite', '', ref.source_name));
      content.append(quote);
    });
  } else {
    const points = scene.body?.length ? scene.body : [scene.source_refs[0]?.quote || ''];
    points.forEach((point, i) => content.append(el('p', i === 0 ? 'lead-point' : 'support-point', point)));
  }
  root.append(content);
  const footer = el('footer', 'scene-footer');
  const names = [...new Set(scene.source_refs.map(r => r.source_name))];
  if (scene.web_source) {
    const credit = el('div', 'web-credit');
    const link = el('a', '', scene.web_source.provider + ' · source ↗');
    if (/^https:\/\//i.test(scene.web_source.url)) { link.href = scene.web_source.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    credit.append(link, el('span', '', scene.web_source.presenter_reviewed ? 'Researched online · reviewed during preparation' : 'Retrieved live · not presenter-reviewed'));
    if (scene.web_source.image_url) {
      const imageCredit = el('a', '', `${scene.web_source.artist || 'Wikimedia Commons'} · ${scene.web_source.image_license}`);
      if (/^https:\/\//i.test(scene.web_source.image_url)) { imageCredit.href = scene.web_source.image_url; imageCredit.target = '_blank'; imageCredit.rel = 'noopener noreferrer'; }
      credit.append(imageCredit);
    }
    footer.append(credit, el('span', 'scene-mark', '↗'));
  } else footer.append(el('span', '', names.join(' · ') + (scene.data_note ? ' · ' + scene.data_note : '')), el('span', 'scene-mark', '↗'));
  root.append(footer);
  return root;
}

function annotatedImage(scene) {
  const canvas = el('figure', 'annotation-canvas');
  canvas.style.setProperty('--image-ratio', scene.asset.width / scene.asset.height);
  const picture = el('img', 'annotation-image');
  picture.src = scene.asset.data_url;
  picture.alt = scene.asset.alt;
  picture.width = scene.asset.width; picture.height = scene.asset.height;
  canvas.append(picture);
  const ns = 'http://www.w3.org/2000/svg';
  const overlay = document.createElementNS(ns, 'svg');
  overlay.setAttribute('viewBox', '0 0 1000 1000');
  overlay.setAttribute('preserveAspectRatio', 'none');
  overlay.setAttribute('aria-hidden', 'true');
  overlay.classList.add('attention-overlay');
  scene.annotations.forEach(target => {
    const group = document.createElementNS(ns, 'g');
    group.dataset.attentionId = target.id;
    const line = document.createElementNS(ns, 'line');
    Object.entries({x1: target.x * 1000, y1: target.y * 1000,
      x2: target.label_x * 1000, y2: target.label_y * 1000}).forEach(([key,value]) => line.setAttribute(key, value));
    line.classList.add('attention-leader');
    const ring = document.createElementNS(ns, 'ellipse');
    Object.entries({cx: target.x * 1000, cy: target.y * 1000, rx: 14,
      ry: 14 * scene.asset.width / scene.asset.height}).forEach(([key,value]) => ring.setAttribute(key, value));
    ring.classList.add('attention-ring');
    group.append(line,ring); overlay.append(group);
  });
  canvas.append(overlay);
  scene.annotations.forEach(target => {
    const label = el('span', 'attention-label', target.label);
    label.dataset.attentionId = target.id;
    // Label placement is reviewed with the image. The bounded label width
    // and clamped position keep text inside the image at narrow viewports.
    label.style.left = `clamp(4.5rem, ${target.label_x * 100}%, calc(100% - 4.5rem))`;
    label.style.top = `clamp(1.5rem, ${target.label_y * 100}%, calc(100% - 1.5rem))`;
    canvas.append(label);
  });
  attentionResize?.observe(canvas);
  return canvas;
}

function alignLabels(canvas) {
  const frame = canvas.getBoundingClientRect();
  if (!frame.width || !frame.height) return;
  canvas.querySelectorAll('.attention-label:not([hidden])').forEach(label => {
    const box = label.getBoundingClientRect();
    const line = canvas.querySelector(`g[data-attention-id="${label.dataset.attentionId}"] line`);
    line.setAttribute('x2', ((box.left + box.width / 2 - frame.left) / frame.width) * 1000);
    line.setAttribute('y2', ((box.top + box.height / 2 - frame.top) / frame.height) * 1000);
  });
}

const attentionResize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(entries => {
  entries.forEach(({target}) => {
    if (target.isConnected) alignLabels(target);
    else attentionResize.unobserve(target);
  });
});

export function applyAttention(container, scene, attention) {
  if (!scene || scene.kind !== 'annotated_image') return;
  const active = attention?.scene_id === scene.id &&
    scene.annotations.some(target => target.id === attention.annotation_id) ? attention.annotation_id : '';
  const illustration = container.querySelector('.annotation-canvas');
  if (!illustration) return;
  illustration.dataset.attention = active;
  illustration.querySelectorAll('[data-attention-id]').forEach(node => {
    node.dataset.focused = String(node.dataset.attentionId === active);
    if (node.classList.contains('attention-label')) node.hidden = node.dataset.attentionId !== active;
  });
  alignLabels(illustration);
  attentionResize?.observe(illustration);
}

function chart(scene) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 900 420');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${scene.y} by ${scene.x}: ${scene.data.map(d => `${d.label} ${d.value}`).join(', ')}`);
  function shape(tag, attrs, text) {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text !== undefined) n.textContent = String(text);
    svg.append(n); return n;
  }
  const min = Math.min(0, ...scene.data.map(d => d.value));
  const max = Math.max(0, ...scene.data.map(d => d.value));
  const range = max - min || 1;
  const y = n => 340 - ((n - min) / range) * 270;
  const count = scene.data.length;
  const band = 780 / Math.max(count, 1);
  shape('text', { x: 45, y: 22, fill: '#65746d', 'font-size': 18 }, scene.y.replaceAll('_', ' '));
  for (let i = 0; i <= 3; i++) {
    const value = min + range * i / 3;
    shape('line', { x1: 70, x2: 855, y1: y(value), y2: y(value), stroke: '#dce3dc', 'stroke-width': 1 });
    shape('text', { x: 58, y: y(value) + 5, 'text-anchor': 'end', fill: '#738077', 'font-size': 15 }, Number(value.toFixed(1)));
  }
  scene.data.forEach((d, i) => {
    const x = 75 + band * i + band * .18;
    const baseline = y(0), top = Math.min(y(d.value), baseline);
    shape('rect', { x, y: top, width: Math.max(2, band * .64), height: Math.max(1, Math.abs(baseline - y(d.value))), rx: 6, fill: i % 2 ? '#b1cdbb' : '#2d6657' });
    shape('text', { x: x + band * .32, y: d.value >= 0 ? top - 12 : baseline + Math.abs(baseline - y(d.value)) + 22,
      'text-anchor': 'middle', fill: '#173a30', 'font-size': count > 12 ? 11 : 22, 'font-weight': 600 }, d.value);
    shape('text', { x: x + band * .32, y: 377, 'text-anchor': 'middle', fill: '#4a5f55', 'font-size': count > 12 ? 10 : 18 }, d.label.slice(0, count > 12 ? 8 : 20));
  });
  return svg;
}
