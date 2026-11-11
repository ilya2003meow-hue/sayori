const state = {
  user: null, tab: 'bookings', editingProcedure: null,
  procedures: [], procedureBusy: false, procedureLoadId: 0,
  approvalBusy: false, approvalLoadId: 0, decidedRequests: new Set(),
};
const canManageProcedures = $('#staff-tabs')?.dataset.role === 'admin';
const canApproveProcedures = $('#staff-tabs')?.dataset.role === 'owner';
let procedureImageURL = null;

const ROLE_LABELS = { client: tr('role_client'), admin: tr('role_admin'), owner: tr('role_owner') };

function openModal(id) { $('#' + id)?.classList.remove('hidden'); }
function closeModalEl(el) {
  if (el.id === 'procedure-modal') {
    if (state.procedureBusy) return;
    revokeProcedureImageURL();
  }
  el.classList.add('hidden');
}
$$('.modal-overlay').forEach((ov) => {
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) closeModalEl(ov); });
  ov.querySelectorAll('[data-close]').forEach((b) => { b.onclick = () => closeModalEl(ov); });
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') $$('.modal-overlay:not(.hidden)').forEach(closeModalEl);
});

const LOADERS = { stats: loadStats, bookings: loadAdminBookings, procedures: loadAdminProcedures, approvals: loadApprovals, staff: loadStaff };

function switchTab(name) {
  if (!LOADERS[name] || !$('#tab-' + name) || (name === 'approvals' && !canApproveProcedures)) return;
  state.tab = name;
  $$('#staff-tabs .tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-page').forEach((p) => p.classList.add('hidden'));
  $('#tab-' + name).classList.remove('hidden');
  LOADERS[name]();
}
$('#staff-tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-tab]');
  if (btn) switchTab(btn.dataset.tab);
});
$('#open-approvals-btn')?.addEventListener('click', () => switchTab('approvals'));

