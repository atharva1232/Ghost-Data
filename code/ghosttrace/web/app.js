'use strict';
const $ = id => document.getElementById(id);
const state = {workspaces: [], runs: [], data: null, selected: null, ai: false, evaluation: null};
const statuses = ['COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE', 'REVIEW_REQUIRED'];
const labels = {COMPLETE: 'Complete', INCOMPLETE: 'Incomplete', NOT_APPLICABLE: 'Not applicable', REVIEW_REQUIRED: 'Needs review'};
let toastTimer;

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) value.textContent = String(text);
  if (className) value.className = className;
  return value;
}
function badge(status) { return node('span', labels[status] || status, 'badge ' + status); }
function empty(text) { return node('div', text, 'empty'); }
function toast(text, error = false) {
  $('toast').textContent = text;
  $('toast').className = 'toast' + (error ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 8500 : 4000);
}
async function api(path, body) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request failed.');
  return result;
}
async function action(button, task, busyText) {
  const original = button.textContent;
  button.disabled = true;
  button.classList.add('busy');
  button.textContent = busyText;
  try { await task(); }
  catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.classList.remove('busy'); button.textContent = original; }
}
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + name));
  document.querySelectorAll('.nav').forEach(v => v.classList.toggle('active', v.dataset.view === name));
  $('page-title').textContent = {overview: 'Overview', requests: 'Audit requests', evidence: 'Evidence sources', evaluation: 'Evaluation'}[name];
  window.scrollTo({top: 0, behavior: 'smooth'});
}
function currentWorkspace() { return state.workspaces.find(w => w.id === $('workspace').value); }
function updateContext() {
  const workspace = currentWorkspace();
  const isDemo = workspace?.demo;
  $('mode-badge').textContent = isDemo ? 'Synthetic demo' : 'Organizer / uploaded data';
  $('mode-badge').className = 'pill ' + (isDemo ? 'demo' : 'real');
  const count = workspace?.requests ?? 0;
  const available = (workspace?.readiness || []).filter(r => r.available).length;
  $('workspace-description').textContent = `${count} requests · ${available}/6 evidence files available` + (isDemo ? ' · Fictional examples only' : '');
  renderReadiness();
}
function renderReadiness() {
  const rows = currentWorkspace()?.readiness || [];
  $('readiness-count').textContent = rows.filter(r => r.available).length + ' / ' + rows.length + ' AVAILABLE';
  $('readiness').replaceChildren();
  for (const row of rows) {
    const line = node('div', undefined, 'source-row');
    const name = node('span', undefined, 'source-name');
    name.append(node('span', '▤', 'file-icon'), node('span', row.filename));
    line.append(name, node('span', row.available ? 'Available' : 'Missing', row.available ? 'available' : 'missing'));
    $('readiness').append(line);
  }
  const table = makeTable(['File', 'Purpose', 'Status'], rows.map(row => [node('code', row.filename), row.role,
    node('span', row.available ? 'Available' : 'Missing', row.available ? 'available' : 'missing')]));
  $('evidence-table').replaceChildren(table);
}
function makeTable(headers, rows) {
  const wrap = node('div', undefined, 'table-wrap'), table = node('table', undefined, 'data-table');
  const head = node('thead'), headRow = node('tr');
  headers.forEach(title => headRow.append(node('th', title)));
  head.append(headRow); table.append(head);
  const body = node('tbody');
  rows.forEach(values => {
    const row = node('tr');
    values.forEach(value => { const cell = node('td'); cell.append(value instanceof Node ? value : node('span', value)); row.append(cell); });
    body.append(row);
  });
  table.append(body); wrap.append(table); return wrap;
}
function metric(label, value, description, className, symbol = '◎') {
  const card = node('div', undefined, 'metric ' + className), top = node('div', undefined, 'metric-top');
  top.append(node('div', label, 'metric-label'), node('span', symbol, 'metric-icon'));
  card.append(top, node('div', value, 'metric-number'), node('div', description, 'metric-description'));
  return card;
}
function renderOverview() {
  const data = state.data, total = data?.results.length ?? 0, counts = data?.summary.counts || {};
  $('nav-count').textContent = String(total);
  $('metrics').replaceChildren(
    metric('Requests investigated', total || '—', data?.summary.demo ? 'Synthetic demo cases' : 'In this audit run', '', '☷'),
    metric('Policy failures', data ? data.summary.findings : '—', 'Residual data or missing retention', 'red', '◇'),
    metric('Recreation paths', data ? data.summary.recreation_paths : '—', 'Active, unblocked writers', 'amber', '↗'),
    metric('Verified complete', counts.COMPLETE || (data ? 0 : '—'), 'All required evidence checks passed', 'green', '✓')
  );
  $('total-pill').textContent = data ? total + ' requests' : 'No run yet';
  $('outcomes').replaceChildren();
  if (!data) $('outcomes').append(empty('Run an audit to see its verdicts.'));
  else for (const status of statuses) {
    const row = node('div', undefined, 'outcome-row'), line = node('div', undefined, 'outcome-line');
    const name = node('span', undefined, 'outcome-name');
    name.append(node('span', undefined, 'status-dot dot-' + status), node('span', labels[status]));
    line.append(name, node('strong', counts[status] || 0));
    const track = node('div', undefined, 'bar-track'), bar = node('div', undefined, 'bar ' + status);
    bar.style.width = ((counts[status] || 0) / (total || 1) * 100) + '%';
    track.append(bar); row.append(line, track); $('outcomes').append(row);
  }
  const notice = $('overview-notice');
  notice.classList.toggle('hidden', !data);
  if (data) notice.textContent = data.summary.demo
    ? 'Synthetic demonstration. These cases show the audit workflow; their findings and accuracy do not describe the organizer dataset.'
    : `${counts.REVIEW_REQUIRED || 0} requests need more evidence or intent review. This is a provisional internal report; the official competition schema is still required.`;
  $('fingerprints').replaceChildren();
  if (!data) $('fingerprints').append(empty('Run an audit to fingerprint its inputs.'));
  else for (const file of data.summary.inputs) {
    const line = node('div', undefined, 'fingerprint');
    line.append(node('strong', file.file), node('span', ' · ' + file.bytes.toLocaleString() + ' bytes', 'mini-label'), node('code', file.sha256));
    $('fingerprints').append(line);
  }
  document.querySelectorAll('[data-download]').forEach(b => { b.disabled = !data; });
}
function renderHistory() {
  $('history').replaceChildren();
  if (!state.runs.length) { $('history').append(empty('Your completed audit runs will be saved here.')); return; }
  for (const run of state.runs.slice(0, 8)) {
    const line = node('div', undefined, 'history-row'), left = node('div'), right = node('div', undefined, 'history-right');
    const name = state.workspaces.find(w => w.id === run.workspace)?.name || 'Saved investigation';
    left.append(node('div', name, 'history-title'), node('div', new Date(run.created_at).toLocaleString() + ' · ' + run.id.slice(0, 8), 'history-meta'));
    const open = node('button', 'Open →', 'text-button');
    open.onclick = () => action(open, () => loadRun(run.id), 'Opening…');
    right.append(node('span', run.summary.requests + ' requests', 'history-count'), node('span', run.summary.demo ? 'Demo' : 'Audit', 'pill'), open);
    line.append(left, right); $('history').append(line);
  }
}
function resetEvaluation() {
  state.evaluation = null;
  $('evaluation-output').replaceChildren(empty('Run evaluation to compare this audit with its reference labels.'));
  const ws = currentWorkspace();
  $('eval-note').textContent = ws?.demo
    ? 'Synthetic evaluation only. The demo reference labels exercise expected behavior and do not establish accuracy on organizer data.'
    : ws?.has_labels ? 'Reference labels are available. Evaluation is separate from prediction.' : 'No reference labels supplied. Include expected.csv with case_id,status in an uploaded workspace to evaluate.';
}
async function refreshWorkspaces(selected) {
  const data = await api('/api/workspaces');
  state.workspaces = data.workspaces; state.ai = data.ai_available;
  const previous = selected || $('workspace').value;
  $('workspace').replaceChildren(...state.workspaces.map(w => { const option = node('option', w.name); option.value = w.id; return option; }));
  if (state.workspaces.some(w => w.id === previous)) $('workspace').value = previous;
  updateContext();
}
async function refreshRuns() {
  state.runs = (await api('/api/runs')).runs;
  renderHistory();
}
function setData(data) {
  state.data = data; state.selected = data.results[0]?.case_id || null;
  $('workspace').value = data.run.workspace;
  $('search').value = ''; $('status-filter').value = '';
  updateContext(); renderOverview(); renderRequests(); resetEvaluation();
}
async function loadRun(id) { setData(await api('/api/runs/' + id)); }
async function runAudit() {
  const workspace = $('workspace').value;
  if (!workspace) throw new Error('Choose a dataset first.');
  const data = await api('/api/audit', {workspace});
  setData(data); await refreshRuns();
  toast(`Audit complete: ${data.results.length} requests investigated.`);
}
function renderRequests() {
  const all = state.data?.results || [], query = $('search').value.trim().toLowerCase(), status = $('status-filter').value;
  const rows = all.filter(r => (!status || r.status === status) &&
    [r.case_id, r.request?.email || '', ...r.identifiers.map(i => i.value)].some(value => String(value).toLowerCase().includes(query)));
  if (!rows.some(r => r.case_id === state.selected)) state.selected = rows[0]?.case_id || null;
  $('request-count').textContent = rows.length + ' OF ' + all.length;
  $('request-list').replaceChildren();
  if (!rows.length) $('request-list').append(empty(all.length ? 'No matching requests.' : 'Run an audit first.'));
  for (const result of rows) {
    const card = node('button', undefined, 'request-card' + (state.selected === result.case_id ? ' selected' : ''));
    const top = node('div', undefined, 'request-card-head');
    top.append(node('strong', result.case_id), badge(result.status));
    card.append(top, node('p', result.request?.email || result.intent.replaceAll('_', ' ')));
    card.onclick = () => { state.selected = result.case_id; renderRequests(); };
    $('request-list').append(card);
  }
  renderDetail(rows.find(r => r.case_id === state.selected));
}
function detailSection(title, items, renderer) {
  const section = node('div', undefined, 'detail-section'), heading = node('h3', title);
  heading.append(node('span', items.length, 'section-count')); section.append(heading);
  if (!items.length) section.append(node('div', 'No items recorded.', 'evidence-description'));
  else for (const item of items) section.append(renderer(item));
  $('detail').append(section);
}
function source(item) { return node('code', item.source + (item.policy ? ' · policy: ' + item.policy : ''), 'source-reference'); }
function evidenceItem(item, className = '') {
  const div = node('div', undefined, 'evidence-item ' + className);
  div.append(node('strong', item.description));
  if (item.record_id) div.append(node('div', item.system + ' / ' + item.record_id, 'evidence-description'));
  if (item.forbidden_fields?.length) div.append(node('div', 'Forbidden fields: ' + item.forbidden_fields.join(', '), 'evidence-description'));
  if (item.source) div.append(source(item));
  return div;
}
function renderDetail(result) {
  $('detail').replaceChildren();
  if (!result) { $('detail').append(empty('Select a request from an audit run.')); return; }
  const top = node('div', undefined, 'detail-top');
  top.append(node('h2', result.case_id), badge(result.status));
  $('detail').append(top, node('p', 'Reported: ' + result.reported_status + ' · Intent: ' + result.intent.replaceAll('_', ' '), 'detail-sub'));
  if (result.request) {
    const request = node('div', undefined, 'evidence-item');
    request.append(node('strong', result.request.email), node('div', result.request.text, 'evidence-description'),
      node('div', 'Requested: ' + result.request.requested_at + ' · Audit: ' + result.request.audit_at, 'source-reference'),
      source({source: result.request_source}));
    $('detail').append(request);
  }
  detailSection('Evidence gaps', result.gaps, gap => evidenceItem({description: gap}, 'gap'));
  const identifiers = node('div', undefined, 'identifier-list');
  result.identifiers.forEach(item => identifiers.append(node('span', item.type + ': ' + item.value, 'identifier')));
  detailSection('Identity trail', result.identifiers.length ? [identifiers] : [], x => x);
  detailSection('Policy failures & residual data', result.findings, item => evidenceItem(item, 'risk'));
  detailSection('Recreation paths', result.recreation_paths, item => evidenceItem({description: item.process_id + ': ' + item.from + ' → ' + item.to, source: item.source}, 'risk'));
  detailSection('Ordered remediation', result.remediation, item => {
    const row = node('div', undefined, 'step'), body = node('div', undefined, 'step-body');
    body.append(node('span', item.action), source(item)); row.append(node('span', item.step, 'step-number'), body); return row;
  });
  detailSection('Required retained records', result.retained_records, item => node('div', item, 'identifier'));
  detailSection('Proof checks', result.proof, item => evidenceItem(item));
  detailSection('Observed timeline', result.timeline, item => {
    const row = node('div', undefined, 'timeline-row'), body = node('div');
    body.append(node('div', item.description, 'timeline-description'), source(item));
    row.append(node('span', item.at.replace('T', '\n').replace('Z', ''), 'timeline-date'), body); return row;
  });
  const ai = node('div', undefined, 'ai-section');
  ai.append(node('h3', 'AI second look'), node('p', state.ai
    ? 'Optional advisory review sends minimized findings to OpenAI. The evidence verdict stays unchanged.'
    : 'Set OPENAI_API_KEY before launching the app to enable advisory review. Offline auditing works without a key.'));
  if (state.ai) {
    const controls = node('div', undefined, 'ai-controls'), model = node('input'), button = node('button', 'Review case ↗', 'button primary');
    model.placeholder = 'Structured-output-capable model ID'; model.setAttribute('aria-label', 'AI model ID');
    const response = node('div', undefined, 'ai-response');
    button.onclick = () => action(button, async () => {
      if (!model.value.trim()) throw new Error('Enter the OpenAI model ID to use.');
      const review = await api('/api/review', {run_id: state.data.run.id, case_id: result.case_id, model: model.value.trim()});
      response.replaceChildren(node('div', review.summary));
      review.checks.forEach(check => response.append(evidenceItem({description: check.observation, source: check.source})));
    }, 'Reviewing…');
    controls.append(model, button); ai.append(controls, response);
  }
  $('detail').append(ai);
}
async function evaluateRun() {
  if (!state.data) throw new Error('Run an audit first.');
  const result = await api('/api/evaluate', {run_id: state.data.run.id});
  state.evaluation = result;
  const cards = node('div', undefined, 'metrics');
  cards.append(metric('Status accuracy', (result.accuracy_including_abstentions * 100).toFixed(1) + '%', 'Abstentions count as incorrect', 'green'),
    metric('Labeled requests', result.labeled_cases, result.demo ? 'Synthetic cases only' : 'Supplied reference cases', ''),
    metric('False complete', result.false_complete, 'Predicted complete but reference disagrees', 'red'),
    metric('Abstentions', result.abstentions, 'Requests needing more evidence', 'amber'));
  const panel = node('section', undefined, 'panel evaluation-panel'), heading = node('div', undefined, 'panel-heading');
  heading.append(node('h2', 'Confusion matrix'), node('span', result.demo ? 'SYNTHETIC EVALUATION' : 'REFERENCE EVALUATION', 'mini-label'));
  panel.append(heading, makeTable(['Reference', 'Prediction', 'Requests'], result.confusion_matrix.map(row => [badge(row.expected), badge(row.predicted), row.count])));
  const mismatches = node('section', undefined, 'panel evaluation-panel'), mismatchHeading = node('div', undefined, 'panel-heading');
  mismatchHeading.append(node('h2', 'Mismatches')); mismatches.append(mismatchHeading);
  mismatches.append(result.failures.length ? makeTable(['Case', 'Reference', 'Prediction'], result.failures.map(row => [row.case_id, badge(row.expected), badge(row.predicted)])) : empty('No status mismatches in the labeled cases.'));
  $('evaluation-output').replaceChildren(cards, panel, mismatches);
  toast('Evaluation complete. Labels stayed separate from prediction.');
}
function openUpload() { $('upload-error').textContent = ''; $('upload-dialog').showModal(); }
async function uploadFiles(event) {
  event.preventDefault();
  await action($('upload-submit'), async () => {
    const files = [...$('upload-files').files];
    if (!files.length) throw new Error('Choose your evidence files first.');
    if (files.reduce((sum, f) => sum + f.size, 0) > 16 * 1024 * 1024) throw new Error('The total upload limit is 16 MB.');
    const encoded = await Promise.all(files.map(file => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('Could not read ' + file.name));
      reader.onload = () => resolve({name: file.name.toLowerCase().endsWith('.csv') ? file.name : 'media/' + file.name, content: reader.result.split(',')[1]});
      reader.readAsDataURL(file);
    })));
    try {
      const result = await api('/api/upload', {name: $('upload-name').value || 'Uploaded evidence', synthetic: $('upload-synthetic').checked, files: encoded});
      await refreshWorkspaces(result.id);
      state.data = null; state.selected = null; renderOverview(); renderRequests(); resetEvaluation();
      $('upload-dialog').close(); showView('overview'); toast('Workspace created. Run an audit to investigate it.');
    } catch (error) { $('upload-error').textContent = error.message; throw error; }
  }, 'Validating files…');
}

