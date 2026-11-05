// Ad placements stay in header and sidebar only; nothing is inserted into the fishing list.
// Once Google AdSense approves this domain, replace the two labeled placeholders
// with correctly sized MANUAL AdSense ad units. Do not enable automatic in-content ads.
(() => {
  'use strict';
  document.querySelectorAll('[data-jump-filter]').forEach(link => {
    link.addEventListener('click', () => {
      const tab = document.querySelector('.tab[data-filter="' + link.dataset.jumpFilter + '"]');
      if (tab) tab.click();
    });
  });
})();
