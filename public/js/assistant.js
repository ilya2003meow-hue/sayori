(function () {
  const fab = $('#chat-fab');
  const panel = $('#chat-panel');
  const msgs = $('#chat-msgs');
  const suggests = $('#chat-suggests');
  const form = $('#chat-form');
  const input = $('#chat-text');
  let started = false;
  let busy = false;
  let controller = null;
  let generation = 0;
  const send = form.querySelector('.chat-send');

  function addMsg(text, who, link) {
    const el = document.createElement('div');
    el.className = 'msg ' + who;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    const body = document.createElement('div');
    body.className = 'msg-text';
    body.textContent = text;
    bubble.appendChild(body);
    if (link && link.url) {
      const a = document.createElement('a');
      a.className = 'msg-link';
      a.href = link.url;
      a.textContent = link.label || link.url;
      bubble.appendChild(a);
    }
    el.appendChild(bubble);
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    const el = document.createElement('div');
    el.className = 'msg bot typing';
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    for (let i = 0; i < 3; i++) {
      const dot = document.createElement('span');
      dot.className = 'dot';
      bubble.appendChild(dot);
    }
    el.appendChild(bubble);
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
  }

  function renderSuggests(list) {
    suggests.innerHTML = '';
    (list || []).forEach((s) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'suggest';
      b.textContent = s;
      b.addEventListener('click', () => ask(s));
      suggests.appendChild(b);
    });
    msgs.scrollTop = msgs.scrollHeight;
  }

  function openPanel() {
    panel.classList.remove('hidden');
    fab.classList.add('hidden');
    input.focus();
  }
  function closePanel() {
    panel.classList.add('hidden');
    fab.classList.remove('hidden');
  }

  async function ask(text) {
    if (busy) return;
    busy = true;
    send.disabled = true;
    const current = generation;
    controller = new AbortController();
    if (text) addMsg(text, 'user');
    renderSuggests([]);
    const typing = showTyping();
    try {
      const data = await api('/api/assistant', {
        method: 'POST', body: { message: text }, signal: controller.signal,
      });
      if (current !== generation) return;
      typing.remove();
      addMsg(data.reply, 'bot', data.link);
      renderSuggests(data.suggestions);
    } catch (err) {
      if (current !== generation || err.name === 'AbortError') return;
      typing.remove();
      addMsg(tr('assistant_error'), 'bot');
      if (!text) started = false;
    } finally {
      if (current === generation) {
        busy = false;
        send.disabled = false;
        controller = null;
      }
    }
  }

  function greet() {
    if (started) return;
    started = true;
    ask('');
  }

  fab.addEventListener('click', () => { openPanel(); greet(); });
  $('#chat-close').addEventListener('click', closePanel);
  $('#chat-clear').addEventListener('click', () => {
    if (!confirm(tr('assistant_clear_confirm'))) return;
    generation++;
    controller?.abort();
    controller = null;
    busy = false;
    started = false;
    send.disabled = false;
    msgs.replaceChildren();
    suggests.replaceChildren();
    input.value = '';
    greet();
    input.focus();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.classList.contains('hidden')) closePanel();
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = '';
    ask(text);
  });
})();