document.querySelectorAll('.nav').forEach(button => button.onclick = () => showView(button.dataset.view));
$('see-requests').onclick = () => showView('requests');
$('run-audit').onclick = () => action($('run-audit'), runAudit, 'Investigating…');
$('evaluate').onclick = () => action($('evaluate'), evaluateRun, 'Evaluating…');
$('workspace').onchange = () => { state.data = null; state.selected = null; updateContext(); renderOverview(); renderRequests(); resetEvaluation(); };
$('search').oninput = renderRequests; $('status-filter').onchange = renderRequests;
$('upload-open').onclick = openUpload; $('evidence-upload').onclick = openUpload;
$('upload-close').onclick = () => $('upload-dialog').close(); $('upload-form').onsubmit = uploadFiles;
$('upload-files').onchange = () => $('upload-file-list').replaceChildren(...[...$('upload-files').files].map(f => node('div', f.name + ' · ' + (f.size / 1024).toFixed(1) + ' KB')));
document.querySelectorAll('[data-download]').forEach(button => button.onclick = () => {
  if (!state.data) return;
  const link = node('a'); link.href = '/api/runs/' + state.data.run.id + '/download?format=' + button.dataset.download;
  link.download = ''; document.body.append(link); link.click(); link.remove();
});
(async () => {
  try {
    await refreshWorkspaces('demo'); await refreshRuns();
    renderOverview(); renderRequests(); resetEvaluation();
    if (state.runs.length) await loadRun(state.runs[0].id);
  } catch (error) { toast('Could not load the workspace: ' + error.message, true); }
})();
