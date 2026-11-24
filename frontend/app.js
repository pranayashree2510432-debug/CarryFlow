const $ = s => document.querySelector(s);
let selected = 'facts';
let cachedState = null;
let browserMode = 'iframe';
const browser = $('#browser');
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(path, body = {}, method = 'POST') {
  const r = await fetch('/api/' + path, {
    method: method,
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    const err = await r.text();
    alert('Operation error: ' + err);
    throw Error(err);
  }
  return r.json();
}

async function load() {
  const s = await (await fetch('/api/state')).json();
  cachedState = s;
  render(s);
}

function getActiveFact(facts, conflicts, factId) {
  const resolved = (conflicts || []).find(c => c.fact_id === factId && c.resolved);
  if (resolved && resolved.resolution_version) {
    const match = facts.find(f => f.id === factId && f.version === resolved.resolution_version);
    if (match) return match;
  }
  const nonSup = (facts || []).filter(f => f.id === factId && f.verification !== 'SUPERSEDED');
  if (nonSup.length) {
    return nonSup.sort((a, b) => b.version - a.version)[0];
  }
  return (facts || []).filter(f => f.id === factId).sort((a, b) => b.version - a.version)[0];
}

function render(s) {
  const facts = s.facts || [];
  const rec = s.receipts || [];
  const actions = s.actions || [];
  const events = s.events || [];
  const conflicts = s.conflicts || [];

  const uniqueFactIds = [...new Set(facts.map(x => x.id))];
  const activeFacts = uniqueFactIds.map(id => getActiveFact(facts, conflicts, id)).filter(Boolean);
  $('#fact-count').textContent = activeFacts.length;
  $('#receipt-count').textContent = rec.length;
  $('#workflow-id').textContent = s.meta?.workflow_id ? 'Passport · ' + s.meta.workflow_id.slice(0, 8) : 'Workflow not started';

  const pCtrl = $('#passport-controls');
  if (pCtrl) pCtrl.style.display = selected === 'facts' ? 'flex' : 'none';

  const recovered = events.some(e => e.title === 'Page inspected before resume');
  const portalA = rec.some(r => r.origin.endsWith('/portal/a'));
  const portalB = rec.some(r => r.origin.endsWith('/portal/b'));
  const profile = events.some(e => e.title === 'Profile facts verified');
  const steps = [
    ['Goal captured', Boolean(s.meta?.user_goal)],
    ['Profile facts verified', profile],
    ['Portal A prepared', portalA],
    ['Portal B prepared', portalB],
    [recovered ? 'Recovery reconciled' : 'Recovery checkpoint', recovered]
  ];
  $('#timeline').innerHTML = steps.map(([label, done], i) =>
    `<div class="tl-item ${done ? 'done' : ''}"><strong>${label}</strong>${i === 4 ? '<small>' + esc(recovered ? 'RECONCILED' : s.meta?.status || 'PENDING') + '</small>' : ''}</div>`
  ).join('');
  $('#progress-count').textContent = `${steps.filter(x => x[1]).length} / 5`;

  $('#inspector').innerHTML = selected === 'facts' ? renderFacts(facts, conflicts) : selected === 'receipts' ? renderReceipts(rec) : renderActions(actions);
  $('#conflict-box').innerHTML = renderConflicts(s, facts);
}

function renderFacts(facts, conflicts) {
  const ids = [...new Set(facts.map(f => f.id))];
  const activeList = ids.map(id => getActiveFact(facts, conflicts, id)).filter(Boolean);
  if (!activeList.length) return '<div class="empty">Your personal data passport is empty. Add a fact or start the demo to initialize.</div>';

  return activeList.map(f => {
    let origins = [];
    try { origins = JSON.parse(f.permitted_origins || '[]'); } catch { origins = []; }
    const originsFormatted = origins.map(o => o.replace(/https?:\/\//, '')).join(', ') || 'None';
    const isConfirmed = Boolean(f.user_confirmed);
    const isConflict = f.verification === 'UNVERIFIED_CONFLICT';
    const statusClass = isConflict ? 'conflict' : isConfirmed ? '' : 'unconfirmed';
    const statusText = isConflict ? '⚡ Conflict' : isConfirmed ? '✓ Confirmed' : '⚠ Unconfirmed';

    return `<div class="fact" data-fact-id="${esc(f.id)}">
      <div class="fact-top">
        <b>${esc(f.source_label || f.id)}</b>
        <span class="status ${statusClass}">${statusText}</span>
      </div>
      <div class="fact-value">${esc(f.value)}</div>
      <div class="fact-provenance">
        <span>Source: <b>${esc(f.source_url.split('/').pop() || f.source_url)}</b> · v${f.version}</span><br>
        <span>Added: ${esc(f.collected_at ? f.collected_at.slice(0, 16).replace('T', ' ') : 'N/A')}</span> · 
        <span>Confirmed: ${esc(f.last_confirmed_at ? f.last_confirmed_at.slice(0, 16).replace('T', ' ') : 'Pending')}</span>
      </div>
      <div class="fact-perms">Sharing: <b>${esc(originsFormatted)}</b></div>
      <div class="fact-actions">
        ${!isConfirmed ? `<button type="button" class="tiny-btn confirm" onclick="confirmFact('${esc(f.id)}', ${f.version})">Confirm</button>` : ''}
        <button type="button" class="tiny-btn" onclick="openEditFactModal('${esc(f.id)}')">Edit</button>
        <button type="button" class="tiny-btn" onclick="openPermissionsModal('${esc(f.id)}')">Sharing</button>
      </div>
    </div>`;
  }).join('');
}

const CANONICAL_MAP = {
  'person.name': 'full_name',
  'person.email': 'email',
  'person.phone': 'phone',
  'education.degree': 'degree',
  'education.graduation_year': 'graduation_year',
  'skills.technical': 'skills',
  'address.current': 'current_address',
  'address.permanent': 'permanent_address'
};

function renderReceipts(rs) {
  if (!rs.length) return '<div class="empty">Prepare a portal to create inspectable handoff receipts.</div>';
  return rs.map(r => {
    const canon = CANONICAL_MAP[r.semantic_type] || (r.mapping_type === 'AMBIGUOUS' ? 'unresolved (ambiguous)' : r.mapping_type === 'UNCONFIRMED_FACT' ? 'unconfirmed profile fact' : 'unmapped');
    return `<div class="receipt">
      <div class="receipt-title"><span>${esc(r.source_field || 'Unresolved source')} → ${esc(r.destination_field.replaceAll('_', ' '))}</span><span class="status ${r.status === 'WAITING_FOR_USER' ? 'conflict' : ''}">${esc(r.status)}</span></div>
      <p>${esc(r.reason)}</p>
      <div class="receipt-meta"><span><b>Canonical:</b> ${esc(canon)}</span> · <span>${esc(r.mapping_type)}</span> · <span>confidence ${Math.round(r.confidence * 100)}%</span> · <span>permission ${esc(r.permission)}</span></div>
    </div>`;
  }).join('');
}

function renderActions(as) {
  if (!as.length) return '<div class="empty">No action has run. Prepared and verified actions will appear here.</div>';
  return as.map(a =>
    `<div class="receipt">
      <div class="receipt-title"><span>${esc(a.action_type.replaceAll('_', ' '))}</span><span class="status ${a.status === 'UNCERTAIN' ? 'conflict' : ''}">${esc(a.status)}</span></div>
      <p>${esc(a.observed_result)}</p>
      <div class="receipt-meta">${esc(a.origin.split('/').pop())} · ${esc(a.verification)}</div>
    </div>`
  ).join('');
}

function renderConflicts(s, facts) {
  const unresolved = (s.conflicts || []).filter(c => !c.resolved);
  if (!unresolved.length) return '';
  return unresolved.map(c => {
    const old = facts.find(f => f.id === c.fact_id && f.version === c.old_version);
    const n = facts.find(f => f.id === c.fact_id && f.version === c.new_version);
    const label = n?.source_label || old?.source_label || c.fact_id.replaceAll('_', ' ');
    return `<div class="conflict-card" data-fact="${esc(c.fact_id)}">
      <h3>⚠ Conflicting ${esc(label)} values</h3>
      <p>v${c.old_version}: ${esc(old?.value)} · ${esc(old?.source_label || 'Original')} (${esc(old?.verification || 'SAVED')})</p>
      <p>v${c.new_version}: ${esc(n?.value)} · ${esc(n?.source_label || 'Incoming')} · ${esc(n?.verification || 'UNVERIFIED')}</p>
      <button type="button" onclick="resolve('${esc(c.fact_id)}', ${c.old_version})">Keep v${c.old_version}</button>
      <button type="button" onclick="resolve('${esc(c.fact_id)}', ${c.new_version})">Use v${c.new_version}</button>
    </div>`;
  }).join('');
}

async function resolve(fact_id, version) {
  await api('resolve', {fact_id, version});
  await load();
}
window.resolve = resolve;

async function confirmFact(fact_id, version) {
  await api('passport/fact/' + fact_id + '/confirm', {version});
  await load();
}
window.confirmFact = confirmFact;

function closeFactModal() {
  const m = $('#fact-modal');
  m.style.display = 'none';
  m.innerHTML = '';
}
window.closeFactModal = closeFactModal;

function openAddFactModal() {
  const m = $('#fact-modal');
  m.style.display = 'block';
  m.innerHTML = `
    <h3>Add Profile Fact to Passport</h3>
    <label>Field Type</label>
    <select id="modal-fact-id">
      <option value="full_name">Full Name (person.name)</option>
      <option value="email">Email Address (person.email)</option>
      <option value="phone">Phone Number (person.phone)</option>
      <option value="degree">Academic Degree (education.degree)</option>
      <option value="graduation_year">Graduation Year (education.graduation_year)</option>
      <option value="skills">Technical Skills (skills.technical)</option>
      <option value="current_address">Current Address (address.current)</option>
      <option value="permanent_address">Permanent Address (address.permanent)</option>
      <option value="custom">Custom Field...</option>
    </select>
    <div id="custom-fields-group" style="display:none;margin-top:6px;">
      <label>Custom Field Identifier</label>
      <input type="text" id="modal-custom-id" placeholder="e.g. portfolio_url">
      <label>Custom Label</label>
      <input type="text" id="modal-custom-label" placeholder="e.g. Portfolio Website">
    </div>
    <label>Value</label>
    <input type="text" id="modal-fact-val" placeholder="Enter fact value">
    <label>Sharing Permissions</label>
    <div style="font-size:10px;margin-top:4px;">
      <label style="display:inline;font-size:10px;"><input type="checkbox" id="perm-portal-a" checked style="width:auto;"> Allow 127.0.0.1:8000 (Northstar / Summit)</label>
    </div>
    <div style="font-size:10px;margin-top:6px;">
      <label style="display:inline;font-size:10px;"><input type="checkbox" id="modal-confirm-now" checked style="width:auto;"> Confirm this fact immediately</label>
    </div>
    <div class="form-actions">
      <button type="button" class="tiny-btn" onclick="closeFactModal()">Cancel</button>
      <button type="button" class="tiny-btn primary" id="modal-submit-add">Save Fact</button>
    </div>
  `;

  $('#modal-fact-id').onchange = () => {
    $('#custom-fields-group').style.display = $('#modal-fact-id').value === 'custom' ? 'block' : 'none';
  };

  $('#modal-submit-add').onclick = async () => {
    const sel = $('#modal-fact-id').value;
    const isCustom = sel === 'custom';
    const id = isCustom ? $('#modal-custom-id').value.trim() : sel;
    const label = isCustom ? $('#modal-custom-label').value.trim() : $('#modal-fact-id').selectedOptions[0].text.split(' (')[0];
    const val = $('#modal-fact-val').value.trim();

    if (!id || !val) {
      alert('Field and Value are required');
      return;
    }

    const permitted = [];
    if ($('#perm-portal-a').checked) {
      permitted.push('http://127.0.0.1:8000', 'http://localhost:8000');
    }

    const confirmed = $('#modal-confirm-now').checked;

    await api('passport/fact', {
      id: id,
      label: label,
      value: val,
      permitted_origins: permitted,
      user_confirmed: confirmed
    });

    closeFactModal();
    await load();
  };
}
window.openAddFactModal = openAddFactModal;

function openEditFactModal(factId) {
  const facts = cachedState?.facts || [];
  const fact = facts.filter(f => f.id === factId).sort((a, b) => b.version - a.version)[0];
  if (!fact) return;

  const m = $('#fact-modal');
  m.style.display = 'block';
  m.innerHTML = `
    <h3>Edit Fact: ${esc(fact.source_label || fact.id)}</h3>
    <label>Current Value (v${fact.version})</label>
    <input type="text" id="modal-edit-val" value="${esc(fact.value)}">
    <div style="font-size:9px;color:#7b8882;margin-top:4px;">* Changing the value creates a new version (v${fact.version + 1}) to preserve provenance.</div>
    <div style="font-size:10px;margin-top:8px;">
      <label style="display:inline;font-size:10px;"><input type="checkbox" id="modal-edit-confirm" checked style="width:auto;"> Confirm updated version</label>
    </div>
    <div class="form-actions">
      <button type="button" class="tiny-btn" onclick="closeFactModal()">Cancel</button>
      <button type="button" class="tiny-btn primary" id="modal-submit-edit">Save Update</button>
    </div>
  `;

  $('#modal-submit-edit').onclick = async () => {
    const val = $('#modal-edit-val').value.trim();
    if (!val) {
      alert('Value cannot be empty');
      return;
    }
    const confirmed = $('#modal-edit-confirm').checked;

    await api('passport/fact/' + factId, {
      value: val,
      user_confirmed: confirmed,
      source_label: fact.source_label
    }, 'PUT');

    closeFactModal();
    await load();
  };
}
window.openEditFactModal = openEditFactModal;

function openPermissionsModal(factId) {
  const facts = cachedState?.facts || [];
  const fact = facts.filter(f => f.id === factId).sort((a, b) => b.version - a.version)[0];
  if (!fact) return;

  let currentPerms = [];
  try { currentPerms = JSON.parse(fact.permitted_origins || '[]'); } catch { currentPerms = []; }
  const isAllowedLocal = currentPerms.some(p => p.includes('127.0.0.1') || p.includes('localhost'));

  const m = $('#fact-modal');
  m.style.display = 'block';
  m.innerHTML = `
    <h3>Sharing Permissions: ${esc(fact.source_label || fact.id)}</h3>
    <p style="font-size:10px;color:#607069;margin:4px 0 8px;">Select which destination websites are permitted to access this fact.</p>
    <div>
      <label style="display:inline;font-size:10px;"><input type="checkbox" id="modal-perm-local" ${isAllowedLocal ? 'checked' : ''} style="width:auto;"> Approved Local Portals (127.0.0.1:8000 / localhost:8000)</label>
    </div>
    <div class="form-actions">
      <button type="button" class="tiny-btn" onclick="closeFactModal()">Cancel</button>
      <button type="button" class="tiny-btn primary" id="modal-submit-perm">Update Permissions</button>
    </div>
  `;

  $('#modal-submit-perm').onclick = async () => {
    const permitted = [];
    if ($('#modal-perm-local').checked) {
      permitted.push('http://127.0.0.1:8000', 'http://localhost:8000');
    }

    await api('passport/fact/' + factId + '/permissions', {
      permitted_origins: permitted
    });

    closeFactModal();
    await load();
  };
}
window.openPermissionsModal = openPermissionsModal;

function currentOrigin() {
  try {
    const u = new URL(browser.src, window.location.href);
    return u.origin + u.pathname;
  } catch {
    return browser.src || '';
  }
}

async function updateScreenshot() {
  try {
    const res = await fetch('/api/automation/screenshot?t=' + Date.now());
    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const img = $('#playwright-screenshot');
      const ph = $('#playwright-placeholder');
      if (img) {
        img.src = url;
        img.style.display = 'block';
      }
      if (ph) ph.style.display = 'none';
    }
  } catch {}
}

function setMode(mode) {
  browserMode = mode;
  const btnIframe = $('#mode-iframe');
  const btnPlaywright = $('#mode-playwright');
  const iframeEl = $('#browser');
  const pwContainer = $('#playwright-container');
  const connState = $('#conn-state');

  if (mode === 'playwright') {
    if (btnPlaywright) btnPlaywright.classList.add('active');
    if (btnIframe) btnIframe.classList.remove('active');
    if (iframeEl) iframeEl.style.display = 'none';
    if (pwContainer) pwContainer.style.display = 'block';
    if (connState) connState.textContent = 'Playwright Chromium connected';
    // Navigate Playwright browser to match current view
    const origin = currentOrigin();
    api('automation/navigate', {url: origin}).then(() => updateScreenshot()).catch(() => {});
  } else {
    if (btnIframe) btnIframe.classList.add('active');
    if (btnPlaywright) btnPlaywright.classList.remove('active');
    if (iframeEl) iframeEl.style.display = 'block';
    if (pwContainer) pwContainer.style.display = 'none';
    if (connState) connState.textContent = 'Browser connected';
  }
}

$('#mode-iframe').onclick = () => setMode('iframe');
$('#mode-playwright').onclick = () => setMode('playwright');

function observed() {
  try {
    const doc = browser.contentDocument;
    if (!doc) return {};
    const result = {};
    const elements = doc.querySelectorAll('input, textarea, select');
    for (const el of elements) {
      const name = el.name;
      if (!name) continue;
      const type = (el.type || '').toLowerCase();
      if (type === 'submit' || type === 'button' || type === 'reset' || type === 'image') {
        continue;
      }
      if (type === 'radio') {
        if (el.checked) {
          result[name] = el.value;
        } else if (!(name in result)) {
          result[name] = '';
        }
      } else if (type === 'checkbox') {
        if (el.checked) {
          result[name] = el.value || 'true';
        } else if (!(name in result)) {
          result[name] = '';
        }
      } else if (el.tagName.toLowerCase() === 'select') {
        result[name] = el.value;
      } else {
        result[name] = el.value;
      }
    }
    return result;
  } catch {
    return {};
  }
}

function navigate(url, name) {
  browser.src = url;
  $('#site-name').textContent = name;
  let fullUrl = url;
  try {
    const u = new URL(url, window.location.origin);
    fullUrl = u.origin + u.pathname;
    $('#address').textContent = u.host + u.pathname;
  } catch {
    $('#address').textContent = url.replace('http://', '');
  }
  $('#site-url').textContent = '127.0.0.1 · approved demo origin';
  if (url.endsWith('/source')) {
    $('#browser-state').textContent = 'Source profile · Facts ready to carry forward';
  } else {
    $('#browser-state').textContent = 'Page ready · synthetic data';
  }

  if (browserMode === 'playwright') {
    api('automation/navigate', {url: fullUrl})
      .then(() => updateScreenshot())
      .catch(() => {});
  }
}

$('#start').onclick = async () => {
  await api('start', {user_goal: $('#goal-input').value});
  navigate('/portal/source', 'Student profile');
  await load();
};

$('#reset').onclick = async () => {
  await api('reset');
  navigate('/portal/source', 'Student profile');
  await load();
};

$('#portal-source').onclick = () => navigate('/portal/source', 'Student profile');
$('#portal-a').onclick = () => navigate('/portal/a', 'Northstar Internships');
$('#portal-b').onclick = () => navigate('/portal/b', 'Summit Talent');

const addBtn = $('#add-fact-btn');
if (addBtn) addBtn.onclick = openAddFactModal;

$('#prepare').onclick = async () => {
  const origin = currentOrigin();
  if (origin.endsWith('/source')) {
    $('#browser-state').textContent = 'Source profile is active. Select Portal A or Portal B to prepare.';
    return;
  }
  let p = null;
  if (origin.endsWith('/a')) p = 'a';
  else if (origin.endsWith('/b')) p = 'b';
  if (!p) {
    $('#browser-state').textContent = 'Please navigate to an approved application portal to prepare.';
    return;
  }
  await api('prepare/' + p);
  $('#browser-state').textContent = `Portal ${p.toUpperCase()} prepared · Review handoff receipts`;
  await load();
};

$('#fill').onclick = async () => {
  if (browserMode === 'playwright') {
    $('#browser-state').textContent = 'Playwright is filling approved fields...';
    try {
      await api('automation/fill');
      await updateScreenshot();
      $('#browser-state').textContent = 'Playwright filled approved fields into Chromium';
    } catch (e) {
      $('#browser-state').textContent = 'Playwright fill error: ' + e.message;
    }
    await load();
    return;
  }

  const s = await (await fetch('/api/state')).json();
  const origin = currentOrigin();
  const pending = s.receipts.filter(r => r.origin === origin && r.status === 'PROPOSED');
  const doc = browser.contentDocument;

  for (const r of pending) {
    if (r.permission !== 'APPROVED') continue;
    const fact = getActiveFact(s.facts, s.conflicts, r.source_fact_id);
    if (!fact || fact.verification === 'UNVERIFIED_CONFLICT' || !fact.user_confirmed) continue;

    const key = `${origin}|${r.destination_field}|${fact.id}|${fact.version}`;
    const prior = s.actions.find(a => a.idempotency_key === key);
    if (prior && ['VERIFIED', 'UNCERTAIN', 'PREPARED'].includes(prior.status)) continue;

    if (doc) {
      const targets = doc.querySelectorAll(`[name="${CSS.escape(r.destination_field)}"]`);
      for (const target of targets) {
        const type = (target.type || '').toLowerCase();
        if (type === 'radio') {
          if (target.value === fact.value) {
            target.checked = true;
            target.dispatchEvent(new Event('input', {bubbles: true}));
            target.dispatchEvent(new Event('change', {bubbles: true}));
          }
        } else if (type === 'checkbox') {
          target.checked = (fact.value === 'true' || fact.value === '1' || fact.value === target.value);
          target.dispatchEvent(new Event('input', {bubbles: true}));
          target.dispatchEvent(new Event('change', {bubbles: true}));
        } else if (target.tagName.toLowerCase() === 'select') {
          target.value = fact.value;
          target.dispatchEvent(new Event('change', {bubbles: true}));
        } else {
          target.value = fact.value;
          target.dispatchEvent(new Event('input', {bubbles: true}));
          target.dispatchEvent(new Event('change', {bubbles: true}));
        }
      }
    }
  }

  await api('fill', {origin, observed: observed()});
  $('#browser-state').textContent = 'Fields checked against the visible page';
  await load();
};

$('#conflict').onclick = async () => {
  await api('conflict');
  await load();
};

$('#recover').onclick = async () => {
  if (browserMode === 'playwright') {
    $('#browser-state').textContent = 'Playwright inspecting live DOM...';
    try {
      await api('automation/recover');
      await updateScreenshot();
      $('#browser-state').textContent = 'Playwright inspected live page · reconciled';
    } catch (e) {
      $('#browser-state').textContent = 'Playwright recovery error: ' + e.message;
    }
    await load();
    return;
  }

  const origin = currentOrigin();
  await api('recover', {origin, observed: observed()});
  $('#browser-state').textContent = 'Actual page read · saved actions reconciled';
  await load();
};

$('#submit-prepare').onclick = async () => {
  await api('submit/prepare');
  await load();
};

$('#submit-approve').onclick = async () => {
  await api('submit/approve');
  await load();
};

document.querySelectorAll('.tab').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    selected = b.dataset.tab;
    load();
  };
});

window.addEventListener('message', () => {});
browser.onload = () => {
  try {
    const doc = browser.contentDocument;
    const name = doc?.querySelector('h1')?.textContent;
    if (name) {
      $('#site-name').textContent = name;
      const u = new URL(browser.src, window.location.origin);
      $('#address').textContent = u.host + u.pathname;
    }
  } catch {}
};

navigate('/portal/source', 'Student profile');
load();
