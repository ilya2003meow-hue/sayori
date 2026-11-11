const reviewsList = $('.reviews-list');
const reviewForm = $('#review-form');
const isLoggedIn = !!$('#logout-btn');
const isAdmin = document.body.dataset.userRole === 'admin';
let syncInFlight = false;

function makeStarIcon() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'icon');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M12 2l2.4 7.2H22l-6 4.6 2.3 7.2-6.3-4.5-6.3 4.5L8 13.8 2 9.2h7.6z');
  path.setAttribute('fill', 'currentColor');
  svg.append(path);
  return svg;
}

function makeReply(reply) {
  const item = document.createElement('div');
  item.className = 'reply-item';
  item.dataset.replyId = String(reply.id);

  const head = document.createElement('div');
  head.className = 'reply-head';
  const author = document.createElement('span');
  author.className = 'reply-author';
  author.textContent = reply.author_name || '';
  const role = document.createElement('span');
  role.className = 'reply-role';
  role.textContent = tr(`role_${reply.author_role || 'admin'}`);
  head.append(author, role);

  const text = document.createElement('p');
  text.textContent = reply.text || '';
  item.append(head, text);
  return item;
}

function addReplyToCard(card, reply) {
  let replies = card.querySelector('.review-replies');
  if (!replies) {
    replies = document.createElement('div');
    replies.className = 'review-replies';
    const form = card.querySelector('.reply-form, .reply-login');
    if (form) card.insertBefore(replies, form);
    else card.append(replies);
  }
  if (replies.querySelector(`[data-reply-id="${CSS.escape(String(reply.id))}"]`)) return;
  replies.append(makeReply(reply));
}

function makeReviewCard(review) {
  const card = document.createElement('article');
  card.className = 'review-card';
  card.dataset.reviewCard = String(review.id);

  const stars = document.createElement('div');
  stars.className = 'review-stars';
  for (let i = 1; i <= 5; i += 1) {
    const star = document.createElement('span');
    if (i > Number(review.rating || 0)) star.className = 'dim';
    star.append(makeStarIcon());
    stars.append(star);
  }

  const text = document.createElement('p');
  text.textContent = review.text || '';
  const author = document.createElement('div');
  author.className = 'review-author';
  author.textContent = review.name || '';
  card.append(stars, text, author);

  if (isAdmin) {
    const remove = document.createElement('button');
    remove.className = 'btn btn-danger btn-sm';
    remove.type = 'button';
    remove.dataset.deleteReview = String(review.id);
    remove.textContent = tr('btn_delete');
    card.append(remove);
  }

  (review.replies || []).forEach((reply) => addReplyToCard(card, reply));

  if (isLoggedIn) {
    const form = document.createElement('form');
    form.className = 'reply-form';
    form.dataset.reviewId = String(review.id);
    const textarea = document.createElement('textarea');
    textarea.name = 'text';
    textarea.rows = 2;
    textarea.required = true;
    textarea.minLength = 2;
    textarea.maxLength = 1000;
    textarea.placeholder = tr('reply_placeholder');
    const error = document.createElement('div');
    error.className = 'form-error hidden';
    const submit = document.createElement('button');
    submit.className = 'btn btn-ghost btn-sm';
    submit.type = 'submit';
    submit.textContent = tr('reply_submit');
    form.append(textarea, error, submit);
    card.append(form);
  } else {
    const login = document.createElement('a');
    login.className = 'reply-login';
    login.href = '/login?next=/reviews';
    login.textContent = tr('reply_login');
    card.append(login);
  }

  return card;
}

function insertReview(review) {
  if (!reviewsList) return;
  const key = String(review.id);
  if (reviewsList.querySelector(`[data-review-card="${CSS.escape(key)}"]`)) return;
  reviewsList.querySelector('.reviews-empty')?.remove();
  reviewsList.prepend(makeReviewCard(review));
}

function syncReplies(card, replies) {
  (replies || []).forEach((reply) => addReplyToCard(card, reply));
}

async function refreshReviews() {
  if (!reviewsList || syncInFlight || document.visibilityState !== 'visible') return;
  syncInFlight = true;
  try {
    const latest = await api('/api/reviews?limit=50', { cache: 'no-store' });
    // Add oldest unseen entries first so the newest review remains at the top.
    latest.slice().reverse().forEach((review) => insertReview(review));
    const latestIds = new Set(latest.map((review) => String(review.id)));
    latest.forEach((review) => {
      const card = reviewsList.querySelector(`[data-review-card="${CSS.escape(String(review.id))}"]`);
      if (card) syncReplies(card, review.replies);
    });
    reviewsList.querySelectorAll('[data-review-card]').forEach((card) => {
      if (!latestIds.has(String(card.dataset.reviewCard))) card.remove();
    });
    if (!reviewsList.querySelector('[data-review-card]') && !reviewsList.querySelector('.reviews-empty')) {
      const empty = document.createElement('div');
      empty.className = 'empty-state reviews-empty';
      empty.textContent = tr('reviews_empty');
      reviewsList.append(empty);
    }
  } catch (_) {
    // Keep the already-rendered reviews visible when the network is temporarily unavailable.
  } finally {
    syncInFlight = false;
  }
}

if (reviewForm) {
  reviewForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    hideError(form);
    const fd = new FormData(form);
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const review = await api('/api/reviews', {
        method: 'POST',
        body: { rating: Number(fd.get('rating')), text: fd.get('text') },
      });
      insertReview(review);
      form.reset();
      toast(tr('toast_reviewed'));
    } catch (err) {
      showError(form, err.message);
    } finally {
      submit.disabled = false;
    }
  });
}

if (reviewsList) {
  reviewsList.addEventListener('submit', async (event) => {
    const form = event.target.closest('.reply-form');
    if (!form) return;
    event.preventDefault();
    hideError(form);
    const fd = new FormData(form);
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const reply = await api(`/api/reviews/${encodeURIComponent(form.dataset.reviewId)}/replies`, {
        method: 'POST', body: { text: fd.get('text') },
      });
      const card = form.closest('[data-review-card]');
      if (card) addReplyToCard(card, reply);
      form.reset();
      toast(tr('toast_replied'));
    } catch (err) {
      showError(form, err.message);
    } finally {
      submit.disabled = false;
    }
  });

  reviewsList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete-review]');
    if (!button || button.disabled || !confirm(tr('confirm_delete_review'))) return;
    button.disabled = true;
    try {
      await api(`/api/admin/reviews/${encodeURIComponent(button.dataset.deleteReview)}`, { method: 'DELETE' });
      button.closest('[data-review-card]')?.remove();
      if (!reviewsList.querySelector('[data-review-card]')) {
        const empty = document.createElement('div');
        empty.className = 'empty-state reviews-empty';
        empty.textContent = tr('reviews_empty');
        reviewsList.append(empty);
      }
    } catch (err) {
      toast(err.message, true);
      button.disabled = false;
    }
  });

  // Other visitors see new reviews and staff replies without refreshing the page.
  refreshReviews();
  window.setInterval(refreshReviews, 3000);
}
