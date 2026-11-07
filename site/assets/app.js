(() => {
  'use strict';
  const app = { locations: [], reports: new Map(), generated: null, tab: 'all', search: '', species: 'all', sort: 'best', shown: 18, visible: [], map: null, markers: null, current: null };
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const escapeHTML = text => String(text == null ? '' : text).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const value = n => Number.isFinite(Number(n)) && n !== null && n !== undefined ? Math.round(Number(n)) : null;
  const fmt = (n, unit = '') => n === undefined || n === null || Number.isNaN(Number(n)) ? '—' : `${Number(n).toLocaleString()}${unit}`;
  const byKey = key => app.locations.find(loc => loc.key === key);
  const getReport = key => app.reports.get(key) || null;
  const level = score => score === null || score === undefined ? 'pending' : score >= 65 ? 'good' : score >= 40 ? 'mid' : 'low';
  const readableScore = n => n == null ? '—' : String(Math.round(n));
  const weatherCond = report => report && report.weather_text && report.weather_text !== 'Weather unavailable' ? report.weather_text : 'Conditions pending';
  const allFilters = {all: () => true, piers: loc => loc.is_pier, crab: loc => loc.has_blue_crab};

  function freshness() {
    if (!app.generated) return {label: 'Awaiting first live update', status: 'neutral', short: 'Pending update'};
    const age = (Date.now() - new Date(app.generated).getTime()) / 3600000;
    if (!Number.isFinite(age) || age < -0.5) return {label: 'Report timestamp unavailable', status: 'warn', short: 'Check status'};
    const time = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}).format(new Date(app.generated));
    if (age > 3) return {label: `Report may be outdated · last updated ${time} ET`, status:'warn', short:'Delayed update'};
    return {label: `Latest report update: ${time} ET · scheduled to refresh hourly`, status:'ok', short:'Recently updated'};
  }

  function compact(n, suffix = '') { return n == null || !Number.isFinite(Number(n)) ? '—' : `${Math.round(Number(n))}${suffix}`; }
  function pickReferenceReport() {
    const keys = ['annapolis_bay','jonas_green_pier','sandy_point_bay_bridge'];
    for (const key of keys) { const rep = app.reports.get(key); if (rep && rep.temperature_f != null) return rep; }
    return [...app.reports.values()].find(r => r && r.temperature_f != null) || null;
  }
  function renderTop() {
    const piers = app.locations.filter(x => x.is_pier).length;
    const crab = app.locations.filter(x => x.has_blue_crab).length;
    $('#statLocations').textContent = app.locations.length;
    $('#statPiers').textContent = piers;
    $('#statCrab').textContent = crab;
    $('#allTabCount').textContent = app.locations.length;
    $('#pierTabCount').textContent = piers;
    $('#crabTabCount').textContent = crab;
    const recent = freshness();
    $('#heroStatus').innerHTML = `<span class="status-dot ${recent.status === 'ok' ? '' : recent.status}"></span>${escapeHTML(recent.label)}`;
    $('#statUpdated').textContent = recent.short;
    $('#year').textContent = new Date().getFullYear();

    // Use only real generated data. The reference picture is visual guidance, not a data source.
    const scored = [...app.reports.values()].filter(r => r && Number.isFinite(Number(r.score)) && r.score != null);
    const regionalIndex = scored.length ? Math.round(scored.reduce((sum,r) => sum+Number(r.score),0)/scored.length) : null;
    $('#overallScore').innerHTML = regionalIndex == null ? '—<em>/100</em>' : `${regionalIndex}<em>/100</em>`;
    const species = new Map();
    scored.forEach(r => (r.species_scores || []).forEach(item => {
      if (item.score == null || !Number.isFinite(Number(item.score))) return;
      const clean = String(item.name).replace(/\s+(seasonally|nearby)$/i,'').trim();
      const prev = species.get(clean) || {sum:0,count:0};
      prev.sum += Number(item.score); prev.count++;
      species.set(clean,prev);
    }));
    const betNames = [...species.entries()].filter(([name,v]) => v.count >= 2 && !/blue crab/i.test(name))
      .sort((a,b)=>b[1].sum/b[1].count-a[1].sum/a[1].count).slice(0,3).map(([name])=>name);
    $('#bestBets').textContent = betNames.length ? betNames.join(' · ') : 'Waiting for reports';

    const rep = pickReferenceReport();
    $('#headerCurrentTemp').textContent = compact(rep && rep.temperature_f,'°F');
    $('#headerCurrentText').textContent = rep ? String(rep.weather_text || 'Latest available conditions').slice(0,24) : 'Conditions unavailable';
    $('#weatherCond').textContent = rep ? String(rep.weather_text || '—').slice(0,28) : '—';
    $('#weatherArea').textContent = rep && rep.key === 'annapolis_bay' ? 'Annapolis area' : 'Regional example';
    $('#weatherWind').textContent = compact(rep && rep.wind_mph,' mph');
    $('#weatherGust').textContent = `Gusts ${compact(rep && rep.wind_gust_mph,' mph')}`;
    $('#weatherPressure').textContent = rep && rep.pressure_hpa != null ? `${(Number(rep.pressure_hpa)*0.029529983).toFixed(2)} inHg` : '—';
    $('#weatherRain').textContent = compact(rep && rep.rain_chance_pct,'%');
    $('#weatherTide').textContent = rep && rep.tide_summary ? String(rep.tide_summary).slice(0,27) : '—';
    const crabs = [...app.reports.values()].map(r=>r.blue_crab_score).filter(v=>v != null && Number.isFinite(Number(v)));
    $('#weatherCrab').textContent = crabs.length ? `${Math.round(crabs.reduce((x,y)=>x+Number(y),0)/crabs.length)}/100` : '—';
  }

  function createSpeciesFilter() {
    const names = [...new Set(app.locations.flatMap(loc => loc.species || []).map(x => String(x).replace(/\s+(seasonally|nearby)$/i,'').trim()))].sort((a,b) => a.localeCompare(b));
    $('#speciesFilter').innerHTML = '<option value="all">All species</option>' + names.map(name => `<option value="${escapeHTML(name)}">${escapeHTML(name)}</option>`).join('');
  }

  function filterLocations() {
    const search = app.search.trim().toLowerCase();
    const fn = allFilters[app.tab] || allFilters.all;
    const rows = app.locations.filter(loc => fn(loc) &&
      (app.species === 'all' || loc.species.some(s => s.toLowerCase().includes(app.species.toLowerCase()))) &&
      (!search || [loc.name,loc.short_name,loc.note,...loc.species].join(' ').toLowerCase().includes(search)));
    if (app.sort === 'name') rows.sort((a,b) => a.name.localeCompare(b.name));
    else rows.sort((a,b) => {
      const rA = getReport(a.key), rB = getReport(b.key);
      const scoreA = rA && rA[app.sort === 'crab' ? 'blue_crab_score' : 'score'];
      const scoreB = rB && rB[app.sort === 'crab' ? 'blue_crab_score' : 'score'];
      if (scoreA == null && scoreB == null) return a.name.localeCompare(b.name);
      if (scoreA == null) return 1;
      if (scoreB == null) return -1;
      return scoreB - scoreA || a.name.localeCompare(b.name);
    });
    return rows;
  }

  function speciesIcon(name) {
    const n = String(name).toLowerCase();
    if (n.includes('crab')) return '🦀';
    if (n.includes('catfish')) return '🐟';
    if (n.includes('crappie')) return '🐟';
    if (n.includes('strip')) return '🐟';
    return '🐠';
  }
  function card(loc) {
    const report = getReport(loc.key);
    const score = report && report.score != null ? Number(report.score) : null;
    const cls = level(score);
    const danger = !!(report && (report.hazards || []).length);
    const species = report && report.species_scores && report.species_scores.length ? report.species_scores : (loc.species || []).map(name=>({name,score:null}));
    let displayed = species.filter(s=>s.name && !/blue crab/i.test(s.name)).slice(0,4);
    if (loc.has_blue_crab) displayed = displayed.concat([{name:'Blue crab',score:report ? report.blue_crab_score : null}]);
    const speciesHTML = displayed.map(sp=>`<span class="species-chip"><span class="species-emoji" aria-hidden="true">${speciesIcon(sp.name)}</span><span class="species-name">${escapeHTML(String(sp.name).replace(/\s+(seasonally|nearby)$/i,''))}</span><span class="species-rating ${level(sp.score)}">${readableScore(sp.score)}</span></span>`).join('');
    const tide = report && report.tide_summary ? String(report.tide_summary).slice(0,42) : 'Not available for this location';
    const conditions = report ? `<span>💧 Water temp: <b>${compact(report.water_temp_f,'°F')}</b></span><span>≋ Wind: <b>${compact(report.wind_mph,' mph')}</b></span><span>◷ Tide: <b>${escapeHTML(tide)}</b></span>` : '<span>Conditions not yet available</span>';
    const imgSrc = /bridge|mchenry|annapolis|jonas|romancoke|matapeake/i.test(loc.key) ? 'bridgeview.webp' : 'pier.webp';
    return `<button type="button" class="spot-card ${danger ? 'caution-card' : ''}" data-key="${escapeHTML(loc.key)}" aria-label="Open full fishing report for ${escapeHTML(loc.name)}">
      <span class="spot-image" aria-hidden="true"><img src="assets/${imgSrc}" alt="" loading="lazy"><span>Illustration</span></span>
      <span class="spot-core"><span class="spot-name">${escapeHTML(loc.short_name)}</span><span class="spot-subtitle">⌖ ${escapeHTML(loc.name)}</span><span class="spot-data-row"><span class="score-box ${cls}"><small>Fishing rating</small><strong>${readableScore(score)}<em>/100</em></strong></span><span class="species-chips">${speciesHTML}</span></span></span>
      <span class="spot-conditions">${conditions}<span class="view-report">View full report →</span></span>
    </button>`;
  }

  function renderResults() {
    app.visible = filterLocations();
    $('#resultCount').textContent = `SHOWING ${app.visible.length} LOCATION${app.visible.length === 1 ? '' : 'S'}`;
    const subset = app.visible.slice(0,app.shown);
    $('#locationList').innerHTML = subset.length ? subset.map(card).join('') +
      (subset.length < app.visible.length ? `<button type="button" id="showMore" class="button ghost" style="width:100%;justify-content:center;margin-top:10px">Show more locations (${app.visible.length - subset.length} remaining) ↓</button>` : '') :
      '<div class="empty-state">No matching locations. Try a different search, species, or filter.</div>';
    renderMap();
  }

  function startMap() {
    if (!window.L) { $('#map').innerHTML = '<p class="map-fallback">Map tiles need an internet connection. Searchable location reports remain available.</p>'; return; }
    $('#map').innerHTML = '';
    app.map = L.map('map', {scrollWheelZoom: false}).setView([39.05, -76.45], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 17, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(app.map);
    app.markers = L.layerGroup().addTo(app.map);
    setTimeout(() => app.map.invalidateSize(), 90);
  }

  function renderMap() {
    if (!app.map || !app.markers) return;
    app.markers.clearLayers();
    const bounds = [];
    for (const loc of app.visible) {
      const report = getReport(loc.key);
      const color = level(report ? report.score : null);
      const icon = L.divIcon({html: `<span class="custom-map-dot ${color}"></span>`, iconSize: [16,16], iconAnchor:[8,8],className:'fishing-pin'});
      const marker = L.marker([loc.lat,loc.lon], {icon, title:loc.name});
      marker.on('click', () => openDetail(loc.key));
      marker.addTo(app.markers);
      bounds.push([loc.lat,loc.lon]);
    }
    if (bounds.length > 1) app.map.fitBounds(bounds,{padding:[20,20],maxZoom:10});
    else if (bounds.length === 1) app.map.setView(bounds[0],10);
  }

  function sourceLinks(report) {
    const urls = report && report.source_urls || {};
    const labels = {nws:'NWS hourly forecast', noaa:'NOAA tide predictions', usgs:'USGS stream gauge', open_meteo:'Open-Meteo forecast'};
    return Object.entries(labels).map(([key,label]) => {
      const link = urls[key];
      if (!link || !/^https:\/\//.test(link)) return '';
      return `<a class="drawer-link" href="${escapeHTML(link)}" target="_blank" rel="noopener noreferrer">${escapeHTML(label)} ↗</a>`;
    }).join('');
  }

  function openDetail(key) {
    const loc = byKey(key);
    if (!loc) return;
    app.current = key;
    const rep = getReport(key);
    const score = rep && rep.score != null ? rep.score : null;
    const crabScore = rep && rep.blue_crab_score != null ? rep.blue_crab_score : null;
    const warnings = rep && rep.hazards || [];
    const reasons = rep && rep.reasons || [];
    const alerts = rep && rep.alerts || [];
    const values = rep ? [
      ['Air temperature',fmt(rep.temperature_f,'°F')], ['Wind',fmt(rep.wind_mph,' mph')],
      ['Wind gusts',fmt(rep.wind_gust_mph,' mph')], ['Rain chance (next 3h)',fmt(rep.rain_chance_pct,'%')],
      ['Pressure',fmt(rep.pressure_hpa,' hPa')],['Water temperature',fmt(rep.water_temp_f,'°F')],
      ['Gauge flow',fmt(rep.flow_cfs,' CFS')],['Blue crab',crabScore == null ? '—' : `${Math.round(crabScore)}/100`]
    ] : [];
    const reportTime = freshness();
    const species = rep && rep.species_scores && rep.species_scores.length ? rep.species_scores : (loc.species || []).map(s => ({name:s,score:null}));
    const sourceSection = sourceLinks(rep);
    $('#drawerBody').innerHTML = `
      <div class="drawer-label">${loc.is_pier ? 'MARYLAND FISHING PIER / DOCK' : 'FISHING LOCATION'} · CONDITIONS REPORT</div>
      <h2 class="drawer-title" id="drawerTitle">${escapeHTML(loc.short_name)}</h2>
      <p class="drawer-meta">${escapeHTML(loc.name)}</p>
      <div class="drawer-score"><strong class="${level(score)}">${readableScore(score)}${score != null ? '<small style="font-size:17px;color:#9ec2c0"> / 100</small>' : ''}</strong><span>${score == null ? 'Live report not yet available.' : 'Modeled fishing activity index. Actual catches vary.'}<br><small>${escapeHTML(reportTime.label)}</small></span></div>
      <p class="drawer-meta">${escapeHTML(loc.note)}</p>
      ${score == null ? '<div class="drawer-callout">No current source data for this location. Do not treat this as a live forecast.</div>' : ''}
      ${rep && rep.status === 'partial' ? '<div class="drawer-callout">Some source providers did not respond. This is a partial conditions estimate.</div>' : ''}
      ${warnings.map(s => `<div class="drawer-callout danger">⚑ ${escapeHTML(s)}</div>`).join('')}
      ${alerts.map(a => `<div class="drawer-callout danger">NWS ${escapeHTML(a.event)} ${a.severity ? '('+escapeHTML(a.severity)+')' : ''}</div>`).join('')}
      <h3 class="drawer-heading">Weather & water</h3>
      <div class="drawer-grid">${values.map(([label,val]) => `<div class="drawer-cell"><small>${escapeHTML(label)}</small><strong>${escapeHTML(val)}</strong></div>`).join('') || '<div class="drawer-cell"><small>Data</small><strong>Awaiting update</strong></div>'}</div>
      ${rep && rep.tide_summary ? `<div class="drawer-callout">Tide: ${escapeHTML(rep.tide_summary)}<br><small>Regional station estimate, not a measurement at this exact pier.</small></div>` : ''}
      ${rep && rep.weather_text ? `<p class="drawer-meta" style="margin-top:13px">Forecast: ${escapeHTML(rep.weather_text)}</p>` : ''}
      <h3 class="drawer-heading">Species activity</h3>
      ${species.map(s => `<div class="species-row"><span>${escapeHTML(s.name)}</span><div style="text-align:right"><b>${s.score == null ? '—' : `${Math.round(s.score)}/100`}</b><div class="species-bar"><span class="${level(s.score)}" style="width:${Math.max(0,Math.min(100,s.score || 0))}%"></span></div></div></div>`).join('')}
      ${reasons.length ? `<h3 class="drawer-heading">What's influencing the score</h3>${reasons.map(r => `<div class="reason">${escapeHTML(r)}</div>`).join('')}` : ''}
      <h3 class="drawer-heading">Location & source links</h3>
      <a class="drawer-link" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc.lat + ',' + loc.lon)}" target="_blank" rel="noopener noreferrer">View location on Google Maps ↗</a>
      ${sourceSection}
      <p class="drawer-footnote">This is an estimated activity rating, not an observed catch report, fishing safety advisory, pier-opening confirmation, or legal authorization to harvest. Check official rules and posted access restrictions before travel. Water temperature may be estimated from weather rather than measured.</p>`;
    $('#drawerBackdrop').hidden = false;
    $('#detailsDrawer').hidden = false;
    document.body.classList.add('drawer-open');
    $('#closeDrawer').focus();
    try { const url = new URL(location.href); url.searchParams.set('spot',key); history.replaceState(null,'',url); } catch (_) {}
  }

  function closeDetail() {
    $('#detailsDrawer').hidden = true;
    $('#drawerBackdrop').hidden = true;
    document.body.classList.remove('drawer-open');
    if (app.current) {
      const element = $$('[data-key]').find(x => x.dataset.key === app.current);
      if (element) element.focus();
    }
    app.current = null;
    try { const url = new URL(location.href); url.searchParams.delete('spot'); history.replaceState(null,'',url); } catch (_) {}
  }

  function bind() {
    $$('.tab').forEach(el => el.addEventListener('click', () => {
      app.tab = el.dataset.filter;
      app.shown = 18;
      $$('.tab').forEach(t => { t.classList.toggle('active',t===el);t.setAttribute('aria-pressed',t===el?'true':'false'); });
      renderResults();
    }));
    $('#locationSearch').addEventListener('input', event => {app.search=event.target.value; app.shown=18; renderResults();});
    $('#speciesFilter').addEventListener('change', event => {app.species=event.target.value;app.shown=18;renderResults();});
    $('#sortBy').addEventListener('change', event => {app.sort=event.target.value;renderResults();});
    $('#locationList').addEventListener('click', event => {
      const card = event.target.closest('[data-key]');
      if (card) openDetail(card.dataset.key);
      if (event.target.closest('#showMore')) {app.shown+=18;renderResults();}
    });
    $('#resetMap').addEventListener('click', () => {if (app.map && app.visible.length) renderMap();});
    $('#closeDrawer').addEventListener('click',closeDetail);
    $('#drawerBackdrop').addEventListener('click',closeDetail);
    window.addEventListener('keydown',event => {if(event.key==='Escape' && !$('#detailsDrawer').hidden) closeDetail();});
  }

  async function init() {
    bind();
    startMap();
    try {
      const [locResponse, reportsResponse] = await Promise.all([
        fetch('data/locations.json', {cache:'no-cache'}),
        fetch('data/reports.json', {cache:'no-cache'}),
      ]);
      if (!locResponse.ok) throw new Error('Location directory could not be loaded');
      const directory = await locResponse.json();
      app.locations = directory.locations || [];
      if (reportsResponse.ok) {
        const data = await reportsResponse.json();
        app.generated = data.generated_at || null;
        app.reports = new Map((data.reports || []).map(row => [row.key,row]));
      }
      createSpeciesFilter();
      renderTop();
      renderResults();
      const target = new URLSearchParams(location.search).get('spot');
      if (target && byKey(target)) openDetail(target);
    } catch (error) {
      $('#heroStatus').textContent = 'Location directory unavailable. Try reloading.';
      $('#locationList').innerHTML = `<div class="empty-state">Unable to load the website data. Check your connection and try again.<br><small>${escapeHTML(error.message)}</small></div>`;
    }
  }
  init();
})();

/* Automatically reload when new fishing reports are published */
(() => {
  let lastUpdate = null;
  let checking = false;

  async function checkForUpdates() {
    if (checking || document.hidden) return;
    checking = true;

    try {
      const response = await fetch(
        'data/reports.json?refresh=' + Date.now(),
        { cache: 'no-store' }
      );

      if (!response.ok) return;

      const data = await response.json();
      const latest = data.generated_at;

      if (!latest) return;

      if (lastUpdate && latest !== lastUpdate) {
        window.location.reload();
        return;
      }

      lastUpdate = latest;
    } catch (error) {
      console.warn('Fishing report update check failed:', error);
    } finally {
      checking = false;
    }
  }

  window.addEventListener('load', checkForUpdates);
  setInterval(checkForUpdates, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkForUpdates();
  });
})();
