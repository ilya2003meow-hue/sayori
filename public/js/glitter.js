/* Постоянные хаотичные искры Princess Spa. Не блокируют нажатия и прокрутку. */
(() => {
  const initGlitter = () => {
    const layer = document.getElementById('glitter-layer');
    if (!layer || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    // Достаточно мелких частиц, чтобы мерцание было постоянным, но не перегружало телефон.
    const count = window.matchMedia('(max-width: 640px)').matches ? 18 : 30;
    const random = (min, max) => Math.random() * (max - min) + min;
    const colors = ['pink', 'gold', 'white', 'lavender'];

    for (let i = 0; i < count; i += 1) {
      const particle = document.createElement('span');
      particle.className = 'glitter-particle';
      particle.setAttribute('aria-hidden', 'true');
      const color = colors[Math.floor(Math.random() * colors.length)];
      particle.dataset.tone = color;
      particle.style.setProperty('--x', `${random(1, 99).toFixed(2)}%`);
      particle.style.setProperty('--y', `${random(2, 98).toFixed(2)}%`);
      particle.style.setProperty('--size', `${random(7, 15).toFixed(1)}px`);
      particle.style.setProperty('--duration', `${random(2.8, 7.2).toFixed(2)}s`);
      particle.style.setProperty('--delay', `${random(-7.2, 0).toFixed(2)}s`);
      particle.style.setProperty('--dx', `${random(-42, 42).toFixed(1)}px`);
      particle.style.setProperty('--dy', `${random(-55, 55).toFixed(1)}px`);
      particle.style.setProperty('--turn', `${random(-220, 220).toFixed(0)}deg`);
      particle.style.setProperty('--peak', random(0.42, 0.95).toFixed(2));
      layer.appendChild(particle);
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGlitter, { once: true });
  } else {
    initGlitter();
  }
})();
