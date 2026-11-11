function setAuthTab(tab) {
  $$('[data-auth-tab]').forEach((b) => b.classList.toggle('active', b.dataset.authTab === tab));
  $('#login-form').classList.toggle('hidden', tab !== 'login');
  $('#register-form').classList.toggle('hidden', tab !== 'register');
}
$$('[data-auth-tab]').forEach((b) => { b.onclick = () => setAuthTab(b.dataset.authTab); });
setAuthTab(new URLSearchParams(location.search).get('tab') === 'register' ? 'register' : 'login');

function redirectAfterLogin(user) {
  const next = new URLSearchParams(location.search).get('next');
  if (next && next.startsWith('/') && !next.startsWith('//')) {
    location = next;
  } else {
    location = user.role === 'client' ? '/cabinet' : '/staff';
  }
}

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  hideError(form);
  const fd = new FormData(form);
  try {
    const data = await api('/api/login', { method: 'POST', body: { email: fd.get('email'), password: fd.get('password') } });
    redirectAfterLogin(data.user);
  } catch (err) { showError(form, err.message); }
});

$('#register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  hideError(form);
  const fd = new FormData(form);
  try {
    const data = await api('/api/register', { method: 'POST', body: { name: fd.get('name'), email: fd.get('email'), phone: fd.get('phone'), password: fd.get('password') } });
    redirectAfterLogin(data.user);
  } catch (err) { showError(form, err.message); }
});