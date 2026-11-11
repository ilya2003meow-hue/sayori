const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const tr = (key) => (window.I18N && window.I18N[key]) || key;
const catLabel = (cat) => (window.I18N && window.I18N.cats && window.I18N.cats[cat]) || cat;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, { method = 'GET', body, signal, cache = 'default' } = {}) {
  const apiBase = String(window.PSPA_API_BASE_URL || '').trim().replace(/\/+$/, '');
  if (!apiBase) {
    throw new Error('Сервер входа и отзывов пока не подключён. Интерфейс восстановлен, но для сохранения данных нужен backend.');
  }
  const res = await fetch(apiBase + path, {
    method, signal, cache, credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || tr('err_server'));
    err.code = data.code;
    throw err;
  }
  return data;
}

const MONTHS = tr('months').split(',');
const fmtDate = (iso) => {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
};
const NUM_LOCALE = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-US' }[window.LANG] || 'ru-RU';
const fmtPrice = (n) => Number(n).toLocaleString(NUM_LOCALE) + ' ₸';
const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const addDaysStr = (days) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const STATUS_LABELS = { new: tr('status_new'), confirmed: tr('status_confirmed'), completed: tr('status_completed'), cancelled: tr('status_cancelled'), rejected: tr('status_rejected') };
const badge = (status) => `<span class="badge badge-${status}">${STATUS_LABELS[status] || status}</span>`;

const icons = {
  clock: '<svg viewBox="0 0 24 24" class="icon"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3.5 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  star: '<svg viewBox="0 0 24 24" class="icon"><path d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2-6.3-4.5-6.3 4.5L8 13.8 2 9.2h7.6z" fill="currentColor"/></svg>',
};

function toast(msg, isError = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (isError ? ' error' : '');
  t.textContent = msg;
  $('#toast-wrap').append(t);
  setTimeout(() => t.remove(), 4200);
}
function showError(form, msg) {
  const el = form.querySelector('.form-error');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideError(form) {
  form.querySelector('.form-error')?.classList.add('hidden');
}

const logoutBtn = $('#logout-btn');
if (logoutBtn) {
  logoutBtn.onclick = async () => {
    await api('/api/logout', { method: 'POST' });
    location = '/';
  };
}

$$('.lang-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.dataset.lang === window.LANG) return;
    document.cookie = 'pspa_lang=' + btn.dataset.lang + ';path=/;max-age=31536000;SameSite=Lax';
    location.reload();
  });
});

const themeBtn = $('#theme-toggle');
if (themeBtn) {
  themeBtn.onclick = () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('pspa_theme', next); } catch (e) {}
  };
}

const params = new URLSearchParams(location.search);
const TOASTS = { booked: tr('toast_booked'), reviewed: tr('toast_reviewed'), replied: tr('toast_replied'), profile: tr('toast_profile'), denied: tr('toast_denied') };
let hadToast = false;
for (const [key, msg] of Object.entries(TOASTS)) {
  if (params.has(key)) {
    toast(msg, key === 'denied');
    params.delete(key);
    hadToast = true;
  }
}
if (hadToast) {
  const rest = params.toString();
  history.replaceState(null, '', location.pathname + (rest ? '?' + rest : ''));
}