const procedureId = Number($('.booking-proc').dataset.procedureId);
let selectedTime = null;

const form = $('#booking-form');
const dateInput = form.elements.date;
const paymentSummary = $('#payment-total');
const procedurePrice = Number(paymentSummary.dataset.price || 0);
const depositPercent = Number(paymentSummary.dataset.percent || 20);
const paymentPlanChoice = $('#payment-plan-choice');
function updatePaymentSummary() {
  const channel = form.elements.payment_channel.value;
  if (channel === 'onsite') {
    paymentPlanChoice.hidden = true;
    paymentSummary.textContent = tr('booking_onsite_total').replace('{amount}', fmtPrice(procedurePrice));
    return;
  }
  paymentPlanChoice.hidden = false;
  const method = form.elements.payment_method.value;
  if (method === 'deposit') {
    const amount = Math.round(procedurePrice * depositPercent / 100);
    paymentSummary.textContent = tr('booking_deposit_total').replace('{amount}', fmtPrice(amount));
  } else {
    paymentSummary.textContent = tr('booking_full_total').replace('{amount}', fmtPrice(procedurePrice));
  }
}
form.querySelectorAll('input[name="payment_method"], input[name="payment_channel"]').forEach((radio) => radio.addEventListener('change', updatePaymentSummary));
updatePaymentSummary();
dateInput.min = todayStr();
dateInput.max = addDaysStr(30);
dateInput.value = addDaysStr(1);
dateInput.onchange = loadSlots;

async function loadSlots() {
  const grid = $('#slots-grid');
  selectedTime = null;
  if (!dateInput.value) { grid.innerHTML = `<div class="slots-empty">${esc(tr('slots_pick_date'))}</div>`; return; }
  grid.innerHTML = `<div class="slots-empty">${esc(tr('loading'))}</div>`;
  try {
    const data = await api(`/api/slots?procedure_id=${procedureId}&date=${dateInput.value}`);
    grid.innerHTML = data.slots.length
      ? data.slots.map((t) => `<button type="button" class="slot-btn" data-slot="${t}">${t}</button>`).join('')
      : `<div class="slots-empty">${esc(tr('slots_none'))}</div>`;
  } catch (err) {
    grid.innerHTML = `<div class="slots-empty">${esc(err.message)}</div>`;
  }
}
$('#slots-grid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-slot]');
  if (!btn) return;
  $$('#slots-grid .slot-btn').forEach((b) => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedTime = btn.dataset.slot;
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideError(form);
  if (!selectedTime) { showError(form, tr('err_pick_time')); return; }
  const fd = new FormData(form);
  try {
    const result = await api('/api/bookings', { method: 'POST', body: {
      procedure_id: procedureId,
      date: fd.get('date'),
      time: selectedTime,
      child_name: fd.get('child_name'),
      child_age: Number(fd.get('child_age')),
      children_count: Number(fd.get('children_count')),
      comment: fd.get('comment'),
      payment_method: fd.get('payment_method'),
      payment_channel: fd.get('payment_channel'),
    } });
    location = result.payment_url || '/cabinet?booked=1';
  } catch (err) {
    showError(form, err.message);
    if (err.code === 'slot_taken') loadSlots();
  }
});

loadSlots();