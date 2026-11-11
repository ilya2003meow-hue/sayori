const eventsList = $('#events-list');
const eventForm = $('#event-form');
const isLoggedIn = !!$('#logout-btn');
const canManageEvents = ['admin', 'owner'].includes(document.body.dataset.userRole);
let eventSyncBusy = false;

const eventText = {
  empty: tr('events_empty'),
  reply: tr('event_reply'),
  comment: tr('event_comment_label'),
  commentPlaceholder: tr('event_comment_placeholder'),
  send: tr('event_comment_submit'),
  login: tr('event_login_to_comment'),
  remove: tr('event_delete'),
  removeConfirm: tr('event_delete_confirm'),
  datePrefix: tr('event_date_prefix'),
  noComments: tr('event_no_comments'),
};
let lastEventsSnapshot = '';


function eventDate(value) {
  const parsed = new Date(String(value || '').replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return String(value || '');
  return parsed.toLocaleString(NUM_LOCALE, { dateStyle: 'medium', timeStyle: 'short' });
}

function commentMarkup(comment, isReply = false) {
  const replies = (comment.replies || []).map((reply) => commentMarkup(reply, true)).join('');
  return `<article class="event-comment${isReply ? ' event-comment-reply' : ''}" data-comment-id="${Number(comment.id)}">
    <div class="event-comment-head"><strong>${esc(comment.author_name || '')}</strong><time>${esc(eventDate(comment.created_at))}</time></div>
    <p>${esc(comment.text || '')}</p>
    ${isLoggedIn && !isReply ? `<button class="event-reply-toggle" type="button" data-reply-toggle="${Number(comment.id)}">${esc(eventText.reply)}</button>` : ''}
    ${!isReply ? `<div class="event-replies">${replies}</div>` : ''}
    ${!isReply && isLoggedIn ? `<form class="event-reply-form hidden" data-reply-form="${Number(comment.id)}">
      <textarea name="text" rows="2" required minlength="2" maxlength="1500" placeholder="${esc(eventText.commentPlaceholder)}"></textarea>
      <div class="form-error hidden"></div>
      <button class="btn btn-ghost btn-sm" type="submit">${esc(eventText.send)}</button>
    </form>` : ''}
  </article>`;
}

function eventMarkup(item) {
  const photos = (item.photos || []).map((photo, index) =>
    `<a class="event-photo" href="/${esc(photo)}" target="_blank" rel="noopener"><img src="/${esc(photo)}" alt="${esc(item.title)} — ${index + 1}" loading="lazy"></a>`
  ).join('');
  const comments = (item.comments || []).map((comment) => commentMarkup(comment)).join('');
  const loginPrompt = !isLoggedIn ? `<p class="event-login-prompt"><a href="/login?next=/events">${esc(eventText.login)}</a></p>` : '';
  const commentForm = isLoggedIn ? `<form class="event-comment-form" data-event-comment-form="${Number(item.id)}">
      <label>${esc(eventText.comment)}
        <textarea name="text" rows="2" required minlength="2" maxlength="1500" placeholder="${esc(eventText.commentPlaceholder)}"></textarea>
      </label>
      <div class="form-error hidden"></div>
      <button class="btn btn-ghost btn-sm" type="submit">${esc(eventText.send)}</button>
    </form>` : loginPrompt;
  return `<article class="event-card" data-event-id="${Number(item.id)}">
    <div class="event-card-header">
      <div><h2>${esc(item.title)}</h2><div class="event-meta">${esc(eventText.datePrefix)} ${esc(eventDate(item.created_at))} · ${esc(item.author_name || 'Princess Spa')}</div></div>
      ${canManageEvents ? `<button class="btn btn-danger btn-sm" type="button" data-delete-event="${Number(item.id)}">${esc(eventText.remove)}</button>` : ''}
    </div>
    <div class="event-gallery">${photos}</div>
    <p class="event-description">${esc(item.description)}</p>
    <section class="event-discussion" aria-label="${esc(eventText.comment)}">
      <h3>${esc(eventText.comment)}${(item.comments || []).length ? ` (${item.comments.length})` : ''}</h3>
      <div class="event-comments">${comments || `<p class="muted event-no-comments">${esc(eventText.noComments)}</p>`}</div>
      ${commentForm}
    </section>
  </article>`;
}

function renderEvents(rows) {
  const snapshot = JSON.stringify(rows);
  if (snapshot === lastEventsSnapshot) return;

  // Keep text people are typing if a new post or reply arrives during polling.
  const draftValues = new Map();
  eventsList.querySelectorAll('form[data-event-comment-form], form[data-reply-form]').forEach((form) => {
    const key = form.dataset.eventCommentForm ? `event:${form.dataset.eventCommentForm}` : `reply:${form.dataset.replyForm}`;
    draftValues.set(key, form.elements.text?.value || '');
  });
  const focused = document.activeElement;
  let focusKey = null;
  if (focused?.form?.dataset?.eventCommentForm) focusKey = `event:${focused.form.dataset.eventCommentForm}`;
  if (focused?.form?.dataset?.replyForm) focusKey = `reply:${focused.form.dataset.replyForm}`;

  if (!rows.length) {
    eventsList.innerHTML = `<div class="empty-state">${esc(eventText.empty)}</div>`;
  } else {
    eventsList.innerHTML = rows.map(eventMarkup).join('');
  }
  draftValues.forEach((value, key) => {
    const [kind, id] = key.split(':');
    const selector = kind === 'event' ? `[data-event-comment-form="${CSS.escape(id)}"]` : `[data-reply-form="${CSS.escape(id)}"]`;
    const textarea = eventsList.querySelector(`${selector} textarea`);
    if (textarea) textarea.value = value;
  });
  if (focusKey) {
    const [kind, id] = focusKey.split(':');
    const selector = kind === 'event' ? `[data-event-comment-form="${CSS.escape(id)}"]` : `[data-reply-form="${CSS.escape(id)}"]`;
    eventsList.querySelector(`${selector} textarea`)?.focus({ preventScroll: true });
  }
  lastEventsSnapshot = snapshot;
}

async function loadEvents() {
  if (!eventsList || eventSyncBusy || document.visibilityState !== 'visible') return;
  eventSyncBusy = true;
  try {
    const rows = await api('/api/events', { cache: 'no-store' });
    renderEvents(rows);
  } catch (err) {
    if (!eventsList.querySelector('.event-card')) {
      eventsList.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    }
  } finally {
    eventSyncBusy = false;
  }
}

async function postComment(form, eventId, parentId = null) {
  hideError(form);
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    await api(`/api/events/${eventId}/comments`, {
      method: 'POST', body: { text: form.elements.text.value, parent_id: parentId },
    });
    form.elements.text.value = '';
    await loadEvents();
    toast(tr('event_comment_success'));
  } catch (err) {
    showError(form, err.message);
  } finally {
    submit.disabled = false;
  }
}

