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
    if (age > 5) return {label: `Report may be outdated · last updated ${time} ET`, status:'warn', short:'Delayed update'};
    return {label: `Latest report update: ${time} ET · refreshes approximately every 3 hours`, status:'ok', short:'Recently updated'};
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

  function card(loc) {
    const report = getReport(loc.key);
    const score = report ? report.score : null;
    const cls = level(score);
    const danger = report && (report.hazards || []).length > 0;
    const note = loc.is_pier ? 'MARYLAND PIER / DOCK' : 'FISHING LOCATION';
    const desc = weatherCond(report);
    const crab = report && report.blue_crab_score != null ? `Crab ${Math.round(report.blue_crab_score)}/100` : 'Blue crab';
    return `<button type="button" class="spot-card" data-key="${escapeHTML(loc.key)}" aria-label="Open report for ${escapeHTML(loc.name)}">
      <span class="score-box ${cls}"><strong>${readableScore(score)}</strong><small>${score == null ? 'NO DATA' : danger ? 'CAUTION' : cls === 'good' ? 'GOOD' : cls === 'mid' ? 'FAIR' : 'POOR'}</small></span>
      <span class="spot-copy"><span class="spot-kicker">${note}</span><span class="spot-title" style="display:block">${escapeHTML(loc.short_name)}</span><span class="spot-desc" style="display:block">${escapeHTML(loc.name)}</span><span class="tags">${loc.has_blue_crab ? `<span class="tag crab">♧ ${escapeHTML(crab)}</span>` : ''}${danger ? '<span class="tag danger">⚑ Weather caution</span>' : ''}${!report || report.status === 'unavailable' ? '<span class="tag pending">Awaiting data</span>' : `<span class="tag">${escapeHTML(desc)}</span>`}</span></span>
      <span class="card-arrow" aria-hidden="true">↗</span>
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
