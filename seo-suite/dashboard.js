(function () {
  'use strict';

  const PROPERTIES = {
    vantagecircle: { label: 'Vantage Circle', domain: 'vantagecircle.com' },
    vantagefit: { label: 'Vantage Fit', domain: 'vantagefit.io' },
  };
  const NOT_FOUND = 101;
  const INTENT_SHORT = { informational: 'info', navigational: 'nav', commercial: 'com', transactional: 'trans' };
  const COMPETITOR_TYPES = [
    ['', 'All types'],
    ['new_page', 'New page'],
    ['content_update', 'Content update'],
    ['title_change', 'Title change'],
    ['meta_change', 'Meta change'],
    ['h1_change', 'H1 change'],
    ['schema_change', 'Schema change'],
    ['redirect', 'Redirect'],
    ['page_removed', 'Page removed'],
    ['url_case_change', 'URL case change'],
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtNum(n) {
    if (n === null || n === undefined || n === '') return '';
    return Number(n).toLocaleString();
  }

  function fmtPos(pos) {
    if (pos === null || pos === undefined || pos >= NOT_FOUND) return '—';
    return String(pos);
  }

  function intentHtml(intentJson) {
    let flags = {};
    try { flags = JSON.parse(intentJson || '{}'); } catch (e) {}
    const labels = [];
    for (const [name, short] of Object.entries(INTENT_SHORT)) {
      if (flags[name]) labels.push(short);
    }
    if (!labels.length) return '<td class="sub">—</td>';
    return '<td>' + labels.map(function (l) { return '<span class="feat-chip">' + esc(l) + '</span>'; }).join(' ') + '</td>';
  }

  // Position cell + separate delta cell. Returns both plus the numeric
  // change value used for sorting the Δ column.
  function posCell(prev, cur, hasPrev) {
    const curS = fmtPos(cur);
    const posHtml = '<td class="num"><b>' + curS + '</b></td>';
    if (!hasPrev) return { posHtml: posHtml, deltaHtml: '<td class="num sub">—</td>', change: '' };
    if (prev === null && cur === null) return { posHtml: '<td class="num">—</td>', deltaHtml: '<td class="num sub">—</td>', change: '' };
    if (prev === null) {
      return { posHtml: posHtml, deltaHtml: '<td class="num"><span class="pos-chip new">New</span></td>', change: String(NOT_FOUND - cur) };
    }
    if (cur === null) {
      return { posHtml: '<td class="num">—</td>', deltaHtml: '<td class="num"><span class="pos-chip down">out</span> <span class="sub">from ' + prev + '</span></td>', change: String(prev - NOT_FOUND) };
    }
    const d = prev - cur;
    let chip;
    if (d > 0) chip = '<span class="pos-chip up">▲' + d + '</span>';
    else if (d < 0) chip = '<span class="pos-chip down">▼' + Math.abs(d) + '</span>';
    else chip = '<span class="pos-chip flat">·</span>';
    const prevS = d ? ' <span class="sub">from ' + prev + '</span>' : '';
    return { posHtml: posHtml, deltaHtml: '<td class="num">' + chip + prevS + '</td>', change: String(d) };
  }

  async function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    const res = await fetch('/api/' + path, init);
    if (!res.ok) {
      const text = await res.text().catch(function () { return 'unknown error'; });
      throw new Error(res.status + ' ' + text);
    }
    return res.json();
  }

  function errorCard(message) {
    return '<div class="card" style="color:var(--rose)"><b>Error</b><p class="sub">' + esc(message) + '</p></div>';
  }

  function stampHtml(dayText) {
    return dayText ? '<div class="panel-stamp">Data as of ' + esc(dayText) + '</div>' : '';
  }

  // ---------------------------------------------------------------- summary
  const ACTION_TYPE_META = {
    rank_drop: { icon: '▼', cls: 'action-rank_drop' },
    freshness: { icon: '◷', cls: 'action-freshness' },
    llm_loss: { icon: '◈', cls: 'action-llm_loss' },
    backlink_lost: { icon: '◉', cls: 'action-backlink_lost' },
    competitor_change: { icon: '◆', cls: 'action-competitor_change' },
  };

  function renderActionDigest(actions, generatedAt) {
    if (!actions || !actions.length) {
      return '<div class="card action-digest"><b>Urgent actions</b><p class="sub">No urgent actions this week.</p></div>';
    }
    const sorted = actions.slice().sort(function (a, b) { return (b.priority || 0) - (a.priority || 0); });
    const top = sorted.slice(0, 12);
    const rows = top.map(function (a) {
      const meta = ACTION_TYPE_META[a.type] || { icon: '•', cls: 'action-other' };
      return '<div class="action-row ' + esc(meta.cls) + '" data-link="' + esc(a.link || '') + '">' +
        '<span class="action-badge">' + esc(meta.icon) + '</span>' +
        '<div class="action-body"><div class="action-title">' + esc(a.title) + '</div>' +
        '<div class="action-detail sub">' + esc(a.detail || '') + '</div></div></div>';
    }).join('');
    return '<div class="card action-digest"><b>Urgent actions</b>' + rows +
      '<p class="sub">Generated ' + esc(generatedAt || '—') + '</p></div>';
  }

  function renderAnnotations(list) {
    const today = new Date().toISOString().slice(0, 10);
    const rows = (list || []).map(function (a) {
      return '<div class="annotation-row">' +
        '<span class="annotation-day">' + esc(a.day || '') + '</span>' +
        '<span class="annotation-label chip">' + esc(a.label || '') + '</span>' +
        '<span class="annotation-note">' + esc(a.note || '') + '</span></div>';
    }).join('');
    return '<div class="card annotations-card"><b>Annotations</b>' +
      '<form class="annotation-form">' +
      '<input type="date" name="day" value="' + esc(today) + '" required>' +
      '<input type="text" name="label" placeholder="Label" required>' +
      '<textarea name="note" placeholder="Note…" rows="1"></textarea>' +
      '<button type="submit">Add annotation</button></form>' +
      '<div class="annotation-list">' + (rows || '<p class="sub">No annotations yet.</p>') + '</div></div>';
  }

  async function loadSummary() {
    const el = document.getElementById('panel-summary');
    try {
      const [data, actionsData, annotationsData] = await Promise.all([
        api('summary'),
        api('actions').catch(function () { return { actions: [], generated_at: '' }; }),
        api('annotations?days=90').catch(function () { return { annotations: [] }; }),
      ]);
      const cards = [];

      // rank KPIs across properties
      let totalRanked = 0, totalTop3 = 0, totalTop10 = 0, totalTop50 = 0, totalCount = 0;
      let latestDay = '';
      for (const [prop, info] of Object.entries(data.rank || {})) {
        totalRanked += info.ranked || 0;
        totalTop3 += info.top3 || 0;
        totalTop10 += info.top10 || 0;
        totalTop50 += info.top50 || 0;
        totalCount += info.count || 0;
        if (info.latest_day && info.latest_day > latestDay) latestDay = info.latest_day;
      }
      if (totalCount) {
        cards.push([
          esc(String(totalTop3)),
          'keywords in Google top 3<br>' + esc(String(totalTop10)) + ' in top 10 · ' + esc(String(totalTop50)) + ' in top 50<br><span class="sub">' + esc(String(totalRanked)) + '/' + esc(String(totalCount)) + ' ranked' + (latestDay ? ' (' + esc(latestDay) + ')' : '') + '</span>'
        ]);
      }

      if (data.biggest_mover) {
        const m = data.biggest_mover;
        const cls = m.delta > 0 ? 'up' : 'down';
        const arrow = m.delta > 0 ? '▲' : '▼';
        cards.push([
          '<span class="delta ' + cls + '">' + arrow + Math.abs(m.delta) + '</span>',
          'biggest rank move vs previous check<br>' + esc((m.keyword || '').slice(0, 60)) + '<br><span class="sub">' + esc(PROPERTIES[m.property]?.label || m.property) + '</span>'
        ]);
      }

      if (data.backlinks?.latest) {
        const bl = data.backlinks.latest;
        const prev = data.backlinks.previous;
        let delta = '<span class="sub">first run</span>';
        if (prev) {
          const net = (bl.refdomains || 0) - (prev.refdomains || 0);
          const cls = net >= 0 ? 'up' : 'down';
          const arrow = net >= 0 ? '+' : '-';
          delta = '<span class="delta ' + cls + '">' + arrow + esc(fmtNum(Math.abs(net))) + ' vs ' + esc(prev.day) + '</span>';
        }
        cards.push([esc(fmtNum(bl.refdomains)), 'referring domains<br>' + delta]);
      }

      if (data.llm?.day) {
        cards.push([
          esc(String(data.llm.sov) + '%'),
          'AI share of voice<br><span class="sub">' + esc(data.llm.day) + ' · ' + esc(String(data.llm.count)) + ' answers</span>'
        ]);
      }

      if (!cards.length) {
        el.innerHTML = '<div class="card">No summary data available yet.</div>';
        return;
      }

      const kpiHtml = cards.map(function (c) {
        return '<div class="kpi"><div class="num">' + c[0] + '</div><div class="label">' + c[1] + '</div></div>';
      }).join('');

      el.innerHTML = '<h2>Executive summary</h2><div class="kpis">' + kpiHtml + '</div>' +
        renderActionDigest(actionsData.actions, actionsData.generated_at) +
        renderAnnotations(annotationsData.annotations) +
        stampHtml(latestDay);

      // Action digest navigation
      el.querySelectorAll('.action-row').forEach(function (row) {
        row.addEventListener('click', function () {
          const link = row.getAttribute('data-link');
          if (link && link.startsWith('#')) location.hash = link;
        });
      });

      // Annotation form
      const form = el.querySelector('.annotation-form');
      if (form) {
        form.addEventListener('submit', async function (e) {
          e.preventDefault();
          const day = form.querySelector('[name="day"]').value;
          const label = form.querySelector('[name="label"]').value;
          const note = form.querySelector('[name="note"]').value;
          try {
            await api('annotations', { method: 'POST', body: { day: day, label: label, note: note } });
            const fresh = await api('annotations?days=90');
            const listEl = el.querySelector('.annotation-list');
            if (listEl) {
              const rows = (fresh.annotations || []).map(function (a) {
                return '<div class="annotation-row">' +
                  '<span class="annotation-day">' + esc(a.day || '') + '</span>' +
                  '<span class="annotation-label chip">' + esc(a.label || '') + '</span>' +
                  '<span class="annotation-note">' + esc(a.note || '') + '</span></div>';
              }).join('');
              listEl.innerHTML = rows || '<p class="sub">No annotations yet.</p>';
            }
            form.reset();
            form.querySelector('[name="day"]').value = new Date().toISOString().slice(0, 10);
          } catch (err) {
            alert('Failed to add annotation: ' + err.message);
          }
        });
      }
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- rank tracker
  function renderCannibalization(c) {
    if (!c) return '';
    const hasDilution = c.dilution && c.dilution.length;
    const hasFlips = c.url_flips && c.url_flips.length;
    if (!hasDilution && !hasFlips) return '';

    let dilutionRows = '';
    if (hasDilution) {
      dilutionRows = c.dilution.map(function (r) {
        return '<tr><td><a href="' + esc(r.url) + '" target="_blank">' + esc(r.url.replace(/^https?:\/\//, '').slice(0, 70)) + '</a></td>' +
          '<td class="num">' + esc(String(r.keyword_count)) + '</td>' +
          '<td class="sub">' + esc((r.keywords || []).join(', ')) + '</td></tr>';
      }).join('');
    }

    let flipRows = '';
    if (hasFlips) {
      flipRows = c.url_flips.map(function (r) {
        return '<tr><td>' + esc(r.keyword) + '</td>' +
          '<td class="sub"><a href="' + esc(r.previous_url) + '" target="_blank">' + esc(r.previous_url.replace(/^https?:\/\//, '').slice(0, 50)) + '</a></td>' +
          '<td class="sub"><a href="' + esc(r.current_url) + '" target="_blank">' + esc(r.current_url.replace(/^https?:\/\//, '').slice(0, 50)) + '</a></td></tr>';
      }).join('');
    }

    return '<div class="card cannibalization"><b>Cannibalization check · ' + esc(c.latest_day || '—') + '</b>' +
      (hasDilution ? '<table><thead><tr><th>Pages ranking for 5+ keywords</th><th>Keywords</th><th>Keyword list</th></tr></thead><tbody>' + dilutionRows + '</tbody></table>' : '') +
      (hasFlips ? '<table><thead><tr><th>Keyword that changed URL</th><th>Previous URL</th><th>Current URL</th></tr></thead><tbody>' + flipRows + '</tbody></table>' : '') +
      '</div>';
  }

  function renderRankProp(data, cannibalization) {
    const cfg = PROPERTIES[data.property] || { label: data.property, domain: data.property };
    const tags = (data.meta && data.meta.tags) ? data.meta.tags : [];
    const tagOptions = tags.map(function (t) { return '<option value="' + esc(t.toLowerCase()) + '">' + esc(t) + '</option>'; }).join('');

    const rows = data.keywords.map(function (k) {
      const hasPrev = data.previous_day !== null && k.previous_position !== undefined;
      const pos = posCell(k.previous_position, k.position, hasPrev);
      const shortUrl = (k.url || '').replace(/^https?:\/\//, '').slice(0, 50);
      const vol = k.volume;
      const kd = k.kd;
      let state = '';
      if (hasPrev) {
        if (k.previous_position === null && k.position !== null) state = 'new';
        else if (k.position === null && k.previous_position !== null) state = 'out';
        else if (k.position !== null && k.previous_position !== null) {
          const dd = k.previous_position - k.position;
          state = dd > 0 ? 'up' : dd < 0 ? 'down' : 'flat';
        }
      }
      const hist = (k.history || []).slice().reverse(); // oldest → latest
      const spark = hist.length > 1
        ? '<span class="spark" title="position history, oldest to latest">' + hist.map(function (p) {
            if (p === null || p === undefined) return '<i class="gap" style="height:2px"></i>';
            return '<i style="height:' + Math.max(2, Math.round((101 - Math.min(p, 100)) * 18 / 100)) + 'px"></i>';
          }).join('') + '</span>'
        : '<span class="sub">—</span>';
      return '<tr data-keyword="' + esc((k.keyword || '').toLowerCase()) + '" ' +
        'data-search="' + esc(((k.keyword || '') + ' ' + (k.tag || '')).toLowerCase()) + '" ' +
        'data-tag="' + esc((k.tag || '').toLowerCase()) + '" ' +
        'data-position="' + (k.position === null ? '' : esc(String(k.position))) + '" ' +
        'data-change="' + esc(pos.change) + '" ' +
        'data-volume="' + (vol === null || vol === undefined ? '' : esc(String(vol))) + '" ' +
        'data-kd="' + (kd === null || kd === undefined ? '' : esc(String(kd))) + '" ' +
        'data-state="' + state + '" ' +
        'data-url="' + esc(k.url || '') + '">' +
        '<td>' + esc(k.keyword) + '</td>' +
        '<td class="tag-cell">' + esc(k.tag) + '</td>' +
        pos.posHtml +
        pos.deltaHtml +
        '<td>' + spark + '</td>' +
        '<td class="num">' + (vol !== null && vol !== undefined ? fmtNum(vol) : '<span class="sub">—</span>') + '</td>' +
        '<td class="num">' + (kd !== null && kd !== undefined ? Math.round(kd) : '<span class="sub">—</span>') + '</td>' +
        intentHtml(k.intent) +
        '<td>' + (k.branded ? '<span class="badge-b">B</span>' : '') + '</td>' +
        '<td class="sub">' + (k.url ? '<a href="' + esc(k.url) + '" target="_blank" rel="noopener">' + esc(shortUrl) + '</a>' : '') + '</td></tr>';
    }).join('');

    return '<div class="rank-prop" id="rank-' + esc(data.property) + '">' +
      '<div class="card">' +
      '<div class="table-tools no-print">' +
      '<input class="rank-search" type="search" placeholder="Search keywords or tags…">' +
      '<select class="tag-filter"><option value="">All tags</option>' + tagOptions + '<option value="__untagged__">Untagged</option></select>' +
      '<span class="qchips">' +
      '<button class="qchip active" data-q="">All</button>' +
      '<button class="qchip" data-q="up">▲ Moved up</button>' +
      '<button class="qchip" data-q="down">▼ Dropped</button>' +
      '<button class="qchip" data-q="new">New</button>' +
      '<button class="qchip" data-q="out">Out of top 100</button>' +
      '</span>' +
      '<button class="rank-export" type="button">Export CSV</button>' +
      '<span class="rank-count sub">' + esc(String(data.keywords.length)) + ' keywords</span></div>' +
      '<table class="rank-table"><thead><tr>' +
      '<th class="sortable" data-sort="keyword">Keyword <span class="arrow"></span></th>' +
      '<th>Tag</th>' +
      '<th class="sortable" data-sort="position">Position <span class="arrow"></span></th>' +
      '<th class="sortable" data-sort="change">Δ <span class="arrow"></span></th>' +
      '<th>Trend</th>' +
      '<th class="sortable" data-sort="volume">Volume <span class="arrow"></span></th>' +
      '<th class="sortable" data-sort="kd">KD <span class="arrow"></span></th>' +
      '<th>Intent</th><th>Branded</th><th>URL</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>' +
      '<p class="sub">Google US top 100 for ' + esc(cfg.domain) + ' — current: ' + esc(data.latest_day || '—') +
      (data.previous_day ? ', previous: ' + esc(data.previous_day) : '') +
      '. Δ = position change vs previous check (gains on top when sorted). Trend = weekly positions, oldest to latest. Volume / KD / intent from keyword_meta. — = unranked or no data. ' +
      '<span class="no-print">Type to filter, pick a tag or quick filter, click a column header to sort.</span></p>' +
      '</div>' + renderCannibalization(cannibalization) + '</div>';
  }

  async function loadRank() {
    const el = document.getElementById('panel-rank');
    try {
      const [circle, fit, canCircle, canFit] = await Promise.all([
        api('rank?property=vantagecircle'),
        api('rank?property=vantagefit'),
        api('cannibalization?property=vantagecircle').catch(function () { return null; }),
        api('cannibalization?property=vantagefit').catch(function () { return null; }),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle, can: canCircle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit, can: canFit },
      ];

      const anyData = tabs.some(function (t) { return t.data.keywords && t.data.keywords.length; });
      if (!anyData) {
        el.innerHTML = '<div class="card">No rank data available yet.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        return renderRankProp(t.data, t.can).replace('class="rank-prop"', 'class="rank-prop' + (i === 0 ? ' active' : '') + '"');
      }).join('');

      const rankDay = [circle.latest_day, fit.latest_day].filter(Boolean).sort().pop();
      el.innerHTML = '<h2>Rank Tracker · Google US top 100</h2>' + tabHtml + panelsHtml + stampHtml(rankDay);
      initPropTabs(el, 'rank-prop');
      initRankInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- backlinks
  function shortDomain(url) {
    try {
      const u = new URL(url);
      return u.hostname.replace(/^www\./, '');
    } catch (e) {
      return url;
    }
  }

  function renderBacklinkTab(label, id, html) {
    return '<div class="bl-section' + (id === 'overview' ? ' active' : '') + '" id="bl-' + id + '">' + html + '</div>';
  }

  function drScore(rank) {
    return Math.min(100, Math.round((rank || 0) / 10));
  }

  function drGaugeHtml(score) {
    const pct = Math.min(100, Math.max(0, score));
    const color = pct >= 70 ? '#059669' : pct >= 40 ? '#d97706' : '#dc2626';
    return '<div class="dr-gauge"><svg viewBox="0 0 36 36">' +
      '<path class="dr-ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />' +
      '<path class="dr-ring-fill" stroke="' + color + '" stroke-dasharray="' + pct + ', 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />' +
      '</svg><div class="dr-num">' + esc(String(score)) + '</div></div>';
  }

  function renderBacklinkProfile(prop, snap, previous, events) {
    const cfg = PROPERTIES[prop] || { label: prop, domain: prop };
    const score = drScore(snap.rank);
    const prevSnap = previous || {};
    const blDelta = (snap.backlinks || 0) - (prevSnap.backlinks || 0);
    const rdDelta = (snap.refdomains || 0) - (prevSnap.refdomains || 0);
    function deltaHtml(delta) {
      if (!prevSnap.day) return '<span class="bl-delta first">first run</span>';
      const cls = delta >= 0 ? 'up' : 'down';
      const sign = delta >= 0 ? '+' : '';
      return '<span class="bl-delta ' + cls + '">' + sign + esc(fmtNum(delta)) + ' vs ' + esc(prevSnap.day) + '</span>';
    }
    let newCount = 0, lostCount = 0;
    for (const e of events) {
      if (e.property === prop && e.domain === '(total)') {
        if (e.event === 'new') newCount = e.rank || 0;
        if (e.event === 'lost') lostCount = e.rank || 0;
      }
    }
    const chips = '<span class="chip you">+' + esc(fmtNum(newCount)) + ' new</span>' +
      '<span class="chip none">-' + esc(fmtNum(lostCount)) + ' lost</span>';
    return '<div class="bl-profile">' +
      drGaugeHtml(score) +
      '<div class="bl-profile-meta"><div class="bl-profile-title">' + esc(cfg.label) + '</div>' +
      '<div class="bl-profile-domain">' + esc(cfg.domain) + '</div>' +
      '<div class="bl-profile-dr">DR (DFS) ' + esc(String(score)) + '</div></div>' +
      '<div class="bl-stat"><div class="bl-stat-num">' + esc(fmtNum(snap.backlinks)) + '</div>' +
      '<div class="bl-stat-label">Backlinks ' + deltaHtml(blDelta) + '</div></div>' +
      '<div class="bl-stat"><div class="bl-stat-num">' + esc(fmtNum(snap.refdomains)) + '</div>' +
      '<div class="bl-stat-label">Referring domains ' + deltaHtml(rdDelta) + '</div></div>' +
      '<div class="bl-chips">' + chips + '</div></div>';
  }

  async function loadBacklinks() {
    const el = document.getElementById('panel-backlinks');
    try {
      const data = await api('backlinks');
      const snaps = data.snapshots || [];
      const events = data.events || [];

      if (!snaps.length) {
        el.innerHTML = '<h2>Backlinks</h2><div class="card">No backlink data available yet.</div>';
        return;
      }

      // ---- Overview tab
      const latestByProp = {}, previousByProp = {};
      for (const r of snaps) {
        if (!latestByProp[r.property]) latestByProp[r.property] = r;
        else if (!previousByProp[r.property]) previousByProp[r.property] = r;
      }
      const profileCards = Object.keys(latestByProp).sort().map(function (prop) {
        return renderBacklinkProfile(prop, latestByProp[prop], previousByProp[prop], events);
      }).join('');

      const mx = Math.max.apply(null, snaps.map(function (r) { return r.refdomains || 0; }).concat([1]));
      const snapRows = snaps.map(function (r) {
        const label = (PROPERTIES[r.property] || { label: r.property || '—' }).label;
        return '<tr><td><b>' + esc(r.day) + '</b></td>' +
          '<td>' + esc(label) + '</td>' +
          '<td class="vol">' + fmtNum(r.backlinks) + '</td>' +
          '<td class="vol">' + fmtNum(r.refdomains) + '</td>' +
          '<td><div class="bar"><div style="width:' + ((r.refdomains || 0) / mx * 100).toFixed(0) + '%"></div></div></td>' +
          '<td>' + esc(r.rank) + '</td></tr>';
      }).join('');
      const overviewHtml = '<div class="bl-profile-wrap">' + profileCards + '</div>' +
        '<div class="card"><b>Profile totals</b><table>' +
        '<tr><th>date</th><th>property</th><th>backlinks</th><th>refdomains</th><th></th><th>DFS rank</th></tr>' +
        snapRows + '</table></div>' +
        (events.length ? renderBacklinkEvents(events) : '');

      // ---- Top Backlinks tab
      const detailsByProp = data.details || {};
      const topHtml = renderDetailTabs(detailsByProp, 'backlink');

      // ---- Referring Domains tab
      const domainsByProp = data.domains || {};
      const domainsHtml = renderDetailTabs(domainsByProp, 'domain');

      // ---- Anchor Text tab
      const anchorsByProp = data.anchors || {};
      const anchorsHtml = renderDetailTabs(anchorsByProp, 'anchor');

      // ---- Top pages by backlinks + broken pages tabs
      const pagesByProp = data.pages || {};
      const topPagesHtml = renderPageTabs(pagesByProp, 'top-pages');
      const brokenPagesHtml = renderPageTabs(pagesByProp, 'broken-pages');

      const tabs = [
        { id: 'overview', label: 'Overview' },
        { id: 'top', label: 'Top Backlinks' },
        { id: 'domains', label: 'Referring Domains' },
        { id: 'anchors', label: 'Anchor Text' },
        { id: 'pages', label: 'Top Pages by Backlinks' },
        { id: 'broken', label: 'Broken Pages' },
      ];
      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-bl="' + t.id + '">' + t.label + '</button>';
      }).join('') + '</div>';

      el.innerHTML = '<h2>Backlinks</h2>' + tabHtml +
        renderBacklinkTab('Overview', 'overview', overviewHtml) +
        renderBacklinkTab('Top Backlinks', 'top', topHtml) +
        renderBacklinkTab('Referring Domains', 'domains', domainsHtml) +
        renderBacklinkTab('Anchor Text', 'anchors', anchorsHtml) +
        renderBacklinkTab('Top Pages by Backlinks', 'pages', topPagesHtml) +
        renderBacklinkTab('Broken Pages', 'broken', brokenPagesHtml) +
        stampHtml(snaps[0].day);

      initBacklinkTabs(el);
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function renderBacklinkEvents(events) {
    const eventRows = events.slice(0, 40).map(function (r) {
      const chip = r.event === 'new' ? '<span class="chip you">new</span>' : '<span class="chip none">lost</span>';
      if (r.domain === '(total)') {
        return '<tr><td>' + esc(r.day) + '</td><td>' + chip + '</td><td class="sub">API aggregate count</td><td class="vol">' + esc(r.rank) + '</td></tr>';
      }
      return '<tr><td>' + esc(r.day) + '</td><td>' + chip + '</td><td>' + esc(r.domain) + '</td><td class="vol">' + (r.rank !== null && r.rank !== undefined ? esc(String(r.rank)) : '—') + '</td></tr>';
    }).join('');
    return '<div class="card"><b>Recent new / lost referring domains</b><table>' +
      '<tr><th>date</th><th>event</th><th>domain</th><th>rank</th></tr>' + eventRows + '</table>' +
      '<p class="sub">New/lost counts come from DataForSEO bulk endpoint. Per-domain detail is shown when the API provides it.</p></div>';
  }

  function renderDetailTabs(byProp, kind) {
    const props = Object.keys(byProp);
    if (!props.length) {
      return '<div class="card">No detailed data available yet. Run <code>python3 backlinks.py</code> to populate.</div>';
    }
    const hasBoth = props.length > 1;
    const tabBtns = hasBoth ? '<div class="prop-tabs sub-tabs no-print">' + props.map(function (p, i) {
      return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-blprop="' + esc(p) + '">' + esc((PROPERTIES[p] || { label: p }).label) + '</button>';
    }).join('') + '</div>' : '';

    const panels = props.map(function (p, i) {
      const rows = (byProp[p].rows || []);
      const day = byProp[p].day || '';
      let table = '';
      if (kind === 'backlink') {
        table = '<table class="backlink-detail-table">' +
          '<thead><tr><th>Source page</th><th>Target page</th><th>Anchor</th><th>Type</th><th>Rank</th></tr></thead><tbody>' +
          rows.slice(0, 1000).map(function (r) {
            const anchor = r.anchor || '<span class="sub">[empty]</span>';
            return '<tr data-search="' + esc((r.source_url + ' ' + r.target_url + ' ' + (r.anchor || '') + ' ' + r.domain).toLowerCase()) + '">' +
              '<td><a href="' + esc(r.source_url) + '" target="_blank" rel="noopener" class="sub">' + esc(shortDomain(r.source_url)) + '</a></td>' +
              '<td><a href="' + esc(r.target_url) + '" target="_blank" rel="noopener" class="sub">' + esc(shortDomain(r.target_url)) + '</a></td>' +
              '<td>' + anchor + '</td>' +
              '<td>' + (r.dofollow ? '<span class="chip you">dofollow</span>' : '<span class="chip none">nofollow</span>') + '</td>' +
              '<td class="num">' + esc(String(r.rank || '—')) + '</td></tr>';
          }).join('') + '</tbody></table>';
      } else if (kind === 'domain') {
        table = '<table class="backlink-detail-table">' +
          '<thead><tr><th>Domain</th><th>Backlinks</th><th>Ref IPs</th><th>Rank</th></tr></thead><tbody>' +
          rows.slice(0, 1000).map(function (r) {
            return '<tr data-search="' + esc(String(r.domain || '').toLowerCase()) + '">' +
              '<td>' + esc(r.domain || '—') + '</td>' +
              '<td class="num">' + fmtNum(r.backlinks || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.ref_ips || 0) + '</td>' +
              '<td class="num">' + esc(String(r.rank || '—')) + '</td></tr>';
          }).join('') + '</tbody></table>';
      } else if (kind === 'anchor') {
        table = '<table class="backlink-detail-table">' +
          '<thead><tr><th>Anchor text</th><th>Backlinks</th><th>Dofollow</th><th>% Dofollow</th></tr></thead><tbody>' +
          rows.slice(0, 100).map(function (r) {
            const pct = r.backlinks ? Math.round((r.dofollow_backlinks || 0) / r.backlinks * 100) : 0;
            return '<tr data-search="' + esc(String(r.anchor || '').toLowerCase()) + '">' +
              '<td>' + esc(r.anchor || '—') + '</td>' +
              '<td class="num">' + fmtNum(r.backlinks || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.dofollow_backlinks || 0) + '</td>' +
              '<td><div class="bar"><div style="width:' + pct + '%"></div></div> ' + pct + '%</td></tr>';
          }).join('') + '</tbody></table>';
      }
      const searchBox = kind === 'backlink' ? '<input type="search" class="bl-search" placeholder="Filter ' + rows.length + ' backlinks…" data-blsearch="' + esc(p) + '">' : '';
      return '<div class="bl-prop' + (i === 0 ? ' active' : '') + '" id="blprop-' + esc(p) + '-' + kind + '">' +
        '<div class="card">' + searchBox + table +
        '<p class="sub">Latest snapshot ' + esc(day) + ' · ' + rows.length + ' rows from DataForSEO.</p></div></div>';
    }).join('');

    return tabBtns + panels;
  }

  function renderPageTabs(byProp, kind) {
    const props = Object.keys(byProp);
    if (!props.length) {
      return '<div class="card">No page-level backlink data available yet. Run <code>python3 backlinks.py</code> to populate.</div>';
    }
    const hasBoth = props.length > 1;
    const tabBtns = hasBoth ? '<div class="prop-tabs sub-tabs no-print">' + props.map(function (p, i) {
      return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-blprop="' + esc(p) + '">' + esc((PROPERTIES[p] || { label: p }).label) + '</button>';
    }).join('') + '</div>' : '';

    const panels = props.map(function (p, i) {
      let rows = (byProp[p].rows || []);
      const day = byProp[p].day || '';
      if (kind === 'top-pages') {
        rows = rows.slice().sort(function (a, b) { return (b.backlinks || 0) - (a.backlinks || 0); });
      } else if (kind === 'broken-pages') {
        rows = rows.filter(function (r) { return (r.broken_backlinks || 0) > 0; })
          .sort(function (a, b) { return (b.broken_backlinks || 0) - (a.broken_backlinks || 0); });
      }
      const maxBl = Math.max.apply(null, rows.map(function (r) { return r.backlinks || 0; }).concat([1]));
      const maxBr = Math.max.apply(null, rows.map(function (r) { return r.broken_backlinks || 0; }).concat([1]));
      let table = '';
      if (kind === 'top-pages') {
        table = '<table class="backlink-detail-table bl-pages-table">' +
          '<thead><tr><th>Page URL</th><th>Backlinks</th><th>Ref domains</th><th>Dofollow</th><th>Nofollow</th><th>Broken BL</th><th>Rank</th><th>First seen</th></tr></thead><tbody>' +
          rows.slice(0, 1000).map(function (r) {
            const pct = Math.round(((r.backlinks || 0) / maxBl) * 100);
            return '<tr data-search="' + esc(String(r.url || '').toLowerCase()) + '">' +
              '<td><a href="' + esc(r.url || '') + '" target="_blank" rel="noopener">' + esc(shortDomain(r.url || '')) + '</a><br><span class="sub">' + esc(r.url || '') + '</span></td>' +
              '<td class="num"><b>' + fmtNum(r.backlinks || 0) + '</b><div class="bar"><div style="width:' + pct + '%"></div></div></td>' +
              '<td class="num">' + fmtNum(r.refdomains || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.dofollow_backlinks || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.nofollow_backlinks || 0) + '</td>' +
              '<td class="num">' + (r.broken_backlinks ? '<span class="chip none">' + fmtNum(r.broken_backlinks) + '</span>' : '—') + '</td>' +
              '<td class="num">' + esc(String(r.rank || '—')) + '</td>' +
              '<td class="num">' + esc(r.first_seen || '—') + '</td></tr>';
          }).join('') + '</tbody></table>';
      } else {
        table = '<table class="backlink-detail-table bl-pages-table">' +
          '<thead><tr><th>Page URL</th><th>Broken backlinks</th><th>Broken pages</th><th>Total backlinks</th><th>Ref domains</th><th>Rank</th><th>First seen</th></tr></thead><tbody>' +
          rows.slice(0, 1000).map(function (r) {
            const pct = Math.round(((r.broken_backlinks || 0) / maxBr) * 100);
            return '<tr data-search="' + esc(String(r.url || '').toLowerCase()) + '">' +
              '<td><a href="' + esc(r.url || '') + '" target="_blank" rel="noopener">' + esc(shortDomain(r.url || '')) + '</a><br><span class="sub">' + esc(r.url || '') + '</span></td>' +
              '<td class="num"><b>' + fmtNum(r.broken_backlinks || 0) + '</b><div class="bar"><div style="width:' + pct + '%"></div></div></td>' +
              '<td class="num">' + fmtNum(r.broken_pages || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.backlinks || 0) + '</td>' +
              '<td class="num">' + fmtNum(r.refdomains || 0) + '</td>' +
              '<td class="num">' + esc(String(r.rank || '—')) + '</td>' +
              '<td class="num">' + esc(r.first_seen || '—') + '</td></tr>';
          }).join('') + '</tbody></table>';
      }
      const searchBox = '<input type="search" class="bl-search" placeholder="Filter ' + rows.length + ' pages…" data-blsearch="' + esc(p) + '">';
      return '<div class="bl-prop' + (i === 0 ? ' active' : '') + '" id="blprop-' + esc(p) + '-' + kind + '">' +
        '<div class="card">' + searchBox + table +
        '<p class="sub">Latest snapshot ' + esc(day) + ' · ' + rows.length + ' pages from DataForSEO.</p></div></div>';
    }).join('');

    return tabBtns + panels;
  }

  function initBacklinkTabs(panelEl) {
    const tabs = panelEl.querySelectorAll('.prop-tab[data-bl]');
    const sections = panelEl.querySelectorAll('.bl-section');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        const id = tab.getAttribute('data-bl');
        tabs.forEach(function (t) { t.classList.toggle('active', t === tab); });
        sections.forEach(function (s) { s.classList.toggle('active', s.id === 'bl-' + id); });
      });
    });

    // Sub-tabs inside Top/Domain/Anchor tabs
    const subTabs = panelEl.querySelectorAll('.prop-tab[data-blprop]');
    const subProps = panelEl.querySelectorAll('.bl-prop');
    subTabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        const prop = tab.getAttribute('data-blprop');
        const parent = tab.closest('.bl-section');
        if (!parent) return;
        parent.querySelectorAll('.prop-tab[data-blprop]').forEach(function (t) {
          t.classList.toggle('active', t === tab);
        });
        parent.querySelectorAll('.bl-prop').forEach(function (p) {
          p.classList.toggle('active', p.id.startsWith('blprop-' + prop + '-'));
        });
      });
    });

    // Search inside top-backlinks tables
    panelEl.querySelectorAll('.bl-search').forEach(function (input) {
      input.addEventListener('input', function () {
        const q = input.value.toLowerCase();
        const prop = input.getAttribute('data-blsearch');
        const section = input.closest('.bl-section');
        section.querySelectorAll('tbody tr').forEach(function (tr) {
          tr.style.display = (tr.getAttribute('data-search') || '').includes(q) ? '' : 'none';
        });
      });
    });
  }

  // ---------------------------------------------------------------- LLM visibility
  function brandChips(mentionsJson, brands, you) {
    let m = {};
    try { m = JSON.parse(mentionsJson || '{}'); } catch (e) {}
    const found = brands.filter(function (b) { return m[b]; });
    if (!found.length) return '<span class="chip none">no brands</span>';
    return found.map(function (b) { return '<span class="chip ' + (b === you ? 'you' : '') + '">' + esc(b) + '</span>'; }).join(' ');
  }

  function renderLlmProp(data, gapsData) {
    const cfg = PROPERTIES[data.property] || { label: data.property, domain: data.property };
    const brands = data.brands || [];
    const you = data.you;
    let html = '';

    // SOV trend
    if (data.trend && data.trend.length) {
      const head = brands.map(function (b) { return '<th>' + esc(b) + (b === you ? ' (you)' : '') + '</th>'; }).join('');
      const body = data.trend.map(function (row) {
        const cells = brands.map(function (b) {
          const got = row[b] || 0;
          const total = row.total || 1;
          const pct = total ? Math.round((got / total) * 100) : 0;
          const cls = b === you ? 'bar you' : 'bar';
          return '<td><div class="' + cls + '"><div style="width:' + pct + '%"></div></div><span class="sub">' + pct + '%</span></td>';
        }).join('');
        return '<tr><td><b>' + esc(row.day) + '</b></td>' + cells + '</tr>';
      }).join('');
      html += '<h2>AI share of voice trend</h2><div class="card"><table><tr><th>run date</th>' + head + '</tr>' + body + '</table>' +
        '<p class="sub">% of prompt × platform answers mentioning each brand.</p></div>';
    }

    // Content gaps & briefs
    if (gapsData && gapsData.gaps && gapsData.gaps.length) {
      const gapRows = gapsData.gaps.map(function (g, idx) {
        const competitors = (g.competitors_mentioned || []).join(', ');
        const chips = (g.competitors_mentioned || []).map(function (c) {
          return '<span class="chip ' + (c === you ? 'you' : '') + '">' + esc(c) + '</span>';
        }).join(' ');
        return '<tr data-property="' + esc(data.property) + '" data-prompt="' + esc(g.prompt) + '" data-competitors="' + esc(competitors) + '" data-volume="' + esc(String(g.estimated_volume || '')) + '">' +
          '<td>' + esc(g.prompt) + '</td>' +
          '<td>' + (chips || '<span class="sub">—</span>') + '</td>' +
          '<td class="num">' + fmtNum(g.estimated_volume) + '</td>' +
          '<td class="num delta ' + (g.volume_delta >= 0 ? 'up' : 'down') + '">' + (g.volume_delta >= 0 ? '+' : '') + fmtNum(g.volume_delta) + '</td>' +
          '<td><button class="gap-brief" type="button">Copy brief</button></td></tr>';
      }).join('');
      html += '<h2>Content gaps & briefs</h2><div class="card"><table class="llm-gaps-table">' +
        '<thead><tr><th>Prompt</th><th>Competitors mentioned</th><th>Est. AI searches/mo</th><th>Δ vs last</th><th></th></tr></thead><tbody>' + gapRows + '</tbody></table>' +
        '<p class="sub">Questions where competitors appear in AI answers but your brand does not. Click “Copy brief” to build a content brief.</p></div>';
    }

    // Volumes
    if (data.volumes && data.volumes.length) {
      const rows = data.volumes.map(function (r) {
        let spark = '';
        try {
          const months = JSON.parse(r.trend_json || '[]');
          const vals = months.slice(-12).map(function (m) { return m.ai_search_volume || 0; });
          const mx = Math.max.apply(null, vals.concat([1]));
          spark = '<span class="spark">' + vals.map(function (v) { return '<i style="height:' + Math.max(1, Math.round(v / mx * 18)) + 'px"></i>'; }).join('') + '</span>';
        } catch (e) { spark = '<span class="sub">—</span>'; }
        return '<tr><td>' + esc(r.keyword) + '</td><td class="vol">' + fmtNum(r.ai_search_volume) + '</td><td>' + spark + '</td></tr>';
      }).join('');
      html += '<h2>AI search volume — your seed keywords</h2><div class="card"><table>' +
        '<tr><th>keyword</th><th>AI searches/mo</th><th>12-month trend</th></tr>' + rows + '</table>' +
        '<p class="sub">How often each phrase is typed into AI tools per month (US). Updated monthly.</p></div>';
    }

    // Discovered prompts
    if (data.discovered && data.discovered.length) {
      const rows = data.discovered.map(function (r) {
        const prev = r.prev_volume;
        const delta = r.volume_delta;
        let deltaHtml = '<span class="sub">—</span>';
        if (delta !== null && delta !== undefined) {
          deltaHtml = '<span class="delta ' + (delta >= 0 ? 'up' : 'down') + '">' + (delta >= 0 ? '+' : '') + fmtNum(delta) + '</span>';
        } else if (prev !== null && prev !== undefined) {
          deltaHtml = '<span class="sub">from ' + fmtNum(prev) + '</span>';
        }
        return '<tr data-volume="' + esc(String(r.ai_search_volume || 0)) + '" data-delta="' + esc(String(delta === null || delta === undefined ? '' : delta)) + '">' +
          '<td>' + esc(r.query) + '</td><td><span class="chip">' + esc(r.platform) + '</span></td>' +
          '<td class="vol num">' + fmtNum(r.ai_search_volume) + '</td>' +
          '<td class="num discovered-delta">' + deltaHtml + '</td></tr>';
      }).join('');
      html += '<h2>Discovered prompts — what people really ask AI</h2><div class="card"><table class="discovered-table">' +
        '<thead><tr><th>question</th><th>platform</th>' +
        '<th class="sortable" data-sort="volume">AI searches/mo <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="delta">Δ vs last <span class="arrow"></span></th></tr></thead><tbody>' + rows + '</tbody></table>' +
        '<p class="sub">Real user questions from the LLM Mentions database matched to your seeds. Click a column header to sort.</p></div>';
    }

    // Silent citations
    if (data.silent && data.silent.rows && data.silent.rows.length) {
      const trend = data.silent.previous_count ? ' · was ' + fmtNum(data.silent.previous_count) + ' at previous check' : '';
      const rows = data.silent.rows.map(function (r) {
        return '<tr><td>' + esc(r.query) + '</td><td><span class="chip">' + esc(r.platform) + '</span></td>' +
          '<td class="vol">' + fmtNum(r.ai_search_volume) + '</td></tr>';
      }).join('');
      html += '<h2>Silent citations — your content, no brand credit <span class="sub">(' + esc(String(data.silent.count)) + ' found' + esc(trend) + ')</span></h2>' +
        '<div class="card"><table><tr><th>query</th><th>platform</th><th>AI searches/mo</th></tr>' + rows + '</table>' +
        '<p class="sub">AI answers that cite ' + esc(data.domain || 'your domain') + ' as a source but never name your brand. Checked monthly.</p></div>';
    }

    // Latest run
    if (data.by_prompt && Object.keys(data.by_prompt).length) {
      html += '<h2>Latest LLM run — ' + esc(data.latest_day || '—') + '</h2>';
      for (const [prompt, entries] of Object.entries(data.by_prompt)) {
        const chips = entries.map(function (e) {
          return '<div><span class="plat">' + esc(e.platform) + '</span> ' + brandChips(e.mentions, brands, you) +
            (e.cited_mine ? ' <span class="chip cite">your site cited</span>' : '') + '</div>';
        }).join('');
        const answers = entries.map(function (e) {
          return '<div><span class="plat">' + esc(e.platform) + '</span></div>' +
            '<div class="answer">' + esc((e.answer || '').slice(0, 4000)) + '</div>';
        }).join('');
        html += '<div class="card"><b>' + esc(prompt) + '</b>' + chips +
          '<details><summary>show raw answers</summary>' + answers + '</details></div>';
      }
    }

    return html;
  }

  async function loadLLM() {
    const el = document.getElementById('panel-llm');
    try {
      const [circle, fit, gapsCircle, gapsFit] = await Promise.all([
        api('llm?property=vantagecircle'),
        api('llm?property=vantagefit'),
        api('llm_gaps?property=vantagecircle').catch(function () { return { gaps: [] }; }),
        api('llm_gaps?property=vantagefit').catch(function () { return { gaps: [] }; }),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle, gaps: gapsCircle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit, gaps: gapsFit },
      ];

      const anyData = tabs.some(function (t) {
        return (t.data.trend && t.data.trend.length) ||
          (t.data.by_prompt && Object.keys(t.data.by_prompt).length) ||
          (t.data.volumes && t.data.volumes.length) ||
          (t.gaps && t.gaps.gaps && t.gaps.gaps.length);
      });
      if (!anyData) {
        el.innerHTML = '<div class="card">No LLM visibility data available yet.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        const body = renderLlmProp(t.data, t.gaps) || '<div class="card">No data for this project yet — the tracker runs biweekly.</div>';
        return '<div class="llm-prop' + (i === 0 ? ' active' : '') + '" id="llm-' + esc(t.key) + '">' + body + '</div>';
      }).join('');

      const latestDay = tabs.map(function (t) { return t.data.latest_day; }).filter(Boolean).sort().pop();
      el.innerHTML = '<h2>LLM Visibility · share of voice</h2>' + tabHtml + panelsHtml + stampHtml(latestDay);
      initPropTabs(el, 'llm-prop');
      initLlmInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- llm prompts inventory
  async function loadLlmPrompts() {
    const el = document.getElementById('panel-llm-prompts');
    try {
      const [circle, fit] = await Promise.all([
        api('llm_prompts?property=vantagecircle').catch(function () { return { prompts: [] }; }),
        api('llm_prompts?property=vantagefit').catch(function () { return { prompts: [] }; }),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit },
      ];

      const anyData = tabs.some(function (t) { return t.data.prompts && t.data.prompts.length; });
      if (!anyData) {
        el.innerHTML = '<h2>LLM Prompts</h2><div class="card">No LLM prompt data available yet.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        const rows = (t.data.prompts || []).map(function (p) {
          const comps = (p.competitors_mentioned || []).map(function (c) {
            return '<span class="chip">' + esc(c) + '</span>';
          }).join(' ');
          const youChip = p.you_mentioned ? '<span class="chip you">you</span>' : '<span class="chip none">not mentioned</span>';
          const cited = p.cited_count ? '<span class="chip cite">cited ' + p.cited_count + '/' + p.total_answers + '</span>' : '<span class="sub">—</span>';
          return '<tr>' +
            '<td>' + esc(p.prompt) + '</td>' +
            '<td>' + esc((p.platforms || []).join(', ')) + '</td>' +
            '<td>' + youChip + '</td>' +
            '<td>' + (comps || '<span class="sub">—</span>') + '</td>' +
            '<td>' + cited + '</td></tr>';
        }).join('');
        const body = '<div class="card"><table class="llm-prompts-table">' +
          '<thead><tr><th>Prompt</th><th>Platforms</th><th>Your brand</th><th>Competitors mentioned</th><th>Cited</th></tr></thead>' +
          '<tbody>' + (rows || '<tr><td colspan="5" class="sub">No prompts yet.</td></tr>') + '</tbody></table>' +
          '<p class="sub">' + esc(String(t.data.prompts.length)) + ' prompts tracked · latest run ' + esc(t.data.day || '—') + '</p></div>';
        return '<div class="llm-prompts-prop' + (i === 0 ? ' active' : '') + '" id="llm-prompts-' + esc(t.key) + '">' + body + '</div>';
      }).join('');

      const latestDay = tabs.map(function (t) { return t.data.day; }).filter(Boolean).sort().pop();
      el.innerHTML = '<h2>LLM Prompts · inventory</h2>' + tabHtml + panelsHtml + stampHtml(latestDay);
      initPropTabs(el, 'llm-prompts-prop');
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initLlmInteractions() {
    // Copy brief buttons
    document.querySelectorAll('.gap-brief').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var row = btn.closest('tr');
        var prop = row ? row.getAttribute('data-property') : '';
        var prompt = row ? row.getAttribute('data-prompt') : '';
        var competitors = row ? row.getAttribute('data-competitors') : '';
        var volume = row ? row.getAttribute('data-volume') : '';
        var label = (PROPERTIES[prop] && PROPERTIES[prop].label) || prop || 'your brand';
        var text = 'Brief: ' + (prompt || '') + '\nCompetitors mentioned: ' + (competitors || '') + '\nAngle: Explain why ' + label + ' is the better choice for this query. Cite comparison points from current AI answers.\nEstimated AI searches/mo: ' + fmtNum(volume);
        try {
          await navigator.clipboard.writeText(text);
          const orig = btn.textContent;
          btn.textContent = 'Copied';
          setTimeout(function () { btn.textContent = orig; }, 1200);
        } catch (err) {
          alert('Could not copy brief: ' + err.message);
        }
      });
    });

    // Discovered table sorting
    document.querySelectorAll('.discovered-table').forEach(function (table) {
      var tbody = table.querySelector('tbody');
      var ths = table.querySelectorAll('th.sortable');
      if (!tbody || !ths.length) return;
      var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      var sortKey = 'volume', sortDir = -1;

      function keyVal(r, k) {
        var v = r.getAttribute('data-' + k);
        return v === '' || v == null ? null : parseFloat(v);
      }

      function cmp(a, b) {
        var va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
        if (va === null && vb === null) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
        if (va < vb) return -sortDir;
        if (va > vb) return sortDir;
        return 0;
      }

      function applySort() {
        rows.sort(cmp);
        rows.forEach(function (r) { tbody.appendChild(r); });
        ths.forEach(function (th) {
          var arr = th.querySelector('.arrow');
          if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
        });
      }

      ths.forEach(function (th) {
        th.addEventListener('click', function () {
          var k = th.getAttribute('data-sort');
          if (k === sortKey) { sortDir = -sortDir; }
          else { sortKey = k; sortDir = -1; }
          applySort();
        });
      });

      applySort();
    });
  }

  // ---------------------------------------------------------------- freshness
  function riskChip(risk) {
    const cls = { LOW: 'you', MEDIUM: 'cite', HIGH: 'none' }[risk] || '';
    return '<span class="chip ' + cls + '">' + esc(risk) + '</span>';
  }

  function actionChip(action) {
    const cls = { UPDATE: 'none', REFRESH: 'cite', EXPAND: 'cite', PRUNE: 'none', FIX: 'none', MONITOR: 'you' }[action] || '';
    return '<span class="chip ' + cls + '">' + esc(action) + '</span>';
  }

  function freshnessQueueRow(r) {
    const status = (r.status && r.status.status) || 'todo';
    const owner = (r.status && r.status.owner) || '';
    const note = (r.status && r.status.note) || '';
    const display = ((r.title || r.url || '').replace(/^https?:\/\//, '')).slice(0, 70);
    return '<tr data-url="' + esc(r.url) + '">' +
      '<td><a href="' + esc(r.url) + '" target="_blank">' + esc(display) + '</a></td>' +
      '<td>' + esc(r.property) + '</td>' +
      '<td>' + actionChip(r.action) + '</td>' +
      '<td>' + riskChip(r.decay_risk) + '</td>' +
      '<td class="num">' + esc(String(r.priority_score)) + '</td>' +
      '<td><input class="queue-owner" type="text" value="' + esc(owner) + '" placeholder="Owner"></td>' +
      '<td><select class="queue-status">' +
      '<option value="todo"' + (status === 'todo' ? ' selected' : '') + '>Todo</option>' +
      '<option value="in_progress"' + (status === 'in_progress' ? ' selected' : '') + '>In progress</option>' +
      '<option value="done"' + (status === 'done' ? ' selected' : '') + '>Done</option>' +
      '<option value="ignored"' + (status === 'ignored' ? ' selected' : '') + '>Ignored</option>' +
      '</select></td>' +
      '<td><input class="queue-note" type="text" value="' + esc(note) + '" placeholder="Note"></td>' +
      '<td><button class="queue-save" type="button">Save</button><span class="queue-saved sub">saved</span></td>' +
      '</tr>';
  }

  async function loadFreshness() {
    const el = document.getElementById('panel-freshness');
    try {
      const [data, qCircle, qFit] = await Promise.all([
        api('freshness'),
        api('freshness_queue?property=vantagecircle').catch(function () { return { queue: [] }; }),
        api('freshness_queue?property=vantagefit').catch(function () { return { queue: [] }; }),
      ]);
      const rows = data.rows || [];
      const queue = [].concat(qCircle.queue || [], qFit.queue || []);

      const total = rows.length;
      const highRisk = rows.filter(function (r) { return r.decay_risk === 'HIGH'; }).length;
      const ages = rows.filter(function (r) { return r.age_days !== null && r.age_days < 9000; }).map(function (r) { return r.age_days; });
      const avgAge = ages.length ? Math.round(ages.reduce(function (a, b) { return a + b; }, 0) / ages.length) : 0;
      const actionCounts = {};
      rows.forEach(function (r) { actionCounts[r.action] = (actionCounts[r.action] || 0) + 1; });
      const needsAction = Object.entries(actionCounts).filter(function (e) { return e[0] !== 'MONITOR'; }).reduce(function (s, e) { return s + e[1]; }, 0);

      const cards = [
        ['Pages monitored', fmtNum(total), 'as of ' + esc(data.day || '')],
        ['High decay risk', fmtNum(highRisk), (total ? (highRisk / total * 100).toFixed(1) : 0) + '% of pages'],
        ['Average age', fmtNum(avgAge), 'days since last update'],
        ['Needs action', fmtNum(needsAction), 'refresh/update/prune/fix'],
      ];
      const kpiHtml = '<div class="kpis">' + cards.map(function (c) {
        return '<div class="kpi"><div class="num">' + esc(c[1]) + '</div><div class="label">' + esc(c[0]) + '<br><span class="sub">' + esc(c[2]) + '</span></div></div>';
      }).join('') + '</div>';

      const queueTabs = ['All', 'Todo', 'In progress', 'Done', 'Ignored'];
      const queueTabHtml = '<div class="queue-tabs no-print">' + queueTabs.map(function (t, i) {
        return '<button class="queue-tab' + (i === 0 ? ' active' : '') + '" data-status="' + esc(t.toLowerCase().replace(/ /g, '_')) + '">' + esc(t) + '</button>';
      }).join('') + '<span class="queue-count sub">' + esc(String(queue.length)) + ' items</span></div>';

      const queueRows = queue.map(freshnessQueueRow).join('');
      const queueHtml = '<div class="card queue-wrap">' +
        '<b>Decay queue</b>' + queueTabHtml +
        '<table class="queue-table"><thead><tr>' +
        '<th>Page</th><th>Property</th><th>Action</th><th>Risk</th><th>Priority</th>' +
        '<th>Owner</th><th>Status</th><th>Note</th><th></th>' +
        '</tr></thead><tbody>' + (queueRows || '<tr><td colspan="9" class="sub">Queue is empty.</td></tr>') + '</tbody></table></div>';

      const properties = [...new Set(rows.map(function (r) { return r.property; }))].sort();
      const types = [...new Set(rows.map(function (r) { return r.page_type; }))].sort();
      const actions = [...new Set(rows.map(function (r) { return r.action; }))].sort();
      const risks = [...new Set(rows.map(function (r) { return r.decay_risk; }))].sort();

      function opts(list, label) {
        return '<option value="">All ' + label + '</option>' + list.map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + '</option>'; }).join('');
      }

      const tableRows = rows.map(function (r) {
        const display = ((r.title || r.url || '').replace(/^https?:\/\//, '')).slice(0, 70);
        const search = [r.url, r.title, r.target_keyword, r.property, r.page_type, r.action, r.reason, r.decay_risk].filter(Boolean).join(' ').toLowerCase();
        return '<tr data-search="' + esc(search) + '" data-property="' + esc(r.property) + '" data-type="' + esc(r.page_type) + '"' +
          ' data-action="' + esc(r.action) + '" data-risk="' + esc(r.decay_risk) + '" data-age="' + esc(String(r.age_days)) + '" data-priority="' + esc(String(r.priority_score)) + '"' +
          ' data-display="' + esc(display.toLowerCase()) + '" data-keyword="' + esc((r.target_keyword || '').toLowerCase()) + '">' +
          '<td><a href="' + esc(r.url) + '" target="_blank">' + esc(display) + '</a></td>' +
          '<td>' + esc(r.property) + '</td><td>' + esc(r.page_type) + '</td><td>' + esc(String(r.age_days)) + '</td><td>' + esc(String(r.word_count)) + '</td>' +
          '<td>' + esc(String(r.freshness_score)) + '</td><td>' + esc(String(r.depth_score)) + '</td><td>' + riskChip(r.decay_risk) + '</td>' +
          '<td>' + esc(r.target_keyword || '') + '</td><td>' + (r.position && r.position <= 100 ? esc(String(r.position)) : '—') + '</td><td>' + (r.volume ? fmtNum(r.volume) : '—') + '</td>' +
          '<td>' + actionChip(r.action) + '</td><td class="sub">' + esc(r.reason) + '</td></tr>';
      }).join('');

      const tableHtml = '<details class="freshness-all"><summary>All pages</summary><div class="card freshness-wrap">' +
        '<div class="table-tools no-print freshness-tools">' +
        '<input class="freshness-search" type="search" placeholder="Search pages…">' +
        '<select class="freshness-property">' + opts(properties, 'properties') + '</select>' +
        '<select class="freshness-type">' + opts(types, 'types') + '</select>' +
        '<select class="freshness-action">' + opts(actions, 'actions') + '</select>' +
        '<select class="freshness-risk">' + opts(risks, 'risks') + '</select>' +
        '<span class="freshness-count sub">' + esc(String(total)) + ' pages</span></div>' +
        '<table class="freshness-table"><thead><tr>' +
        '<th class="sortable" data-sort="display">Page <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="property">Property <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="type">Type <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="age">Age <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="word_count">Words <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="freshness">Fresh <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="depth">Depth <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="risk">Risk <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="keyword">Keyword <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="position">Pos <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="volume">Vol <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="action">Action <span class="arrow"></span></th>' +
        '<th>Reason</th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div></details>';

      el.innerHTML = '<h2>Content Freshness</h2>' + kpiHtml + queueHtml + tableHtml + stampHtml(data.day);
      initFreshnessInteractions();
      initFreshnessQueueInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initFreshnessQueueInteractions() {
    var wrap = document.querySelector('.queue-wrap');
    if (!wrap) return;
    var tbody = wrap.querySelector('tbody');
    var tabs = wrap.querySelectorAll('.queue-tab');
    var count = wrap.querySelector('.queue-count');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr[data-url]'));

    function applyFilter() {
      var active = wrap.querySelector('.queue-tab.active');
      var status = active ? active.getAttribute('data-status') : 'all';
      var n = 0;
      rows.forEach(function (r) {
        var st = r.querySelector('.queue-status').value;
        var ok = status === 'all' || st === status;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' items';
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (t) { t.classList.toggle('active', t === tab); });
        applyFilter();
      });
    });

    rows.forEach(function (r) {
      var saveBtn = r.querySelector('.queue-save');
      if (!saveBtn) return;
      saveBtn.addEventListener('click', async function () {
        var url = r.getAttribute('data-url');
        var owner = r.querySelector('.queue-owner').value;
        var status = r.querySelector('.queue-status').value;
        var note = r.querySelector('.queue-note').value;
        var saved = r.querySelector('.queue-saved');
        try {
          await api('freshness_queue', { method: 'PATCH', body: { url: url, status: status, owner: owner, note: note } });
          if (saved) {
            saved.style.display = 'inline';
            setTimeout(function () { saved.style.display = ''; }, 1500);
          }
        } catch (err) {
          alert('Save failed: ' + err.message);
        }
      });
    });

    applyFilter();
  }

  // ---------------------------------------------------------------- competitor tracker
  function sectionOf(url) {
    try {
      const locale = { en: 1, fr: 1, es: 1, de: 1, it: 1, pt: 1, ja: 1, ko: 1, zh: 1, 'en-us': 1, 'en-gb': 1, 'en-au': 1, 'en-in': 1, 'en-ca': 1, 'fr-ca': 1 };
      let p = new URL(url).pathname.replace(/^\/+/, '').split('/').filter(Boolean);
      if (p.length > 1 && locale[p[0]]) p.shift();
      return p[0] || 'home';
    } catch (e) { return 'other'; }
  }

  function typeLabel(t, n) {
    const map = {
      new_page: ['new page', 'new pages'],
      content_update: ['content update', 'content updates'],
      page_removed: ['page removed', 'pages removed'],
      redirect: ['redirect', 'redirects'],
      title_change: ['title change', 'title changes'],
      meta_change: ['meta change', 'meta changes'],
      h1_change: ['H1 change', 'H1 changes'],
      schema_change: ['schema change', 'schema changes'],
      url_case_change: ['URL case change', 'URL case changes']
    };
    const pair = map[t] || [t, t + 's'];
    return pair[n === 1 ? 0 : 1];
  }

  function renderCompetitorCharts(box, changes, competitors, selfDomain) {
    var np = changes.filter(function (c) { return c.change_type === 'new_page'; });
    var counts = {}, colors = ['#4f46e5', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2', '#7c3aed'];
    np.forEach(function (c) { counts[c.domain] = (counts[c.domain] || 0) + 1; });
    var sorted = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; });
    var max = Math.max.apply(null, Object.values(counts).concat([1]));
    var html = sorted.map(function (d, i) {
      return "<div class='comp-hbar'><span class='name'>" + esc(d) + "</span>" +
        "<div class='track'><div class='fill' style='width:" + (counts[d] / max * 100) + "%;background:" + colors[i % colors.length] + "'></div></div>" +
        "<b>" + counts[d] + "</b></div>";
    }).join('');
    box.querySelector('.chart-new-pages').innerHTML = html || '<p class="sub">No new pages in range.</p>';

    var sections = {}, secTotals = {};
    np.forEach(function (c) {
      var s = sectionOf(c.url);
      secTotals[s] = (secTotals[s] || 0) + 1;
      sections[c.domain] = sections[c.domain] || {};
      sections[c.domain][s] = (sections[c.domain][s] || 0) + 1;
    });
    var topSections = Object.keys(secTotals).sort(function (a, b) { return secTotals[b] - secTotals[a]; }).slice(0, 6);
    if (topSections.length) {
      var rows = Object.keys(sections).sort().map(function (d) {
        var rowTotal = Object.values(sections[d]).reduce(function (a, b) { return a + b; }, 0);
        var cells = topSections.map(function (s) { return '<td>' + (sections[d][s] || '<span class="sub">—</span>') + '</td>'; }).join('');
        return '<tr><td><b>' + esc(d) + '</b></td>' + cells + '<td><b>' + rowTotal + '</b></td></tr>';
      }).join('');
      box.querySelector('.chart-sections').innerHTML = "<div class='comp-matrix'><table><thead><tr><th>Competitor</th>" +
        topSections.map(function (s) { return '<th>/' + esc(s) + '</th>'; }).join('') + "<th>Total</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
    } else {
      box.querySelector('.chart-sections').innerHTML = '<p class="sub">No new pages in range.</p>';
    }

    var words = {};
    changes.filter(function (c) { return c.change_type === 'content_update' && c.details && c.details.word_count_change; })
      .forEach(function (c) { words[c.domain] = (words[c.domain] || 0) + c.details.word_count_change; });
    var wSorted = Object.keys(words).sort(function (a, b) { return Math.abs(words[b]) - Math.abs(words[a]); });
    var wMax = Math.max.apply(null, Object.values(words).map(Math.abs).concat([1]));
    box.querySelector('.chart-words').innerHTML = wSorted.map(function (d) {
      var v = words[d];
      var color = v >= 0 ? '#059669' : '#dc2626';
      return "<div class='comp-hbar'><span class='name'>" + esc(d) + "</span>" +
        "<div class='track'><div class='fill' style='width:" + (Math.abs(v) / wMax * 100) + "%;background:" + color + "'></div></div>" +
        "<b style='color:" + color + "'>" + (v > 0 ? '+' : '') + v + "</b></div>";
    }).join('') || '<p class="sub">No content updates in range.</p>';

    var typeCounts = {};
    changes.forEach(function (c) { typeCounts[c.change_type] = (typeCounts[c.change_type] || 0) + 1; });
    var tSorted = Object.keys(typeCounts).sort(function (a, b) { return typeCounts[b] - typeCounts[a]; });
    var tMax = Math.max.apply(null, Object.values(typeCounts).concat([1]));
    var tColors = { new_page: '#059669', content_update: '#d97706', title_change: '#4f46e5', meta_change: '#7c3aed', h1_change: '#db2777', schema_change: '#0891b2', redirect: '#ea580c', page_removed: '#dc2626', url_case_change: '#6b7280' };
    box.querySelector('.chart-types').innerHTML = tSorted.map(function (t) {
      return "<div class='comp-hbar'><span class='name'>" + typeLabel(t, 2) + "</span>" +
        "<div class='track'><div class='fill' style='width:" + (typeCounts[t] / tMax * 100) + "%;background:" + (tColors[t] || '#4f46e5') + "'></div></div>" +
        "<b>" + typeCounts[t] + "</b></div>";
    }).join('') || '<p class="sub">No changes in range.</p>';

    var weeks = {};
    changes.forEach(function (c) {
      var d = new Date(c.timestamp);
      var y = d.getFullYear();
      var w = Math.floor((d - new Date(y, 0, 0)) / 604800000);
      var key = y + '-W' + w;
      weeks[key] = weeks[key] || { new_page: 0, content_update: 0, other: 0, total: 0 };
      if (c.change_type === 'new_page') weeks[key].new_page++;
      else if (c.change_type === 'content_update') weeks[key].content_update++;
      else weeks[key].other++;
      weeks[key].total++;
    });
    var wKeys = Object.keys(weeks).sort().slice(-12);
    var wMax = Math.max.apply(null, wKeys.map(function (k) { return weeks[k].total; }).concat([1]));
    box.querySelector('.chart-trend').innerHTML = wKeys.map(function (k) {
      var w = weeks[k];
      return "<div class='comp-hbar'><span class='name'>" + k + "</span>" +
        "<div class='track'><div class='fill' style='width:" + (w.total / wMax * 100) + "%;background:linear-gradient(90deg,#059669 0%,#059669 " + (w.new_page / w.total * 100) + "%,#d97706 " + (w.new_page / w.total * 100) + "%,#d97706 " + ((w.new_page + w.content_update) / w.total * 100) + "%,#4f46e5 100%)'></div></div>" +
        "<b>" + w.total + "</b></div>";
    }).join('') || '<p class="sub">No weekly data yet.</p>';
  }

  function renderTimelineList(changes, compact) {
    if (!changes.length) return '<p class="sub">No changes match the selected filters.</p>';
    var groups = [];
    changes.forEach(function (c) {
      var day = new Date(c.timestamp).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
      var last = groups[groups.length - 1];
      if (!last || last.day !== day || last.domain !== c.domain) {
        groups.push({ day: day, domain: c.domain, competitor: c.competitor, items: [] });
      }
      last = groups[groups.length - 1];
      last.items.push(c);
    });
    var html = '', lastDay = '';
    groups.forEach(function (g) {
      if (g.day !== lastDay) { html += "<div class='comp-day'>" + esc(g.day) + "</div>"; lastDay = g.day; }
      var counts = {};
      g.items.forEach(function (c) { counts[c.change_type] = (counts[c.change_type] || 0) + 1; });
      var summary = Object.entries(counts).sort(function (a, b) { return b[1] - a[1]; }).map(function (e) {
        return e[1] + ' ' + typeLabel(e[0], e[1]);
      }).join(' · ');
      html += "<div class='comp-group'>" +
        "<div class='comp-group-head' onclick=\"this.parentElement.classList.toggle('open')\">" +
        "<span class='comp-group-name'>" + esc(g.competitor) + "</span>" +
        "<span class='comp-group-summary'>" + esc(summary) + "</span></div>" +
        "<div class='comp-group-items'>" + g.items.map(function (c) { return renderChangeRow(c, compact); }).join('') + "</div></div>";
    });
    return html;
  }

  function renderChangeRow(c, compact) {
    var det = c.details || {};
    var tags = '';
    if (det.word_count_change) {
      tags += "<span class='comp-seo-tag " + (det.word_count_change > 0 ? 'up' : 'down') + "'>" + (det.word_count_change > 0 ? '+' : '') + det.word_count_change + "w</span>";
    } else if (c.change_type === 'new_page' && det.word_count) {
      tags += "<span class='comp-seo-tag'>" + fmtNum(det.word_count) + "w</span>";
    } else if (c.change_type === 'redirect' && det.status_code) {
      tags += "<span class='comp-seo-tag'>" + esc(det.status_code) + "</span>";
    }
    var detailHtml = '';
    if (!compact) {
      var parts = [];
      if (det.old_title && det.new_title) parts.push('Title: "' + esc(det.old_title) + '" → "' + esc(det.new_title) + '"');
      if (det.old_meta && det.new_meta) parts.push('Meta: "' + esc(det.old_meta) + '" → "' + esc(det.new_meta) + '"');
      if (det.old_h1 && det.new_h1) parts.push('H1: "' + esc(det.old_h1) + '" → "' + esc(det.new_h1) + '"');
      if (det.redirect && det.redirect_to) parts.push('Redirect → <a href="' + esc(det.redirect_to) + '" target="_blank">' + esc(det.redirect_to) + '</a>');
      if (det.added && det.added.length) parts.push('<div style="color:#059669"><b>+ added</b><br>' + det.added.map(esc).join('<br>') + '</div>');
      if (det.removed && det.removed.length) parts.push('<div style="color:#dc2626"><b>- removed</b><br>' + det.removed.map(esc).join('<br>') + '</div>');
      if (parts.length) detailHtml = "<div class='comp-row-detail'>" + parts.join('<br>') + "</div>";
    }
    return "<div>" +
      "<div class='comp-row' onclick=\"this.nextElementSibling.classList.toggle('open')\">" +
      "<span class='comp-badge " + c.change_type + "'>" + typeLabel(c.change_type, 1) + "</span>" +
      "<span style='flex:1'>" + esc(c.title || c.url) + "</span>" +
      "<span class='sub'>" + esc(sectionOf(c.url)) + "</span>" + tags + "</div>" +
      detailHtml + "</div>";
  }

  function renderCompetitorPanel(box) {
    var data = JSON.parse(box.getAttribute('data-competitor-json') || '{}');
    var changes = data.changes || [];
    var competitors = data.competitors || {};
    var selfDomain = data.self_domain || '';
    var days = parseInt(box.querySelector('.comp-days').value, 10) || 30;

    function inRange(ts, d) {
      if (d === 0) return true;
      var now = new Date(); now.setHours(0, 0, 0, 0);
      var then = new Date(ts);
      return then >= new Date(now.getTime() - d * 86400000);
    }

    var filtered = changes.filter(function (c) { return inRange(c.timestamp, days); });
    var compFilter = box.querySelector('.comp-filter-competitor');
    var typeFilter = box.querySelector('.comp-filter-type');
    if (compFilter && compFilter.value) filtered = filtered.filter(function (c) { return c.domain === compFilter.value; });
    if (typeFilter && typeFilter.value) filtered = filtered.filter(function (c) { return c.change_type === typeFilter.value; });

    var totalPages = Object.values(competitors).reduce(function (s, d) { return s + (d.total_urls || 0); }, 0);
    var selfNew = filtered.filter(function (c) { return c.change_type === 'new_page' && c.domain === selfDomain; }).length;
    var rivalDomains = Object.keys(competitors).filter(function (d) { return d !== selfDomain; });
    var rivalNew = filtered.filter(function (c) { return c.change_type === 'new_page' && c.domain !== selfDomain; }).length;
    var rivalAvg = rivalDomains.length ? Math.round(rivalNew / rivalDomains.length) : 0;
    var kpis = box.querySelector('.comp-kpis');
    kpis.innerHTML = [
      "<div class='comp-kpi'><div class='num'>" + Object.keys(competitors).length + "</div><div class='label'>Tracked competitors</div></div>",
      "<div class='comp-kpi'><div class='num'>" + fmtNum(totalPages) + "</div><div class='label'>Pages indexed</div></div>",
      "<div class='comp-kpi'><div class='num'>" + filtered.filter(function (c) { return c.change_type === 'new_page'; }).length + "</div><div class='label'>New pages</div></div>",
      "<div class='comp-kpi'><div class='num'>" + filtered.filter(function (c) { return c.change_type === 'content_update'; }).length + "</div><div class='label'>Content updates</div></div>",
      "<div class='comp-kpi'><div class='num'>" + filtered.length + "</div><div class='label'>All changes</div></div>",
      "<div class='comp-kpi'><div class='num' style='color:" + (selfNew >= rivalAvg ? '#059669' : '#dc2626') + "'>" + selfNew + " : " + rivalAvg + "</div><div class='label'>You vs rival avg</div></div>"
    ].join('');

    var maxPages = Math.max.apply(null, Object.values(competitors).map(function (d) { return d.total_urls || 0; }).concat([1]));
    var cards = box.querySelector('.comp-cards');
    cards.innerHTML = Object.entries(competitors).map(function (entry, i) {
      var domain = entry[0], d = entry[1];
      var dc = filtered.filter(function (c) { return c.domain === domain; });
      var secCounts = {};
      dc.filter(function (c) { return c.change_type === 'new_page'; }).forEach(function (c) {
        var s = sectionOf(c.url); secCounts[s] = (secCounts[s] || 0) + 1;
      });
      var topSec = Object.entries(secCounts).sort(function (a, b) { return b[1] - a[1]; })[0];
      var color = ['#4f46e5', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2'][i % 6];
      var isSelf = domain === selfDomain;
      return "<div class='comp-card" + (isSelf ? ' you' : '') + "'><div class='comp-card-head'><h4>" + esc(d.name || domain) +
        (isSelf ? "<span class='comp-you-badge'>you</span>" : '') + "</h4><div class='domain'>" + esc(domain) + "</div></div>" +
        "<div class='row'><span>Pages</span><b>" + fmtNum(d.total_urls || 0) + "</b></div>" +
        "<div class='row'><span>New</span><b style='color:#059669'>" + dc.filter(function (c) { return c.change_type === 'new_page'; }).length + "</b></div>" +
        "<div class='row'><span>Updates</span><b style='color:#d97706'>" + dc.filter(function (c) { return c.change_type === 'content_update'; }).length + "</b></div>" +
        "<div class='row'><span>Total</span><b>" + dc.length + "</b></div>" +
        "<div class='row'><span>Top section</span><b>" + (topSec ? esc(topSec[0]) + ' (' + topSec[1] + ')' : '—') + "</b></div>" +
        "<div class='bar'><div style='width:" + ((d.total_urls || 0) / maxPages * 100).toFixed(0) + "%;background:" + color + "'></div></div>";
    }).join('');

    box.querySelector('.comp-overview-timeline').innerHTML = renderTimelineList(filtered.slice(0, 10), true);
    box.querySelector('.comp-changes-timeline').innerHTML = renderTimelineList(filtered, false);

    var seo = filtered.filter(function (c) { return ['title_change', 'meta_change', 'h1_change', 'schema_change'].indexOf(c.change_type) > -1; });
    box.querySelector('.comp-seo-list').innerHTML = seo.slice(0, 200).map(function (c) {
      var det = c.details || {};
      var body;
      if (c.change_type === 'schema_change') {
        body = (det.added_schemas || []).map(function (s) { return "<span class='comp-seo-tag up'>+" + esc(s) + "</span>"; }).join(' ') +
          (det.removed_schemas || []).map(function (s) { return "<span class='comp-seo-tag down'>-" + esc(s) + "</span>"; }).join(' ');
      } else {
        var oldVal = det.old_title || det.old_meta || det.old_h1 || '';
        var newVal = det.new_title || det.new_meta || det.new_h1 || '';
        body = "<div class='sub'>" + esc(oldVal) + "</div><div>→</div><div>" + esc(newVal) + "</div>";
      }
      return "<div class='card' style='margin:8px 0;padding:12px 14px'><div style='display:flex;gap:10px;align-items:center;margin-bottom:6px'>" +
        "<span class='comp-badge " + c.change_type + "'>" + typeLabel(c.change_type, 1) + "</span>" +
        "<b>" + esc(c.competitor) + "</b> <a href='" + esc(c.url) + "' target='_blank' class='sub'>" + esc(c.title || c.url) + "</a></div>" + body + "</div>";
    }).join('') || '<p class="sub">No on-page SEO changes in range.</p>';

    renderCompetitorCharts(box, filtered, competitors, selfDomain);
  }

  function renderCompetitorBox(data) {
    const cfg = PROPERTIES[data.property] || { label: data.property, domain: data.property };
    const competitors = data.competitors || {};
    const compOptions = Object.entries(competitors).sort(function (a, b) { return (a[1].name || a[0]).localeCompare(b[1].name || b[0]); }).map(function (e) {
      return '<option value="' + esc(e[0]) + '">' + esc(e[1].name || e[0]) + '</option>';
    }).join('');
    const typeOptions = COMPETITOR_TYPES.map(function (e) { return '<option value="' + esc(e[0]) + '">' + esc(e[1]) + '</option>'; }).join('');
    const lastRun = data.changes && data.changes.length ? data.changes[0].timestamp.slice(0, 19).replace('T', ' ') + ' UTC' : '—';
    const payload = esc(JSON.stringify({ property: data.property, self_domain: data.self_domain, competitors: competitors, changes: data.changes || [] }));

    return '<div class="competitor-box" data-competitor-json="' + payload + '">' +
      '<div class="comp-tabs no-print">' +
      '<button class="comp-tab active" data-tab="overview">Overview</button>' +
      '<button class="comp-tab" data-tab="changes">Changes</button>' +
      '<button class="comp-tab" data-tab="seo">SEO Moves</button>' +
      '<button class="comp-tab" data-tab="activity">Activity</button>' +
      '<button class="comp-export">Export CSV</button></div>' +
      '<div class="comp-panel active" data-tab="overview">' +
      '<div class="comp-kpis"></div>' +
      '<div class="comp-cards"></div>' +
      '<h4 style="margin-top:20px">Recent changes</h4>' +
      '<div class="comp-overview-timeline comp-timeline"></div></div>' +
      '<div class="comp-panel" data-tab="changes">' +
      '<div class="comp-filters no-print">' +
      '<select class="comp-filter-competitor"><option value="">All competitors</option>' + compOptions + '</select>' +
      '<select class="comp-filter-type"><option value="">All types</option>' + typeOptions + '</select>' +
      '<select class="comp-days"><option value="1">Last 24 hours</option>' +
      '<option value="7">Last 7 days</option>' +
      '<option value="14">Last 14 days</option>' +
      '<option value="30" selected>Last 30 days</option>' +
      '<option value="90">Last 90 days</option>' +
      '<option value="0">All time</option></select></div>' +
      '<div class="comp-changes-timeline comp-timeline"></div></div>' +
      '<div class="comp-panel" data-tab="seo">' +
      '<p class="sub">On-page SEO edits competitors made to existing pages — title rewrites, meta changes, H1 swaps, and schema changes.</p>' +
      '<div class="comp-seo-list"></div></div>' +
      '<div class="comp-panel" data-tab="activity">' +
      '<div class="comp-chart"><h4>New pages by competitor</h4><div class="chart-new-pages"></div></div>' +
      '<div class="comp-chart"><h4>New pages by section</h4><div class="chart-sections"></div></div>' +
      '<div class="comp-chart"><h4>Net content investment (words)</h4><div class="chart-words"></div></div>' +
      '<div class="comp-chart"><h4>Change type breakdown</h4><div class="chart-types"></div></div>' +
      '<div class="comp-chart"><h4>Weekly trend</h4><div class="chart-trend"></div></div></div>' +
      '</div>';
  }

  async function loadCompetitor() {
    const el = document.getElementById('panel-competitor');
    try {
      const [circle, fit] = await Promise.all([
        api('competitor?property=vantagecircle'),
        api('competitor?property=vantagefit'),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit },
      ];

      const anyData = tabs.some(function (t) { return t.data.changes && t.data.changes.length; });
      if (!anyData) {
        el.innerHTML = '<div class="card">No competitor data available yet.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        return '<div class="comp-prop' + (i === 0 ? ' active' : '') + '" id="comp-' + esc(t.key) + '">' +
          '<h2>Competitor Tracker — ' + esc(t.data.label || t.label) + ' <span class="sub">(last run: ' + esc((t.data.changes && t.data.changes[0]) ? t.data.changes[0].timestamp.slice(0, 19).replace('T', ' ') + ' UTC' : '—') + ')</span></h2>' +
          renderCompetitorBox(t.data) + '</div>';
      }).join('');

      el.innerHTML = tabHtml + panelsHtml;
      initPropTabs(el, 'comp-prop');
      initCompetitorInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- interactions
  function initPropTabs(panelEl, propClass) {
    var tabs = panelEl.querySelectorAll('.prop-tab');
    var props = panelEl.querySelectorAll('.' + propClass);
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var key = tab.getAttribute('data-prop');
        tabs.forEach(function (t) { t.classList.toggle('active', t === tab); });
        var prefix = propClass.replace(/-prop$/, '') + '-';
        props.forEach(function (p) {
          p.classList.toggle('active', p.id === prefix + key);
        });
      });
    });
  }

  function panelFromHash() {
    var m = location.hash.match(/^#\/([a-z]+)(?:\/([a-z]+))?/);
    return m ? { p: m[1], t: m[2] } : null;
  }

  function activatePanel(p, t) {
    var items = Array.from(document.querySelectorAll('.nav-item'));
    var it = items.find(function (n) {
      return n.getAttribute('data-panel') === p &&
        (t ? n.getAttribute('data-tab') === t : !n.getAttribute('data-tab'));
    }) || items.find(function (n) { return n.getAttribute('data-panel') === p; });
    if (!it) return;
    items.forEach(function (n) { n.classList.remove('active'); });
    it.classList.add('active');
    document.querySelectorAll('.panel').forEach(function (el) { el.classList.remove('active'); });
    var el = document.getElementById('panel-' + p);
    if (el) el.classList.add('active');
    var tab = t || it.getAttribute('data-tab');
    if (tab && el) {
      var tabBtn = el.querySelector('.prop-tab[data-prop="' + tab + '"]');
      if (tabBtn) tabBtn.click();
    }
    window.scrollTo(0, 0);
  }

  function initSidebar() {
    document.querySelectorAll('.nav-item').forEach(function (it) {
      it.addEventListener('click', function () {
        var p = it.getAttribute('data-panel');
        if (!p) return;
        var t = it.getAttribute('data-tab');
        var h = '#/' + p + (t ? '/' + t : '');
        if (location.hash === h) activatePanel(p, t);
        else location.hash = h; // hashchange handler activates the panel
      });
    });
    window.addEventListener('hashchange', function () {
      var r = panelFromHash();
      if (r) activatePanel(r.p, r.t);
    });
    var initial = panelFromHash();
    if (initial) activatePanel(initial.p, initial.t);
  }

  function initRankInteractions() {
    document.querySelectorAll('.rank-prop').forEach(function (box) {
      var search = box.querySelector('.rank-search');
      var tagSel = box.querySelector('.tag-filter');
      var tbody = box.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      var count = box.querySelector('.rank-count');
      var ths = box.querySelectorAll('th.sortable');
      var qchips = box.querySelectorAll('.qchip');
      var qState = '';
      var sortKey = 'position', sortDir = 1;

      function applyFilter() {
        var q = search ? search.value.toLowerCase() : '';
        var tag = tagSel ? tagSel.value : '';
        var n = 0;
        rows.forEach(function (r) {
          var ok = r.getAttribute('data-search').indexOf(q) > -1;
          if (ok && tag) {
            var rt = r.getAttribute('data-tag');
            ok = tag === '__untagged__' ? rt === '' : rt === tag;
          }
          if (ok && qState) ok = r.getAttribute('data-state') === qState;
          r.style.display = ok ? '' : 'none';
          if (ok) n++;
        });
        if (count) count.textContent = n + ' of ' + rows.length + ' keywords';
      }

      function keyVal(r, k) {
        var v = r.getAttribute('data-' + k);
        if (k === 'keyword') return v;
        return v === '' || v === null ? null : parseFloat(v);
      }

      function cmp(a, b) {
        var va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
        if (sortKey !== 'keyword') {
          if (va === null && vb === null) return 0;
          if (va === null) return 1;
          if (vb === null) return -1;
        }
        if (va < vb) return -sortDir;
        if (va > vb) return sortDir;
        return 0;
      }

      function applySort() {
        rows.sort(cmp);
        rows.forEach(function (r) { tbody.appendChild(r); });
        ths.forEach(function (th) {
          var arr = th.querySelector('.arrow');
          if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
        });
      }

      ths.forEach(function (th) {
        th.addEventListener('click', function () {
          var k = th.getAttribute('data-sort');
          if (k === sortKey) { sortDir = -sortDir; }
          else {
            sortKey = k;
            sortDir = (k === 'keyword' || k === 'position') ? 1 : -1;
          }
          applySort();
        });
      });

      if (search) search.addEventListener('input', applyFilter);
      if (tagSel) tagSel.addEventListener('change', applyFilter);

      qchips.forEach(function (c) {
        c.addEventListener('click', function () {
          qState = c.getAttribute('data-q');
          qchips.forEach(function (x) { x.classList.toggle('active', x === c); });
          applyFilter();
        });
      });

      var exportBtn = box.querySelector('.rank-export');
      if (exportBtn) exportBtn.addEventListener('click', function () {
        var q = function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
        var visible = rows.filter(function (r) { return r.style.display !== 'none'; });
        var csv = ['keyword,tag,position,change,volume,kd,url'].concat(visible.map(function (r) {
          return [
            q(r.cells[0].textContent),
            q(r.cells[1].textContent),
            r.getAttribute('data-position') || '',
            r.getAttribute('data-change') || '',
            r.getAttribute('data-volume') || '',
            r.getAttribute('data-kd') || '',
            q(r.getAttribute('data-url') || '')
          ].join(',');
        })).join('\n');
        var a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
        a.download = box.id + '-' + new Date().toISOString().slice(0, 10) + '.csv';
        a.click();
        URL.revokeObjectURL(a.href);
      });
      applySort();
      applyFilter();
    });
  }

  function initFreshnessInteractions() {
    var wrap = document.querySelector('.freshness-wrap');
    if (!wrap) return;
    var search = wrap.querySelector('.freshness-search');
    var propSel = wrap.querySelector('.freshness-property');
    var typeSel = wrap.querySelector('.freshness-type');
    var actionSel = wrap.querySelector('.freshness-action');
    var riskSel = wrap.querySelector('.freshness-risk');
    var tbody = wrap.querySelector('tbody');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var count = wrap.querySelector('.freshness-count');
    var ths = wrap.querySelectorAll('th.sortable');
    var sortKey = 'priority', sortDir = -1;

    function applyFilter() {
      var q = search ? search.value.toLowerCase() : '';
      var prop = propSel ? propSel.value : '';
      var ptype = typeSel ? typeSel.value : '';
      var action = actionSel ? actionSel.value : '';
      var risk = riskSel ? riskSel.value : '';
      var n = 0;
      rows.forEach(function (r) {
        var ok = true;
        if (q && r.getAttribute('data-search').indexOf(q) === -1) ok = false;
        if (ok && prop && r.getAttribute('data-property') !== prop) ok = false;
        if (ok && ptype && r.getAttribute('data-type') !== ptype) ok = false;
        if (ok && action && r.getAttribute('data-action') !== action) ok = false;
        if (ok && risk && r.getAttribute('data-risk') !== risk) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' pages';
    }

    function keyVal(r, k) {
      var v = r.getAttribute('data-' + k);
      if (k === 'display' || k === 'keyword' || k === 'risk' || k === 'action') return (v || '').toLowerCase();
      return v === '' || v == null ? null : parseFloat(v);
    }

    function cmp(a, b) {
      var va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey !== 'display' && sortKey !== 'keyword') {
        if (va === null && vb === null) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        var arr = th.querySelector('.arrow');
        if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else {
          sortKey = k;
          sortDir = (k === 'display' || k === 'keyword') ? 1 : -1;
        }
        applySort();
      });
    });

    [search, propSel, typeSel, actionSel, riskSel].forEach(function (el) {
      if (el) el.addEventListener('input', applyFilter);
    });
    applySort();
    applyFilter();
  }

  function initCompetitorInteractions() {
    document.querySelectorAll('.competitor-box').forEach(function (box) {
      renderCompetitorPanel(box);
      box.querySelectorAll('.comp-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
          box.querySelectorAll('.comp-tab').forEach(function (t) { t.classList.remove('active'); });
          tab.classList.add('active');
          box.querySelectorAll('.comp-panel').forEach(function (p) {
            p.classList.toggle('active', p.getAttribute('data-tab') === tab.getAttribute('data-tab'));
          });
        });
      });
      box.querySelectorAll('.comp-days, .comp-filter-competitor, .comp-filter-type').forEach(function (el) {
        el.addEventListener('change', function () { renderCompetitorPanel(box); });
      });
      var exportBtn = box.querySelector('.comp-export');
      if (exportBtn) {
        exportBtn.addEventListener('click', function () {
          var data = JSON.parse(box.getAttribute('data-competitor-json') || '{}');
          var rows = data.changes || [];
          var csv = 'timestamp,property,competitor,domain,url,change_type,title,details\n' +
            rows.map(function (c) {
              return [c.timestamp, c.property, c.competitor, c.domain, c.url, c.change_type, c.title, JSON.stringify(c.details || {})]
                .map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
            }).join('\n');
          var blob = new Blob([csv], { type: 'text/csv' });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'competitor_changes_' + data.property + '.csv';
          a.click();
        });
      }
    });
  }

  // ---------------------------------------------------------------- gsc llm queries
  async function loadGscLlmQueries() {
    const el = document.getElementById('panel-gsc-llm-queries');
    try {
      const [circle, fit] = await Promise.all([
        api('gsc_llm_queries?property=vantagecircle&_v=5').catch(function () { return { queries: [] }; }),
        api('gsc_llm_queries?property=vantagefit&_v=5').catch(function () { return { queries: [] }; }),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit },
      ];

      const anyData = tabs.some(function (t) { return t.data.queries && t.data.queries.length; });
      if (!anyData) {
        el.innerHTML = '<h2>GSC LLM Queries</h2><div class="card">No GSC LLM query data available yet. Run <code>python3 gsc_llm_queries.py</code> to populate.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        const rows = (t.data.queries || []).map(function (q) {
          const signals = (q.signals || []).map(function (s) {
            return '<span class="chip">' + esc(s.replace(/_/g, ' ')) + '</span>';
          }).join(' ');
          const pageCell = q.page
            ? '<a href="' + esc(q.page) + '" target="_blank" rel="noopener" class="sub" title="' + esc(q.page) + '">' + esc(q.page.replace(/^https?:\/\//, '').replace(/\/$/, '')) + '</a>'
            : '<span class="sub">—</span>';
          return '<tr>' +
            '<td>' + esc(q.query) + '</td>' +
            '<td class="sub">' + pageCell + '</td>' +
            '<td class="num">' + esc(String(q.llm_score || 0)) + '</td>' +
            '<td>' + (signals || '<span class="sub">—</span>') + '</td>' +
            '<td class="num">' + fmtNum(q.clicks || 0) + '</td>' +
            '<td class="num">' + fmtNum(q.impressions || 0) + '</td>' +
            '<td class="num">' + esc(String(q.ctr != null ? q.ctr + '%' : '—')) + '</td>' +
            '<td class="num">' + esc(String(q.position != null ? q.position : '—')) + '</td></tr>';
        }).join('');
        const summary = '<div class="kpis">' +
          '<div class="kpi"><div class="num">' + fmtNum(t.data.queries.length) + '</div><div class="label">probable LLM queries</div></div>' +
          '<div class="kpi"><div class="num">' + fmtNum(t.data.total_clicks || 0) + '</div><div class="label">clicks</div></div>' +
          '<div class="kpi"><div class="num">' + fmtNum(t.data.total_impressions || 0) + '</div><div class="label">impressions</div></div>' +
          '</div>';
        const body = '<div class="card">' + summary +
          '<table class="gsc-llm-table">' +
          '<thead><tr><th>Query</th><th>Page</th><th>Score</th><th>Signals</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Position</th></tr></thead>' +
          '<tbody>' + (rows || '<tr><td colspan="8" class="sub">No queries yet.</td></tr>') + '</tbody></table>' +
          '<p class="sub">Queries from Google Search Console that match LLM-style patterns (questions, comparisons, long-tail). Latest run ' + esc(t.data.day || '—') + '.</p></div>';
        return '<div class="gsc-llm-prop' + (i === 0 ? ' active' : '') + '" id="gsc-llm-' + esc(t.key) + '">' + body + '</div>';
      }).join('');

      const latestDay = tabs.map(function (t) { return t.data.day; }).filter(Boolean).sort().pop();
      el.innerHTML = '<h2>GSC LLM Queries · probable AI searches</h2>' + tabHtml + panelsHtml + stampHtml(latestDay);
      initPropTabs(el, 'gsc-llm-prop');
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- boot
  document.addEventListener('DOMContentLoaded', function () {
    initSidebar();
    Promise.all([
      loadSummary(),
      loadRank(),
      loadBacklinks(),
      loadFreshness(),
      loadLLM(),
      loadLlmPrompts(),
      loadGscLlmQueries(),
      loadCompetitor(),
    ]).catch(function (e) {
      console.error('Dashboard load error:', e);
    }).finally(function () {
      // Re-apply the hash panel/tab now that async content (prop tabs) exists.
      var r = panelFromHash();
      if (r) activatePanel(r.p, r.t);
    });
  });
})();