if (eventForm) {
  const photoInput = eventForm.elements.photos;
  const selection = $('#event-photo-selection');
  photoInput.addEventListener('change', () => {
    const files = [...photoInput.files];
    selection.textContent = files.length ? files.map((file) => file.name).join(' · ') : '';
    if (files.length > 5) {
      photoInput.setCustomValidity(tr('event_photos_hint'));
    } else {
      photoInput.setCustomValidity('');
    }
  });
  eventForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideError(eventForm);
    if (!eventForm.reportValidity()) return;
    const submit = eventForm.querySelector('[type="submit"]');
    const files = [...photoInput.files];
    if (!files.length || files.length > 5) {
      showError(eventForm, tr('event_photos_hint'));
      return;
    }
    submit.disabled = true;
    try {
      const response = await fetch('/api/events', { method: 'POST', body: new FormData(eventForm) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || tr('err_server'));
      eventForm.reset();
      selection.textContent = '';
      await loadEvents();
      toast(tr('event_publish_success'));
      eventsList.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      showError(eventForm, err.message);
    } finally {
      submit.disabled = false;
    }
  });
}

if (eventsList) {
  eventsList.addEventListener('click', async (event) => {
    const replyButton = event.target.closest('[data-reply-toggle]');
    if (replyButton) {
      const form = eventsList.querySelector(`[data-reply-form="${CSS.escape(replyButton.dataset.replyToggle)}"]`);
      form?.classList.toggle('hidden');
      form?.querySelector('textarea')?.focus();
      return;
    }
    const deleteButton = event.target.closest('[data-delete-event]');
    if (deleteButton && canManageEvents) {
      if (!confirm(eventText.removeConfirm)) return;
      deleteButton.disabled = true;
      try {
        await api(`/api/events/${deleteButton.dataset.deleteEvent}`, { method: 'DELETE' });
        await loadEvents();
        toast(tr('event_delete_success'));
      } catch (err) {
        toast(err.message, true);
        deleteButton.disabled = false;
      }
    }
  });

  eventsList.addEventListener('submit', async (event) => {
    const topLevelForm = event.target.closest('[data-event-comment-form]');
    if (topLevelForm) {
      event.preventDefault();
      await postComment(topLevelForm, Number(topLevelForm.dataset.eventCommentForm));
      return;
    }
    const replyForm = event.target.closest('[data-reply-form]');
    if (replyForm) {
      event.preventDefault();
      const eventCard = replyForm.closest('[data-event-id]');
      await postComment(replyForm, Number(eventCard.dataset.eventId), Number(replyForm.dataset.replyForm));
    }
  });
}

loadEvents();
setInterval(loadEvents, 5000);
