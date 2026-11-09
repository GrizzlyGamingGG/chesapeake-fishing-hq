/* Chesapeake Fishing HQ — approved community catches from the home-hosted forum.
 * Read-only. Photos are uploaded/moderated at forum.chesapeakefishinghq.com.
 * The main GitHub Pages website remains fully usable while the PC is offline.
 */
(() => {
  'use strict';
  const FORUM = 'https://forum.chesapeakefishinghq.com';
  const styles = `
    .community-catches .community-catch-title{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-bottom:16px}
    .community-catches .community-catch-title h2{margin:0;color:#f2fbfc;font-weight:800;font-size:clamp(20px,2.3vw,29px)}
    .community-catches .community-catch-title p{color:#a9c7d3;margin:5px 0 0}
    .community-catches .community-catch-link{border:1px solid #2e899e;background:#11394b;color:#f2ffff;font-size:14px;font-weight:700;padding:10px 14px;text-decoration:none;border-radius:8px;white-space:nowrap}
    .community-catches .community-catch-link:hover{background:#18576b;color:#fff}
    .community-catches .community-catch-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
    .community-catches .community-catch-card{overflow:hidden;display:block;border:1px solid #295267;border-radius:12px;background:#09273b;text-decoration:none;color:#e5f6fb;transition:transform .12s,border-color .12s}
    .community-catches .community-catch-card:hover{transform:translateY(-2px);border-color:#4ca9bf}
    .community-catches .community-catch-photo{display:block;width:100%;aspect-ratio:4 / 3;object-fit:cover;background:#163c51}
    .community-catches .community-catch-copy{display:flex;flex-direction:column;gap:4px;padding:12px}
    .community-catches .community-catch-copy strong{color:#fff;font-size:17px}
    .community-catches .community-catch-copy span{color:#bfd4da;font-size:13px}
    .community-catches .community-catch-empty{border:1px dashed #456c80;border-radius:10px;padding:20px;color:#b6d4da;background:#0b2a3c}
    @media(max-width:850px){.community-catches .community-catch-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:530px){.community-catches .community-catch-grid{grid-template-columns:1fr}}
  `;

  const make = (tag, cls, content) => {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (content != null) element.textContent = content;
    return element;
  };

  function addTab() {
    const nav = document.querySelector('.top-nav');
    if (!nav || nav.querySelector('a[href="#community-catches"]')) return;
    const tab = make('a', '', '📸  Catch Gallery');
    tab.href = '#community-catches';
    const forumTab = nav.querySelector('a[href*="forum.chesapeakefishinghq.com"]');
    if (forumTab) forumTab.insertAdjacentElement('afterend', tab);
    else nav.appendChild(tab);
  }

  function checkedURL(path) {
    if (typeof path !== 'string' || !path.startsWith('/catches/')) return null;
    try {
      const url = new URL(path, FORUM);
      return url.origin === FORUM ? url.href : null;
    } catch (_) { return null; }
  }

  async function loadCatches(section, status, gallery) {
    status.textContent = 'Loading recent community catches…';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch(FORUM + '/api/catches?limit=6', {
        mode: 'cors', cache: 'no-store', credentials: 'omit', signal: controller.signal
      });
      if (!response.ok) throw Error('Forum unavailable');
      const result = await response.json();
      const rows = Array.isArray(result.catches) ? result.catches : [];
      const valid = rows.filter(r => checkedURL(r.image_path) && checkedURL(r.detail_path));
      gallery.replaceChildren();
      if (!valid.length) {
        status.textContent = 'No community catches yet. Be the first to share your fishing photo!';
        return;
      }
      status.textContent = 'Fresh catches shared by Chesapeake anglers';
      valid.forEach(row => {
        const link = make('a', 'community-catch-card');
        link.href = checkedURL(row.detail_path);
        const img = make('img', 'community-catch-photo');
        img.src = checkedURL(row.image_path);
        img.alt = `Community photo: ${String(row.species || 'fishing catch')}`;
        img.loading = 'lazy';
        const copy = make('span', 'community-catch-copy');
        copy.append(make('strong','',row.species || 'Fish catch'));
        copy.append(make('span','',`${row.area || 'Chesapeake Bay'} · Bait: ${row.bait || 'Not specified'}`));
        copy.append(make('span','',`📸 ${row.username || 'Community angler'}`));
        link.append(img,copy);
        gallery.appendChild(link);
      });
    } catch (_) {
      gallery.replaceChildren(make('div','community-catch-empty','The catch gallery is temporarily unavailable while the community forum is offline. Fishing reports and weather remain available.'));
      status.textContent = 'Catch photos are hosted on the community forum';
    } finally { clearTimeout(timer); }
  }

  function init() {
    const target = document.querySelector('.dashboard-main #map-section');
    if (!target || document.getElementById('community-catches')) return;
    const sheet = make('style'); sheet.textContent = styles;
    document.head.appendChild(sheet);
    addTab();
    const section = make('section', 'workbench community-catches');
    section.id = 'community-catches';
    section.setAttribute('aria-label', 'Recent community catch photos');
    const heading = make('div', 'community-catch-title');
    const intro = make('div');
    intro.append(make('h2', '', '📸 Recent Community Catches'));
    const status = make('p', '', 'Loading approved fish photos…');
    status.setAttribute('aria-live', 'polite');
    intro.appendChild(status);
    const button = make('a', 'community-catch-link', 'View gallery / Post your catch');
    button.href = FORUM + '/catches';
    heading.append(intro, button);
    const gallery = make('div', 'community-catch-grid');
    section.append(heading, gallery);
    target.before(section);
    loadCatches(section, status, gallery);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
