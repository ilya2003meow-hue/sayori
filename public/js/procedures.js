$('#category-filters').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-cat]');
  if (!btn) return;
  $$('#category-filters .filter-chip').forEach((b) => b.classList.toggle('active', b === btn));
  const cat = btn.dataset.cat;
  let visible = 0;
  $$('#procedures-grid .proc-card').forEach((card) => {
    const show = cat === 'Все' || card.dataset.category === cat;
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  $('#no-procedures').classList.toggle('hidden', visible > 0);
});