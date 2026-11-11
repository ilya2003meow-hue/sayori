let bookingStateSignature = null;
let previousBookingStatuses = null;

async function loadMyBookings({ silent = false } = {}) {
  const list = $('#my-bookings');
  if (!silent) list.innerHTML = `<div class="empty-state">${esc(tr('loading'))}</div>`;
  try {
    const rows = await api('/api/my/bookings');
    const signature = JSON.stringify(rows.map((b) => [b.id, b.status, b.children_count || 1, b.payment_method, b.payment_channel, b.payment_status]));
    if (silent && signature === bookingStateSignature) return;

    const changedStatuses = [];
    if (silent && previousBookingStatuses) {
      rows.forEach((b) => {
        const previous = previousBookingStatuses.get(String(b.id));
        if (previous && previous !== b.status) changedStatuses.push(b.status);
      });
    }
    previousBookingStatuses = new Map(rows.map((b) => [String(b.id), b.status]));
    bookingStateSignature = signature;

    if (!rows.length) {
      list.innerHTML = `<div class="empty-state">${esc(tr('bookings_empty'))}</div>`;
    } else {
      list.innerHTML = rows.map((b) => `
        <div class="booking-card">
          ${b.image ? `<img src="/${esc(b.image)}" alt="">` : ''}
          <div class="booking-info">
            <h3>${esc(b.procedure_name)}</h3>
            <div class="muted">${esc(tr('booking_child'))}: ${esc(b.child_name)}, ${b.child_age} ${esc(tr('booking_years'))} · ${esc(tr('booking_children_count'))}: ${Number(b.children_count || 1)} · ${b.duration_min} ${esc(tr('proc_min'))}</div>
            <div class="booking-when">${fmtDate(b.date)} ${esc(tr('booking_at'))} ${esc(b.time)}</div>
            <div class="cell-sub">${esc(b.payment_method === 'deposit' ? tr('payment_deposit_label') : (b.payment_method === 'full' ? tr('payment_full_label') : tr('payment_onsite_label')))} · ${esc(b.payment_channel === 'kaspi_qr' ? tr('payment_channel_kaspi') : tr('payment_channel_onsite'))}${b.payment_status === 'pending' ? ` · ${esc(tr('payment_pending_label'))}: ${esc(fmtPrice(b.deposit_amount))}` : (b.payment_status === 'paid' ? ` · ${esc(tr('payment_paid_label'))}: ${esc(fmtPrice(b.payment_channel === 'kaspi_qr' ? b.deposit_amount : b.price))}` : '')}</div>
            ${b.payment_channel === 'kaspi_qr' && b.payment_status === 'pending' ? `<a class="btn btn-ghost btn-sm" href="/payment/${b.id}">${esc(tr('payment_open_kaspi'))}</a>` : ''}
          </div>
          <span class="proc-price">${fmtPrice(b.price)}</span>
          ${badge(b.status)}
          ${['new', 'confirmed'].includes(b.status) ? `<button class="btn btn-danger btn-sm" data-cancel="${b.id}">${esc(tr('btn_cancel'))}</button>` : ''}
        </div>`).join('');
    }
    if (changedStatuses.includes('confirmed')) toast(tr('toast_confirmed'));
    if (changedStatuses.includes('rejected')) toast(tr('toast_rejected'));
  } catch (err) {
    if (!silent) list.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
  }
}

$('#my-bookings').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-cancel]');
  if (!btn || !confirm(tr('confirm_cancel'))) return;
  try {
    await api(`/api/bookings/${btn.dataset.cancel}/cancel`, { method: 'POST' });
    toast(tr('toast_cancelled'));
    loadMyBookings();
  } catch (err) { toast(err.message, true); }
});

loadMyBookings();
window.setInterval(() => loadMyBookings({ silent: true }), 7000);

const profileView = $('#profile-view');
const profileForm = $('#profile-form');
$('#edit-profile-btn').onclick = () => { profileView.classList.add('hidden'); profileForm.classList.remove('hidden'); };
$('#profile-cancel').onclick = () => { profileForm.classList.add('hidden'); profileView.classList.remove('hidden'); };
profileForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  hideError(form);
  const fd = new FormData(form);
  try {
    await api('/api/me', { method: 'PATCH', body: { name: fd.get('name'), phone: fd.get('phone') } });
    location = '/cabinet?profile=1';
  } catch (err) { showError(form, err.message); }
});