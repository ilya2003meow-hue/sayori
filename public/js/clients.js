let allClients = [];
let clientMutationPending = false;
let clientsLoaded = false;
const canManageClients = $('#clients-table')?.dataset.canManage === 'true';

function renderSummary(rows) {
  const bookings = rows.reduce((s, c) => s + Number(c.bookings_count), 0);
  const revenue = rows.reduce((s, c) => s + Number(c.total_spent), 0);
  $('#clients-summary').innerHTML = `
    <div class="stat-card"><div class="stat-value">${rows.length}</div><div class="stat-label">${esc(tr('sum_clients'))}</div></div>
    <div class="stat-card"><div class="stat-value">${bookings}</div><div class="stat-label">${esc(tr('sum_bookings'))}</div></div>
    <div class="stat-card"><div class="stat-value">${esc(fmtPrice(revenue))}</div><div class="stat-label">${esc(tr('sum_spent'))}</div></div>`;
}

function renderTable() {
  const el = $('#clients-table');
  const q = $('#clients-search').value.trim().toLowerCase();
  const rows = allClients.filter((c) => !q || [c.name, c.email, c.phone].some((v) => (v || '').toLowerCase().includes(q)));
  if (!rows.length) {
    el.innerHTML = `<div class="empty-state">${esc(allClients.length ? tr('no_one_found') : tr('no_clients'))}</div>`;
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>${esc(tr('th_name'))}</th><th>${esc(tr('th_email'))}</th><th>${esc(tr('th_phone'))}</th><th>${esc(tr('th_bookings'))}</th><th>${esc(tr('th_spent'))}</th><th>${esc(tr('th_since'))}</th><th>${esc(tr('th_status'))}</th>${canManageClients ? `<th>${esc(tr('th_actions'))}</th>` : ''}</tr></thead>
    <tbody>${rows.map((c) => {
      const blocked = Number(c.blocked) === 1;
      return `<tr>
        <td class="cell-main">${esc(c.name)}</td>
        <td>${esc(c.email)}</td>
        <td>${esc(c.phone || '—')}</td>
        <td>${esc(c.bookings_count)}</td>
        <td class="cell-main">${esc(fmtPrice(c.total_spent))}</td>
        <td>${esc(fmtDate(c.created_at))}</td>
        <td><span class="badge ${blocked ? 'badge-inactive' : 'badge-active'}">${esc(tr(blocked ? 'client_blocked' : 'client_unblocked'))}</span></td>
        ${canManageClients ? `<td><div class="row-actions"><button type="button" class="btn ${blocked ? 'btn-green' : 'btn-danger'} btn-sm" data-block-client="${esc(c.id)}" ${clientMutationPending || !clientsLoaded ? 'disabled' : ''}>${esc(tr(blocked ? 'btn_unblock_client' : 'btn_block_client'))}</button><button type="button" class="btn btn-danger btn-sm" data-delete-client="${esc(c.id)}" ${clientMutationPending || !clientsLoaded ? 'disabled' : ''}>${esc(tr('btn_delete_client'))}</button></div></td>` : ''}
      </tr>`;
    }).join('')}</tbody></table></div>`;
}

$('#clients-search')?.addEventListener('input', renderTable);

async function loadClients() {
  const el = $('#clients-table');
  clientsLoaded = false;
  el.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    allClients = await api('/api/admin/clients');
    clientsLoaded = true;
    renderSummary(allClients);
    renderTable();
  } catch (err) {
    el.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    toast(err.message, true);
  }
}

$('#clients-table')?.addEventListener('click', async (e) => {
  const blockButton = e.target.closest('[data-block-client]');
  const deleteButton = e.target.closest('[data-delete-client]');
  const button = blockButton || deleteButton;
  if (!canManageClients || !button || button.disabled || clientMutationPending || !clientsLoaded) return;

  const clientId = blockButton ? blockButton.dataset.blockClient : deleteButton.dataset.deleteClient;
  const client = allClients.find((c) => String(c.id) === clientId);
  if (!client) return;

  const deleting = Boolean(deleteButton);
  const blocked = Number(client.blocked) !== 1;
  const confirmKey = deleting ? 'confirm_delete_client' : (blocked ? 'confirm_block_client' : 'confirm_unblock_client');
  if (!confirm(tr(confirmKey))) return;

  clientMutationPending = true;
  $$('[data-block-client], [data-delete-client]').forEach((btn) => { btn.disabled = true; });
  try {
    if (deleting) {
      await api(`/api/admin/clients/${encodeURIComponent(client.id)}`, { method: 'DELETE' });
      toast(tr('toast_client_deleted'));
    } else {
      await api(`/api/admin/clients/${encodeURIComponent(client.id)}/block`, { method: 'PATCH', body: { blocked } });
      client.blocked = blocked ? 1 : 0;
      toast(tr(blocked ? 'toast_client_blocked' : 'toast_client_unblocked'));
    }
  } catch (err) { toast(err.message, true); }
  finally {
    await loadClients();
    clientMutationPending = false;
    if (clientsLoaded) renderTable();
  }
});

loadClients();