async function loadAdminBookings() {
  const el = $('#admin-bookings-table');
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  const params = new URLSearchParams();
  if ($('#filter-status').value) params.set('status', $('#filter-status').value);
  if ($('#filter-date').value) params.set('date', $('#filter-date').value);
  try {
    const rows = await api('/api/admin/bookings?' + params);
    if (!rows.length) { el.innerHTML = `<div class="empty-state">${esc(tr('no_bookings_found'))}</div>`; return; }
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>${esc(tr('th_datetime'))}</th><th>${esc(tr('th_client'))}</th><th>${esc(tr('th_procedure'))}</th><th>${esc(tr('th_child'))}</th><th>${esc(tr('th_status'))}</th><th>${esc(tr('booking_payment_method'))}</th><th>${esc(tr('th_sum'))}</th><th>${esc(tr('th_actions'))}</th></tr></thead>
      <tbody>${rows.map((b) => `
        <tr>
          <td><div class="cell-main">${fmtDate(b.date)}</div><div class="cell-sub">${esc(b.time)}</div></td>
          <td><div class="cell-main">${esc(b.client_name)}</div><div class="cell-sub">${esc(b.client_phone || b.client_email)}</div></td>
          <td><div class="cell-main">${esc(b.procedure_name)}</div><div class="cell-sub">${b.duration_min} ${esc(tr('proc_min'))}</div></td>
          <td>${esc(b.child_name)}, ${b.child_age} ${esc(tr('booking_years'))}<div class="cell-sub">${esc(tr('booking_children_count'))}: ${Number(b.children_count || 1)}</div>${b.comment ? `<div class="cell-sub">${esc(b.comment)}</div>` : ''}</td>
          <td>${badge(b.status)}</td>
          <td><div>${esc(b.payment_method === 'deposit' ? tr('payment_deposit_label') : (b.payment_method === 'full' ? tr('payment_full_label') : tr('payment_onsite_label')))}</div><div class="cell-sub">${esc(b.payment_channel === 'kaspi_qr' ? tr('payment_channel_kaspi') : tr('payment_channel_onsite'))}</div>${b.payment_status === 'pending' ? `<div class="cell-sub">${esc(tr('payment_pending_label'))}: ${fmtPrice(b.deposit_amount)}</div>` : (b.payment_status === 'paid' ? `<div class="cell-sub">${esc(tr('payment_paid_label'))}: ${fmtPrice(b.payment_channel === 'kaspi_qr' ? b.deposit_amount : b.price)}</div>` : '')}</td>
          <td class="cell-main">${fmtPrice(b.price)}</td>
          <td><div class="row-actions">
            ${((b.payment_channel === 'kaspi_qr' && b.payment_status === 'pending') || (b.payment_channel === 'onsite' && b.payment_status !== 'paid' && ['confirmed', 'completed'].includes(b.status))) ? `<button class="btn btn-green btn-sm" data-payment-paid="${b.id}" data-payment-channel="${esc(b.payment_channel)}">${esc(tr('payment_mark_paid'))}</button>` : ''}
            ${b.status === 'new' ? `<button class="btn btn-green btn-sm" data-set-status="confirmed" data-id="${b.id}">${esc(tr('btn_accept_booking'))}</button><button class="btn btn-danger btn-sm" data-set-status="rejected" data-id="${b.id}">${esc(tr('btn_reject_booking'))}</button>` : ''}
            ${b.status === 'confirmed' ? `<button class="btn btn-green btn-sm" data-set-status="completed" data-id="${b.id}">${esc(tr('btn_complete'))}</button>` : ''}
            ${b.status === 'confirmed' ? `<button class="btn btn-danger btn-sm" data-set-status="cancelled" data-id="${b.id}">${esc(tr('btn_cancel'))}</button>` : ''}
          </div></td>
        </tr>`).join('')}</tbody></table></div>`;
  } catch (err) { el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`; }
}
$('#filter-status').addEventListener('change', loadAdminBookings);
$('#filter-date').addEventListener('change', loadAdminBookings);
$('#filter-reset').onclick = () => { $('#filter-status').value = ''; $('#filter-date').value = ''; loadAdminBookings(); };
$('#admin-bookings-table').addEventListener('click', async (e) => {
  const paymentBtn = e.target.closest('[data-payment-paid]');
  if (paymentBtn) {
    const confirmText = paymentBtn.dataset.paymentChannel === 'onsite'
      ? tr('payment_mark_onsite_paid_confirm')
      : tr('payment_mark_paid_confirm');
    if (!confirm(confirmText)) return;
    try {
      await api(`/api/admin/bookings/${paymentBtn.dataset.paymentPaid}`, { method: 'PATCH', body: { payment_status: 'paid' } });
      toast(tr('payment_marked_paid'));
      loadAdminBookings();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const btn = e.target.closest('[data-set-status]');
  if (!btn) return;
  const status = btn.dataset.setStatus;
  if (status === 'cancelled' && !confirm(tr('confirm_cancel_booking'))) return;
  if (status === 'rejected' && !confirm(tr('confirm_reject_booking'))) return;
  try {
    await api(`/api/admin/bookings/${btn.dataset.id}`, { method: 'PATCH', body: { status } });
    const toastKey = { completed: 'toast_completed', confirmed: 'toast_confirmed', rejected: 'toast_rejected', cancelled: 'toast_cancelled_admin' }[status];
    toast(tr(toastKey));
    loadAdminBookings();
    pollPendingBookings();
  } catch (err) { toast(err.message, true); }
});

const PROCEDURE_REQUEST_LABELS = {
  pending: 'procedure_status_pending', approved: 'procedure_status_approved',
  rejected: 'procedure_status_rejected', superseded: 'procedure_status_superseded',
};

function editableProcedure(proc) {
  return ['pending', 'rejected'].includes(proc.request?.status) ? proc.request.fields : proc;
}

function procedureFields(p) {
  return {
    name: p.name, description: p.description, category: p.category,
    duration_min: Number(p.duration_min), price: Number(p.price),
    image: p.image || '', active: Number(p.active) === 1 ? 1 : 0,
  };
}

function syncProcedureControls() {
  $$('#add-procedure-btn, #admin-procedures-table button, #procedure-modal input, #procedure-modal select, #procedure-modal textarea, #procedure-modal button')
    .forEach((control) => { control.disabled = state.procedureBusy; });
}

async function loadAdminProcedures() {
  const el = $('#admin-procedures-table');
  const loadId = ++state.procedureLoadId;
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    const rows = await api('/api/admin/procedures');
    if (loadId !== state.procedureLoadId) return;
    state.procedures = rows;
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>${esc(tr('th_name'))}</th><th>${esc(tr('th_category'))}</th><th>${esc(tr('th_duration'))}</th><th>${esc(tr('th_price'))}</th><th>${esc(tr('th_active'))}</th><th>${esc(tr('th_status'))}</th>${canManageProcedures ? `<th>${esc(tr('th_actions'))}</th>` : ''}</tr></thead>
      <tbody>${rows.map((p) => {
        const statusKey = PROCEDURE_REQUEST_LABELS[p.request?.status];
        return `<tr>
          <td class="cell-main">${esc(p.name)}</td>
          <td>${esc(catLabel(p.category))}</td>
          <td>${esc(p.duration_min)} ${esc(tr('proc_min'))}</td>
          <td class="cell-main">${esc(fmtPrice(p.price))}</td>
          <td><span class="badge ${Number(p.active) === 1 ? 'badge-active' : 'badge-inactive'}">${esc(tr(Number(p.active) === 1 ? 'proc_active' : 'proc_hidden'))}</span></td>
          <td><span class="badge">${esc(tr(Number(p.published) === 1 ? 'procedure_published' : 'procedure_unpublished'))}</span>
            ${statusKey ? `<span class="badge">${esc(tr(statusKey))}</span>` : ''}</td>
          ${canManageProcedures ? `<td><div class="row-actions">
            <button type="button" class="btn btn-ghost btn-sm" data-proc-action="edit" data-proc-id="${esc(p.id)}">${esc(tr('btn_edit'))}</button>
            ${Number(p.active) === 1
              ? `<button type="button" class="btn btn-danger btn-sm" data-proc-action="hide" data-proc-id="${esc(p.id)}">${esc(tr('btn_hide'))}</button>`
              : `<button type="button" class="btn btn-green btn-sm" data-proc-action="show" data-proc-id="${esc(p.id)}">${esc(tr('btn_show'))}</button>`}
          </div></td>` : ''}
        </tr>`;
      }).join('')}</tbody></table></div>`;
    syncProcedureControls();
  } catch (err) {
    if (loadId !== state.procedureLoadId) return;
    el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    toast(err.message, true);
  }
}

$('#admin-procedures-table')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-proc-action]');
  if (!btn || btn.disabled || !canManageProcedures || state.procedureBusy) return;
  const proc = state.procedures.find((p) => String(p.id) === btn.dataset.procId);
  if (!proc) return;
  const action = btn.dataset.procAction;
  if (action === 'edit') { openProcedureModal(proc); return; }
  if (!['hide', 'show'].includes(action)) return;
  if (action === 'hide' && !confirm(tr('confirm_hide_proc_request'))) return;
  state.procedureBusy = true;
  syncProcedureControls();
  try {
    const path = `/api/admin/procedures/${encodeURIComponent(proc.id)}`;
    await api(path, action === 'hide'
      ? { method: 'DELETE' }
      : { method: 'PATCH', body: { ...procedureFields(editableProcedure(proc)), active: 1 } });
    toast(tr('toast_proc_submitted'));
  } catch (err) { toast(err.message, true); }
  finally {
    await loadAdminProcedures();
    state.procedureBusy = false;
    syncProcedureControls();
  }
});

// Only relative public image paths are accepted, never external or protocol-relative URLs.
function procedureImageSrc(path) {
  return typeof path === 'string' && /^img\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.(?:png|jpe?g|webp)$/i.test(path) ? '/' + path : '';
}

function revokeProcedureImageURL() {
  if (procedureImageURL) URL.revokeObjectURL(procedureImageURL);
  procedureImageURL = null;
}

function validateProcedureImage(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error(tr('image_invalid_type'));
  if (file.size > 5 * 1024 * 1024) throw new Error(tr('image_too_large'));
}

function updateProcedureImagePreview(file = null) {
  revokeProcedureImageURL();
  const form = $('#procedure-form');
  const preview = $('#procedure-image-preview');
  if (!form || !preview) return;
  if (file) procedureImageURL = URL.createObjectURL(file);
  const src = procedureImageURL || procedureImageSrc(form.elements.image.value);
  if (src) preview.src = src;
  else preview.removeAttribute('src');
  preview.classList.toggle('hidden', !src);
  $('#procedure-image-empty')?.classList.toggle('hidden', !!src);
}
window.addEventListener('pagehide', revokeProcedureImageURL);

function openProcedureModal(proc) {
  const form = $('#procedure-form');
  if (!canManageProcedures || !form || state.procedureBusy) return;
  state.editingProcedure = proc ? proc.id : null;
  $('#procedure-modal-title').textContent = proc ? tr('modal_proc_edit') : tr('modal_proc_new');
  form.reset();
  hideError(form);
  if (proc) {
    const fields = editableProcedure(proc);
    form.elements.name.value = fields.name;
    form.elements.category.value = fields.category;
    form.elements.duration_min.value = fields.duration_min;
    form.elements.price.value = fields.price;
    form.elements.image.value = fields.image || '';
    form.elements.description.value = fields.description || '';
    form.elements.active.checked = Number(fields.active) === 1;
  } else {
    form.elements.duration_min.value = 30;
    form.elements.price.value = 1000;
  }
  updateProcedureImagePreview();
  openModal('procedure-modal');
}
$('#add-procedure-btn')?.addEventListener('click', () => openProcedureModal(null));
$('#procedure-form')?.elements.image_file?.addEventListener('change', (e) => {
  const form = $('#procedure-form');
  if (!canManageProcedures || state.procedureBusy || !form) return;
  hideError(form);
  const file = e.target.files?.[0];
  try {
    if (file) validateProcedureImage(file);
    updateProcedureImagePreview(file);
  } catch (err) {
    e.target.value = '';
    updateProcedureImagePreview();
    showError(form, err.message);
  }
});
$('#remove-procedure-image')?.addEventListener('click', () => {
  const form = $('#procedure-form');
  if (!canManageProcedures || state.procedureBusy || !form) return;
  form.elements.image.value = '';
  form.elements.image_file.value = '';
  hideError(form);
  updateProcedureImagePreview();
});

$('#procedure-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!canManageProcedures || state.procedureBusy) return;
  const form = e.target;
  hideError(form);
  const fd = new FormData(form);
  const body = {
    name: fd.get('name'), category: fd.get('category'),
    duration_min: Number(fd.get('duration_min')), price: Number(fd.get('price')),
    image: fd.get('image'), description: fd.get('description'),
    active: form.elements.active.checked ? 1 : 0,
  };
  const file = form.elements.image_file.files?.[0];
  const editingId = state.editingProcedure;
  let submitted = false;
  state.procedureBusy = true;
  syncProcedureControls();
  try {
    if (file) {
      validateProcedureImage(file);
      const upload = new FormData();
      upload.append('image', file);
      const response = await fetch('/api/admin/images', { method: 'POST', credentials: 'same-origin', body: upload });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || tr('err_server'));
      if (!procedureImageSrc(data.image) || !data.image.startsWith('img/uploads/')) throw new Error(tr('err_server'));
      body.image = data.image;
      form.elements.image.value = data.image;
      form.elements.image_file.value = '';
      updateProcedureImagePreview();
    }
    if (body.image && !procedureImageSrc(body.image)) throw new Error(tr('image_invalid_type'));
    if (editingId !== null) await api(`/api/admin/procedures/${encodeURIComponent(editingId)}`, { method: 'PATCH', body });
    else await api('/api/admin/procedures', { method: 'POST', body });
    submitted = true;
    toast(tr('toast_proc_submitted'));
    await loadAdminProcedures();
  } catch (err) { showError(form, err.message); toast(err.message, true); }
  finally {
    state.procedureBusy = false;
    syncProcedureControls();
    if (submitted) closeModalEl($('#procedure-modal'));
  }
});

function approvalVersion(fields, titleKey) {
  const src = procedureImageSrc(fields?.image);
  return `<section class="approval-version"><h4>${esc(tr(titleKey))}</h4>
    <div class="procedure-preview">
      ${src ? `<img class="image-preview" src="${esc(src)}" alt="${esc(fields.name)}" loading="lazy">` : `<p>${esc(tr('image_none'))}</p>`}
      ${fields ? `<dl>
        <dt>${esc(tr('th_name'))}</dt><dd>${esc(fields.name)}</dd>
        <dt>${esc(tr('label_description'))}</dt><dd>${esc(fields.description)}</dd>
        <dt>${esc(tr('label_category'))}</dt><dd>${esc(catLabel(fields.category))}</dd>
        <dt>${esc(tr('label_duration'))}</dt><dd>${esc(fields.duration_min)} ${esc(tr('proc_min'))}</dd>
        <dt>${esc(tr('label_price'))}</dt><dd>${esc(fmtPrice(fields.price))}</dd>
        <dt>${esc(tr('label_image'))}</dt><dd>${esc(fields.image || tr('image_none'))}</dd>
        <dt>${esc(tr('label_active'))}</dt><dd>${esc(tr(Number(fields.active) === 1 ? 'proc_active' : 'proc_hidden'))}</dd>
      </dl>` : `<p>${esc(tr('approval_new'))}</p>`}
    </div></section>`;
}

function syncApprovalControls() {
  $$('#procedure-approvals [data-decision]').forEach((btn) => {
    btn.disabled = state.approvalBusy || state.decidedRequests.has(btn.dataset.requestId);
  });
}

async function loadApprovals() {
  const el = $('#procedure-approvals');
  if (!canApproveProcedures || !el) return;
  const loadId = ++state.approvalLoadId;
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    const rows = await api('/api/owner/procedure-requests');
    if (loadId !== state.approvalLoadId) return;
    el.innerHTML = rows.length ? rows.map((request) => `<article class="approval-card">
      <h3>${esc(request.fields.name)}</h3>
      <div class="approval-compare">${approvalVersion(request.current, 'approval_current')}${approvalVersion(request.fields, 'approval_proposed')}</div>
      <div class="row-actions">
        <button type="button" class="btn btn-green btn-sm" data-decision="approve" data-request-id="${esc(request.id)}">${esc(tr('btn_approve'))}</button>
        <button type="button" class="btn btn-danger btn-sm" data-decision="reject" data-request-id="${esc(request.id)}">${esc(tr('btn_reject'))}</button>
      </div></article>`).join('') : `<div class="empty-state">${esc(tr('approvals_empty'))}</div>`;
    syncApprovalControls();
  } catch (err) {
    if (loadId !== state.approvalLoadId) return;
    el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    toast(err.message, true);
  }
}

$('#procedure-approvals')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-decision]');
  if (!canApproveProcedures || !btn || btn.disabled || state.approvalBusy) return;
  const { requestId, decision } = btn.dataset;
  if (state.decidedRequests.has(requestId) || !['approve', 'reject'].includes(decision)) return;
  state.approvalBusy = true;
  syncApprovalControls();
  try {
    await api(`/api/owner/procedure-requests/${encodeURIComponent(requestId)}/decision`, { method: 'POST', body: { decision } });
    state.decidedRequests.add(requestId);
    toast(tr(decision === 'approve' ? 'toast_proc_approved' : 'toast_proc_rejected'));
  } catch (err) { toast(err.message, true); }
  finally {
    // Refresh after every response, including a stale (409) decision.
    await loadApprovals();
    await loadAdminProcedures();
    state.approvalBusy = false;
    syncApprovalControls();
  }
});

async function loadStats() {
  const el = $('#tab-stats');
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    const s = await api('/api/owner/stats');
    el.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">${fmtPrice(s.revenue)}</div><div class="stat-label">${esc(tr('stat_revenue'))}</div></div>
        <div class="stat-card"><div class="stat-value">${fmtPrice(s.revenue_week)}</div><div class="stat-label">${esc(tr('stat_revenue_week'))}</div></div>
        <div class="stat-card"><div class="stat-value">${s.clients_count}</div><div class="stat-label">${esc(tr('stat_clients'))}</div></div>
        <div class="stat-card"><div class="stat-value">${s.today_upcoming}</div><div class="stat-label">${esc(tr('stat_today'))}</div></div>
      </div>
      <h3 class="stats-sub">${esc(tr('stats_by_status'))}</h3>
      <div class="status-chips">
        ${Object.keys(STATUS_LABELS).map((k) => `<span class="badge badge-${k}">${STATUS_LABELS[k]}: ${s.status_counts[k] || 0}</span>`).join('')}
      </div>
      <h3 class="stats-sub">${esc(tr('stats_top_procs'))}</h3>
      ${s.top_procedures.length ? `<div class="table-wrap"><table>
        <thead><tr><th>${esc(tr('th_procedure'))}</th><th>${esc(tr('th_bookings'))}</th><th>${esc(tr('th_revenue'))}</th></tr></thead>
        <tbody>${s.top_procedures.map((p) => `<tr><td class="cell-main">${esc(p.procedure_name)}</td><td>${p.cnt}</td><td class="cell-main">${fmtPrice(p.revenue)}</td></tr>`).join('')}</tbody>
      </table></div>` : `<div class="empty-state">${esc(tr('no_bookings_yet'))}</div>`}`;
  } catch (err) { el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`; }
}

async function loadStaff() {
  const el = $('#admin-staff-table');
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    const rows = await api('/api/owner/staff');
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>${esc(tr('th_name'))}</th><th>${esc(tr('th_email'))}</th><th>${esc(tr('th_phone'))}</th><th>${esc(tr('th_role'))}</th><th>${esc(tr('th_actions'))}</th></tr></thead>
      <tbody>${rows.map((u) => `
        <tr>
          <td class="cell-main">${esc(u.name)}</td>
          <td>${esc(u.email)}</td>
          <td>${esc(u.phone || '—')}</td>
          <td><span class="badge badge-${u.role}">${ROLE_LABELS[u.role]}</span></td>
          <td>${u.role === 'admin' && u.id !== state.user.id ? `<button class="btn btn-danger btn-sm" data-del-staff="${u.id}">${esc(tr('btn_delete'))}</button>` : '—'}</td>
        </tr>`).join('')}</tbody></table></div>`;
    el.querySelectorAll('[data-del-staff]').forEach((b) => { b.onclick = async () => {
      if (!confirm(tr('confirm_del_staff'))) return;
      try { await api(`/api/owner/staff/${b.dataset.delStaff}`, { method: 'DELETE' }); toast(tr('toast_staff_deleted')); loadStaff(); }
      catch (err) { toast(err.message, true); }
    }; });
  } catch (err) { el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`; }
}
$('#add-staff-btn')?.addEventListener('click', () => { $('#staff-form').reset(); hideError($('#staff-form')); openModal('staff-modal'); });
$('#staff-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  hideError(form);
  const fd = new FormData(form);
  try {
    await api('/api/owner/staff', { method: 'POST', body: { name: fd.get('name'), email: fd.get('email'), phone: fd.get('phone'), password: fd.get('password') } });
    closeModalEl($('#staff-modal'));
    toast(tr('toast_staff_added'));
    loadStaff();
  } catch (err) { showError(form, err.message); }
});

let knownPendingBookingIds = null;
let pendingPollBusy = false;
async function pollPendingBookings() {
  if (pendingPollBusy) return;
  pendingPollBusy = true;
  try {
    const pending = await api('/api/admin/bookings?status=new');
    const ids = new Set(pending.map((booking) => String(booking.id)));
    const notice = $('#pending-bookings-notice');
    if (notice) {
      notice.textContent = pending.length
        ? `${tr('pending_bookings_label')}: ${pending.length}. ${tr('pending_bookings_hint')}`
        : tr('pending_bookings_none');
      notice.classList.toggle('is-empty', pending.length === 0);
    }
    const hasNewRequests = knownPendingBookingIds !== null
      && [...ids].some((id) => !knownPendingBookingIds.has(id));
    if (hasNewRequests) {
      toast(tr('toast_new_booking'));
      if (state.tab === 'bookings' && !$('#filter-status').value) loadAdminBookings();
    }
    knownPendingBookingIds = ids;
  } catch (err) {
    // The main table reports authorization/network errors; polling stays quiet.
  } finally {
    pendingPollBusy = false;
  }
}

(async function init() {
  const me = await api('/api/me');
  state.user = me.user;
  switchTab('bookings');
  await pollPendingBookings();
  window.setInterval(pollPendingBookings, 7000);
})();