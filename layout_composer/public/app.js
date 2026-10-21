const state = { presets: [], library: [], preset: null, placements: {}, selected: null };
const $ = (id) => document.getElementById(id);
const icons = { 'kpi-chart': 'images/kpi.png', 'bar-chart': 'images/bar.png', 'line-chart': 'images/line.png', table: 'images/table.png' };
const iconFor = (el) => (icons[el.kind] ? `<img src="${icons[el.kind]}" alt="" onerror="this.style.display='none'">` : '');

async function getJson(url, options) {
  const res = await fetch(url, options);
  const body = await res.json();
  if (!res.ok) {
    const err = new Error(typeof body.error === 'string' ? body.error : JSON.stringify(body.error));
    err.status = res.status;
    throw err;
  }
  return body;
}

function setStatus(text, isError) {
  $('status').textContent = text;
  $('status').classList.toggle('error', !!isError);
}

function renderPresets() {
  $('presets').innerHTML = '';
  state.presets.forEach((p) => {
    const b = document.createElement('button');
    b.textContent = p.name;
    b.className = p.id === state.preset.id ? 'active' : '';
    b.onclick = () => {
      state.preset = p;
      state.placements = {};
      render();
    };
    $('presets').appendChild(b);
  });
}

function renderLibrary() {
  const used = new Set(Object.values(state.placements));
  $('library').innerHTML = '';
  state.library.forEach((el) => {
    const card = document.createElement('div');
    card.className = 'card' + (used.has(el.id) ? ' used' : '') + (state.selected === el.id ? ' selected' : '');
    card.draggable = true;
    card.innerHTML = `${iconFor(el)}<div>${el.name}<small>${el.kind.replace('-chart', '')}</small></div>`;
    card.ondragstart = (e) => e.dataTransfer.setData('text/plain', el.id);
    card.onclick = () => {
      state.selected = state.selected === el.id ? null : el.id;
      renderLibrary();
    };
    $('library').appendChild(card);
  });
}

function place(zoneIndex, elementId) {
  // An element can only appear once; moving it clears its previous zone.
  Object.keys(state.placements).forEach((z) => {
    if (state.placements[z] === elementId) delete state.placements[z];
  });
  state.placements[zoneIndex] = elementId;
  state.selected = null;
  render();
}

function renderCanvas() {
  $('canvas').innerHTML = '';
  state.preset.zones.forEach(([c1, c2, r1, r2], i) => {
    const zone = document.createElement('div');
    const elementId = state.placements[i];
    const el = state.library.find((e) => e.id === elementId);
    zone.className = 'zone' + (el ? ' filled' : '');
    zone.style.gridColumn = `${c1} / ${c2}`;
    zone.style.gridRow = `${r1} / ${r2}`;
    zone.innerHTML = el ? `${iconFor(el)}<span>${el.name}</span>` : `Zone ${i + 1}`;
    if (el) {
      const x = document.createElement('button');
      x.className = 'remove';
      x.textContent = 'x';
      x.title = 'Remove';
      x.onclick = (e) => {
        e.stopPropagation();
        delete state.placements[i];
        render();
      };
      zone.appendChild(x);
    }
    zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('over'); };
    zone.ondragleave = () => zone.classList.remove('over');
    zone.ondrop = (e) => {
      e.preventDefault();
      place(i, e.dataTransfer.getData('text/plain'));
    };
    zone.onclick = () => state.selected && place(i, state.selected);
    $('canvas').appendChild(zone);
  });
}

function render() {
  renderPresets();
  renderLibrary();
  renderCanvas();
}

function showView(name) {
  $('compose').hidden = name !== 'compose';
  $('result').hidden = name !== 'result';
}

async function loadPreview(savedWorkbookId) {
  try {
    const query = savedWorkbookId ? `?workbookId=${encodeURIComponent(savedWorkbookId)}` : '';
    const { url, workbookUrl } = await getJson(`/api/embed-url${query}`);
    $('saveBar').hidden = false;
    $('saveControls').hidden = !!savedWorkbookId;
    if (url) {
      $('previewFrame').src = url;
      $('previewFrame').hidden = false;
      $('previewMessage').hidden = true;
    } else {
      $('previewFrame').hidden = true;
      $('previewMessage').hidden = false;
      $('previewMessage').innerHTML = `Embed settings are not configured, so the preview cannot load here. <a href="${workbookUrl}" target="_blank" rel="noopener">Open the generated workbook in Sigma</a>.`;
    }
  } catch (e) {
    $('saveBar').hidden = true;
    $('previewFrame').hidden = true;
    $('previewMessage').hidden = false;
    $('previewMessage').textContent = e.message;
  }
}

async function save() {
  if (!$('saveName').value.trim()) {
    $('saveStatus').textContent = 'Enter a name for the workbook.';
    $('saveStatus').classList.add('error');
    return;
  }
  $('save').disabled = true;
  $('saveStatus').textContent = 'Saving...';
  $('saveStatus').classList.remove('error');
  try {
    const r = await getJson('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: $('saveName').value }),
    });
    $('saveStatus').textContent = `Saved as "${r.name}".`;
    $('saveName').value = '';
    await loadSaved(r);
  } catch (e) {
    $('saveStatus').textContent = e.message;
    $('saveStatus').classList.add('error');
  } finally {
    $('save').disabled = false;
  }
}

async function loadSaved(justSaved) {
  try {
    const saved = await getJson('/api/saved');
    // Sigma's file list can lag a moment behind a fresh copy.
    if (justSaved && !saved.some((w) => w.workbookId === justSaved.workbookId)) saved.unshift(justSaved);
    const select = $('savedSelect');
    select.innerHTML = '<option value="" selected>Saved workbooks</option>';
    saved.forEach((w) => {
      const o = document.createElement('option');
      o.value = w.workbookId;
      o.textContent = w.name;
      select.appendChild(o);
    });
    $('savedGroup').hidden = saved.length === 0;
  } catch (e) {
    $('savedGroup').hidden = true;
  }
}

async function generate() {
  if (!Object.keys(state.placements).length) return setStatus('Place at least one element first.', true);
  $('generate').disabled = true;
  setStatus('Generating workbook...');
  try {
    const r = await getJson('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presetId: state.preset.id, placements: state.placements }),
    });
    setStatus(r.created ? 'Workbook created.' : 'Workbook updated.');
    $('saveStatus').textContent = '';
    $('saveName').value = '';
    $('savedSelect').value = '';
    showView('result');
    await loadPreview();
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    $('generate').disabled = false;
  }
}

$('savedSelect').onchange = async (e) => {
  if (!e.target.value) return;
  $('saveStatus').textContent = '';
  showView('result');
  await loadPreview(e.target.value);
};
$('back').onclick = () => showView('compose');
$('save').onclick = save;
$('generate').onclick = generate;
$('clear').onclick = () => { state.placements = {}; setStatus(''); render(); };

(async () => {
  try {
    [state.presets, state.library] = await Promise.all([getJson('/api/presets'), getJson('/api/library')]);
    state.preset = state.presets[0];
    render();
    loadSaved();
  } catch (e) {
    setStatus(e.message, true);
  }
})();
