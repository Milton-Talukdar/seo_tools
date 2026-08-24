(function () {
  'use strict';

  const PROPERTIES = {
    vantagecircle: { label: 'Vantage Circle', domain: 'vantagecircle.com' },
    vantagefit: { label: 'Vantage Fit', domain: 'vantagefit.io' },
  };
  const NOT_FOUND = 101;
  const INTENT_SHORT = { informational: 'info', navigational: 'nav', commercial: 'com', transactional: 'trans' };

  const ICONS = {
    overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    seo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    content: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',
    ai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>',
    competitors: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
  };

  const MODULES = [
    {
      id: 'overview', label: 'Overview', icon: ICONS.overview,
      groups: [
        { label: 'Executive', sections: [{ id: 'summary', label: 'Executive Summary', panel: 'summary' }] }
      ]
    },
    {
      id: 'seo', label: 'SEO', icon: ICONS.seo,
      groups: [
        { label: 'Rank', sections: [{ id: 'rank', label: 'Rank Tracker', panel: 'rank', tab: 'vantagecircle' }] },
        { label: 'Links', sections: [{ id: 'backlinks', label: 'Backlinks', panel: 'backlinks' }] }
      ]
    },
    {
      id: 'content', label: 'Content', icon: ICONS.content,
      groups: [
        { label: 'Maintenance', sections: [{ id: 'freshness', label: 'Freshness Queue', panel: 'freshness' }] },
        { label: 'Quality', sections: [{ id: 'cannibalization', label: 'Cannibalization', panel: 'cannibalization' }] },
        { label: 'Engine', sections: [
          { id: 'content-inventory', label: 'Inventory', panel: 'content-inventory' },
          { id: 'content-pipeline', label: 'Pipeline', panel: 'content-pipeline' },
          { id: 'content-clusters', label: 'Topic Clusters', panel: 'content-clusters' },
          { id: 'content-performance', label: 'Performance', panel: 'content-performance' },
          { id: 'content-decay', label: 'Decay', panel: 'content-decay' },
          { id: 'content-links', label: 'Internal Links', panel: 'content-links' },
          { id: 'content-authors', label: 'Authors', panel: 'content-authors' }
        ] }
      ]
    },
    {
      id: 'ai-search', label: 'AI Search', icon: ICONS.ai,
      groups: [
        { label: 'Visibility', sections: [
          { id: 'llm-vc', label: 'Vantage Circle', panel: 'llm', tab: 'vantagecircle' },
          { id: 'llm-vfit', label: 'Vantage Fit', panel: 'llm', tab: 'vantagefit' }
        ]},
        { label: 'Prompts', sections: [
          { id: 'llm-prompts', label: 'Tracked Prompts', panel: 'llm-prompts' },
          { id: 'gsc-llm-queries', label: 'GSC LLM Queries', panel: 'gsc-llm-queries' }
        ]}
      ]
    },
    {
      id: 'competitors', label: 'Competitors', icon: ICONS.competitors,
      groups: [
        { label: 'Track', sections: [
          { id: 'competitor-vc', label: 'Vantage Circle', panel: 'competitor', tab: 'vantagecircle' },
          { id: 'competitor-vfit', label: 'Vantage Fit', panel: 'competitor', tab: 'vantagefit' }
        ]}
      ]
    }
  ];

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

  function parseHash() {
    var h = location.hash.replace(/^#\/?/, '');
    if (!h) return null;
    var parts = h.split('/');
    var moduleId = parts[0];
    var mod = MODULES.find(function (m) { return m.id === moduleId; });
    if (mod && parts.length >= 2) {
      return { module: moduleId, section: parts[1], tab: parts[2] || null };
    }
    // legacy format: #/panel[/tab]
    return { module: null, section: parts[0], tab: parts[1] || null };
  }

  function findSection(sectionId) {
    for (var i = 0; i < MODULES.length; i++) {
      var mod = MODULES[i];
      for (var j = 0; j < mod.groups.length; j++) {
        var sec = mod.groups[j].sections.find(function (s) { return s.id === sectionId; });
        if (sec) return { module: mod, section: sec };
      }
    }
    return null;
  }

  function findSectionByPanelTab(panel, tab) {
    for (var i = 0; i < MODULES.length; i++) {
      var mod = MODULES[i];
      for (var j = 0; j < mod.groups.length; j++) {
        var sec = mod.groups[j].sections.find(function (s) {
          return s.panel === panel && (!tab || s.tab === tab);
        });
        if (sec) return { module: mod, section: sec };
      }
    }
    return null;
  }

  var currentModuleId = null;

  function renderRail() {
    var rail = document.getElementById('vc-rail');
    if (!rail) return;
    var html = '<div class="vc-rail-logo"><div class="vc-rail-logo__mark">VC</div></div>';
    MODULES.forEach(function (m) {
      var first = m.groups[0].sections[0].id;
      html += '<a class="vc-rail-item" href="#/' + esc(m.id) + '/' + esc(first) + '" data-module="' + esc(m.id) + '">' +
        m.icon + '<span class="lab">' + esc(m.label) + '</span></a>';
    });
    html += '<div class="vc-rail-foot"><span>SEO Suite</span></div>';
    rail.innerHTML = html;
    rail.querySelectorAll('.vc-rail-item').forEach(function (it) {
      it.addEventListener('click', function (e) {
        e.preventDefault();
        var modId = it.getAttribute('data-module');
        var first = MODULES.find(function (m) { return m.id === modId; }).groups[0].sections[0].id;
        location.hash = '#/' + modId + '/' + first;
      });
    });
  }

  function renderSubnav(moduleId) {
    var sub = document.getElementById('vc-subnav');
    if (!sub) return;
    var mod = MODULES.find(function (m) { return m.id === moduleId; }) || MODULES[0];
    var html = '<div class="vc-subnav-head">' + esc(mod.label) + '</div><ul class="vc-subnav-list">';
    mod.groups.forEach(function (g) {
      html += '<li class="vc-subnav-group">' + esc(g.label) + '</li>';
      g.sections.forEach(function (s) {
        html += '<li><a class="vc-subnav-item" href="#/' + esc(mod.id) + '/' + esc(s.id) + '" data-section="' + esc(s.id) + '">' + esc(s.label) + '</a></li>';
      });
    });
    html += '</ul><div class="vc-subnav-foot">Select a section to view its dashboard panel.</div>';
    sub.innerHTML = html;
    sub.querySelectorAll('.vc-subnav-item').forEach(function (it) {
      it.addEventListener('click', function (e) {
        e.preventDefault();
        var sec = it.getAttribute('data-section');
        location.hash = '#/' + mod.id + '/' + sec;
      });
    });
  }

  function activateSection(sectionId, tabOverride) {
    var found = findSection(sectionId);
    if (!found && tabOverride) {
      // legacy fallback: sectionId was a panel id, tabOverride was a tab key
      found = findSectionByPanelTab(sectionId, tabOverride);
    }
    if (!found) found = findSection('summary');
    var mod = found.module;
    var sec = found.section;

    if (currentModuleId !== mod.id) {
      renderSubnav(mod.id);
      currentModuleId = mod.id;
    }

    document.querySelectorAll('.vc-rail-item').forEach(function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-module') === mod.id);
    });
    document.querySelectorAll('.vc-subnav-item').forEach(function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-section') === sec.id);
    });

    document.querySelectorAll('.panel').forEach(function (el) { el.classList.remove('active'); });
    var panelEl = document.getElementById('panel-' + sec.panel);
    if (panelEl) panelEl.classList.add('active');

    var tab = tabOverride || sec.tab;
    if (tab && panelEl) {
      var tabBtn = panelEl.querySelector('.prop-tab[data-prop="' + tab + '"]');
      if (tabBtn) tabBtn.click();
    }
    window.scrollTo(0, 0);
  }

  function initNavigation() {
    renderRail();
    var initial = parseHash();
    if (initial) {
      var mod = MODULES.find(function (m) { return m.id === initial.module; });
      renderSubnav(mod ? mod.id : (findSection(initial.section) || findSection('summary')).module.id);
    } else {
      renderSubnav('overview');
    }
    window.addEventListener('hashchange', function () {
      var r = parseHash();
      if (r) activateSection(r.section, r.tab);
    });
    if (initial) activateSection(initial.section, initial.tab);
    else activateSection('summary');
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

  // ---------------------------------------------------------------- content inventory
  function parseJsonList(v) {
    try {
      const parsed = JSON.parse(v || '[]');
      if (Array.isArray(parsed)) return parsed;
      if (parsed && typeof parsed === 'object') return [parsed.name || parsed.toString()];
      if (typeof parsed === 'string') return [parsed];
      return [];
    } catch (e) { return []; }
  }

  function daysAgo(iso) {
    if (!iso) return null;
    const then = new Date(iso);
    if (isNaN(then)) return null;
    return Math.floor((Date.now() - then.getTime()) / 86400000);
  }

  function statusChip(status) {
    const cls = status === 'published' ? 'you' : (status === 'draft' ? 'none' : '');
    return '<span class="chip ' + cls + '">' + esc(status || 'unknown') + '</span>';
  }

  async function loadContentInventory() {
    const el = document.getElementById('panel-content-inventory');
    try {
      const data = await api('content_inventory');
      const rows = data.rows || [];
      const summary = data.summary || {};
      if (!rows.length) {
        el.innerHTML = '<h2>Content Inventory</h2><div class="card">No content inventory data yet. Run <code>python3 content_inventory.py</code> and apply <code>supabase_schema_patch_v8.sql</code>.</div>';
        return;
      }

      const total = summary.total || rows.length;
      const byType = summary.by_type || {};
      const byLang = summary.by_lang || {};
      const byStatus = summary.by_status || {};
      const byProperty = {};
      rows.forEach(function (r) { byProperty[r.property] = (byProperty[r.property] || 0) + 1; });

      const propertyOpts = Object.keys(byProperty).sort().map(function (p) { return '<option value="' + esc(p) + '">' + esc(p) + ' (' + byProperty[p] + ')</option>'; }).join('');
      const typeOpts = Object.keys(byType).sort().map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + ' (' + byType[t] + ')</option>'; }).join('');
      const langOpts = Object.keys(byLang).sort().map(function (l) { return '<option value="' + esc(l) + '">' + esc(l) + ' (' + byLang[l] + ')</option>'; }).join('');
      const statusOpts = Object.keys(byStatus).sort().map(function (s) { return '<option value="' + esc(s) + '">' + esc(s) + ' (' + byStatus[s] + ')</option>'; }).join('');

      const oneYearAgo = new Date();
      oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
      let stale = 0, avgWords = 0, totalWords = 0;
      rows.forEach(function (r) {
        const updated = r.updated_date ? new Date(r.updated_date) : null;
        if (updated && updated < oneYearAgo) stale++;
        totalWords += r.word_count || 0;
      });
      avgWords = rows.length ? Math.round(totalWords / rows.length) : 0;

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(total) + '</div><div class="label">Total items</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(Object.keys(byType).length) + '</div><div class="label">Content types</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(stale) + '</div><div class="label">Stale (&gt;1yr)</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(avgWords) + '</div><div class="label">Avg words</div></div>' +
        '</div>';

      const tableRows = rows.map(function (r) {
        const authors = parseJsonList(r.authors).join(', ');
        const tags = parseJsonList(r.tags).map(function (t) { return '<span class="chip">' + esc(t) + '</span>'; }).join(' ');
        const updatedAgo = daysAgo(r.updated_date);
        const updatedText = r.updated_date ? esc(r.updated_date) + (updatedAgo != null ? ' <span class="sub">(' + updatedAgo + 'd)</span>' : '') : '—';
        const search = [r.title, r.meta_title, r.meta_description, r.slug, r.url, r.excerpt, authors, parseJsonList(r.tags).join(' ')].filter(Boolean).join(' ').toLowerCase();
        return '<tr data-search="' + esc(search) + '" data-property="' + esc(r.property) + '" data-type="' + esc(r.content_type) + '" data-lang="' + esc(r.lang) + '" data-status="' + esc(r.status) + '" data-authors="' + esc(authors.toLowerCase()) + '" data-tags="' + esc(parseJsonList(r.tags).join(' ').toLowerCase()) + '" data-words="' + esc(String(r.word_count || 0)) + '" data-updated="' + esc(String(r.updated_date || '')) + '">' +
          '<td><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc((r.title || r.slug)) + '</a><br><span class="sub">' + esc(r.url.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 55)) + '</span></td>' +
          '<td>' + esc(r.content_type) + '</td>' +
          '<td>' + esc(r.lang) + '</td>' +
          '<td class="sub">' + (authors ? esc(authors) : '—') + '</td>' +
          '<td>' + (tags || '<span class="sub">—</span>') + '</td>' +
          '<td class="num">' + fmtNum(r.word_count || 0) + '</td>' +
          '<td class="num"><span title="internal / external">' + fmtNum(r.internal_links || 0) + ' / ' + fmtNum(r.external_links || 0) + '</span></td>' +
          '<td>' + (r.published_date ? esc(r.published_date) : '—') + '</td>' +
          '<td>' + updatedText + '</td>' +
          '<td>' + statusChip(r.status) + '</td></tr>';
      }).join('');

      const filterHtml = '<div class="table-tools no-print ci-tools">' +
        '<input class="ci-search" type="search" placeholder="Search title, URL, tags…">' +
        '<select class="ci-property"><option value="">All properties</option>' + propertyOpts + '</select>' +
        '<select class="ci-type"><option value="">All types</option>' + typeOpts + '</select>' +
        '<select class="ci-lang"><option value="">All languages</option>' + langOpts + '</select>' +
        '<select class="ci-status"><option value="">All statuses</option>' + statusOpts + '</select>' +
        '<input class="ci-author" type="search" placeholder="Author…">' +
        '<input class="ci-tag" type="search" placeholder="Tag…">' +
        '<button class="ci-export" type="button">Export CSV</button>' +
        '<span class="ci-count sub">' + fmtNum(rows.length) + ' items</span></div>';

      const tableHtml = '<div class="card">' + filterHtml +
        '<table class="ci-table"><thead><tr>' +
        '<th class="sortable" data-sort="title">Title <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="type">Type <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="lang">Lang <span class="arrow"></span></th>' +
        '<th>Authors</th>' +
        '<th>Tags</th>' +
        '<th class="sortable" data-sort="words">Words <span class="arrow"></span></th>' +
        '<th>Links</th>' +
        '<th class="sortable" data-sort="published">Published <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="updated">Updated <span class="arrow"></span></th>' +
        '<th>Status</th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div>';

      el.innerHTML = '<h2>Content Inventory</h2>' + kpiHtml + tableHtml;
      initContentInventoryInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentInventoryInteractions() {
    const wrap = document.getElementById('panel-content-inventory');
    if (!wrap) return;
    const search = wrap.querySelector('.ci-search');
    const propertySel = wrap.querySelector('.ci-property');
    const typeSel = wrap.querySelector('.ci-type');
    const langSel = wrap.querySelector('.ci-lang');
    const statusSel = wrap.querySelector('.ci-status');
    const authorIn = wrap.querySelector('.ci-author');
    const tagIn = wrap.querySelector('.ci-tag');
    const tbody = wrap.querySelector('tbody');
    const rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    const count = wrap.querySelector('.ci-count');
    const ths = wrap.querySelectorAll('th.sortable');
    let sortKey = 'updated', sortDir = -1;

    function applyFilter() {
      const q = search ? search.value.toLowerCase() : '';
      const p = propertySel ? propertySel.value : '';
      const t = typeSel ? typeSel.value : '';
      const l = langSel ? langSel.value : '';
      const s = statusSel ? statusSel.value : '';
      const a = authorIn ? authorIn.value.toLowerCase() : '';
      const tg = tagIn ? tagIn.value.toLowerCase() : '';
      let n = 0;
      rows.forEach(function (r) {
        let ok = true;
        if (q && r.getAttribute('data-search').indexOf(q) === -1) ok = false;
        if (ok && p && r.getAttribute('data-property') !== p) ok = false;
        if (ok && t && r.getAttribute('data-type') !== t) ok = false;
        if (ok && l && r.getAttribute('data-lang') !== l) ok = false;
        if (ok && s && r.getAttribute('data-status') !== s) ok = false;
        if (ok && a && r.getAttribute('data-authors').indexOf(a) === -1) ok = false;
        if (ok && tg && r.getAttribute('data-tags').indexOf(tg) === -1) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' items';
    }

    function keyVal(r, k) {
      if (k === 'title') return r.cells[0].textContent.toLowerCase();
      if (k === 'type') return r.getAttribute('data-type');
      if (k === 'lang') return r.getAttribute('data-lang');
      if (k === 'words') return parseInt(r.getAttribute('data-words') || '0', 10);
      if (k === 'published' || k === 'updated') return r.getAttribute('data-' + k) || '';
      return '';
    }

    function cmp(a, b) {
      const va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey === 'words') {
        return (va - vb) * sortDir;
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        const arr = th.querySelector('.arrow');
        if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        const k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else { sortKey = k; sortDir = (k === 'title' || k === 'type' || k === 'lang' || k === 'published' || k === 'updated') ? 1 : -1; }
        applySort();
      });
    });

    [search, propertySel, typeSel, langSel, statusSel, authorIn, tagIn].forEach(function (el) {
      if (el) el.addEventListener('input', applyFilter);
    });

    const exportBtn = wrap.querySelector('.ci-export');
    if (exportBtn) exportBtn.addEventListener('click', function () {
      const q = function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
      const visible = rows.filter(function (r) { return r.style.display !== 'none'; });
      const csv = ['title,type,lang,authors,tags,words,internal_links,external_links,published,updated,status,url'].concat(visible.map(function (r) {
        return [
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').textContent : r.cells[0].textContent),
          q(r.cells[1].textContent),
          q(r.cells[2].textContent),
          q(r.cells[3].textContent),
          q(r.getAttribute('data-tags')),
          r.getAttribute('data-words'),
          q(r.cells[6].textContent.split('/')[0].trim()),
          q(r.cells[6].textContent.split('/')[1].trim()),
          q(r.cells[7].textContent),
          q(r.getAttribute('data-updated')),
          q(r.cells[9].textContent),
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').href : '')
        ].join(',');
      })).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      a.download = 'content-inventory-' + new Date().toISOString().slice(0, 10) + '.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    });

    applySort();
    applyFilter();
  }

  // ---------------------------------------------------------------- cannibalization
  async function loadCannibalization() {
    const el = document.getElementById('panel-cannibalization');
    try {
      const [circle, fit] = await Promise.all([
        api('cannibalization?property=vantagecircle').catch(function () { return null; }),
        api('cannibalization?property=vantagefit').catch(function () { return null; }),
      ]);

      const tabs = [
        { key: 'vantagecircle', label: 'Vantage Circle', data: circle },
        { key: 'vantagefit', label: 'Vantage Fit', data: fit },
      ];

      const anyData = tabs.some(function (t) { return t.data && (t.data.dilution || t.data.url_flips || t.data.missing_url); });
      if (!anyData) {
        el.innerHTML = '<h2>Cannibalization</h2><div class="card">No cannibalization data available yet.</div>';
        return;
      }

      const tabHtml = '<div class="prop-tabs no-print">' + tabs.map(function (t, i) {
        return '<button class="prop-tab' + (i === 0 ? ' active' : '') + '" data-prop="' + esc(t.key) + '">' + esc(t.label) + '</button>';
      }).join('') + '</div>';

      const panelsHtml = tabs.map(function (t, i) {
        const body = renderCannibalization(t.data) || '<div class="card"><p class="sub">No cannibalization detected for ' + esc(t.label) + '.</p></div>';
        return '<div class="can-prop' + (i === 0 ? ' active' : '') + '" id="can-' + esc(t.key) + '">' + body + '</div>';
      }).join('');

      const latestDay = tabs.map(function (t) { return t.data && t.data.latest_day; }).filter(Boolean).sort().pop();
      el.innerHTML = '<h2>Cannibalization</h2>' + tabHtml + panelsHtml + stampHtml(latestDay);
      initPropTabs(el, 'can-prop');
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  // ---------------------------------------------------------------- content pipeline
  const PIPELINE_STAGES = [
    { id: 'idea', label: 'Idea' },
    { id: 'brief', label: 'Brief' },
    { id: 'draft', label: 'Draft' },
    { id: 'review', label: 'Review' },
    { id: 'scheduled', label: 'Scheduled' },
    { id: 'published', label: 'Published' },
    { id: 'refresh', label: 'Refresh' },
    { id: 'prune', label: 'Prune' }
  ];
  const PIPELINE_PROPS = [
    { id: 'vantagecircle', label: 'Vantage Circle' },
    { id: 'vantagefit', label: 'Vantage Fit' }
  ];

  function pipelineStageChip(stage) {
    const colors = {
      idea: '#dbeafe', brief: '#fef3c7', draft: '#e0e7ff', review: '#fce7f3',
      scheduled: '#d1fae5', published: '#059669', refresh: '#fed7aa', prune: '#fecaca'
    };
    const text = { idea: '#1e40af', brief: '#92400e', draft: '#3730a3', review: '#9d174d',
                   scheduled: '#047857', published: '#fff', refresh: '#9a3412', prune: '#991b1b' };
    const bg = colors[stage] || '#f3f4f6';
    const fg = text[stage] || '#374151';
    return '<span class="chip" style="background:' + bg + ';color:' + fg + '">' + esc(stage) + '</span>';
  }

  async function loadContentPipeline() {
    const el = document.getElementById('panel-content-pipeline');
    try {
      const data = await api('content_pipeline');
      const rows = data.rows || [];
      const stages = data.stages || PIPELINE_STAGES.map(function (s) { return s.id; });
      const byStage = data.by_stage || {};
      const currentProp = 'vantagecircle';

      const propOpts = PIPELINE_PROPS.map(function (p) {
        return '<option value="' + esc(p.id) + '"' + (p.id === currentProp ? ' selected' : '') + '>' + esc(p.label) + '</option>';
      }).join('');

      const stageOpts = PIPELINE_STAGES.map(function (s) {
        return '<option value="' + esc(s.id) + '">' + esc(s.label) + '</option>';
      }).join('');

      const typeOpts = ['posts', 'pages', 'casestudy', 'comparisons', 'glossaries', 'resources', 'webinars', 'reports', 'podcasts'].map(function (t) {
        return '<option value="' + esc(t) + '">' + esc(t) + '</option>';
      }).join('');

      function cardHtml(r) {
        const due = r.due_date ? '<div class="cp-due">📅 ' + esc(r.due_date) + '</div>' : '';
        const owner = r.owner ? '<div class="cp-owner">👤 ' + esc(r.owner) + '</div>' : '';
        const kw = r.target_keyword ? '<div class="cp-kw">🎯 ' + esc(r.target_keyword) + '</div>' : '';
        const cluster = r.cluster ? '<div class="cp-cluster">🏷️ ' + esc(r.cluster) + '</div>' : '';
        const briefIcon = r.brief_goal || r.brief_outline ? '<span class="cp-brief-icon" title="Brief attached">📝</span>' : '';
        return '<div class="cp-card" data-id="' + esc(r.id) + '" data-property="' + esc(r.property || 'vantagecircle') + '" data-stage="' + esc(r.stage) + '" data-due="' + esc(r.due_date || '') + '" draggable="true">' +
          '<div class="cp-title">' + esc(r.title) + ' ' + briefIcon + '</div>' +
          (r.url ? '<a href="' + esc(r.url) + '" target="_blank" class="sub" style="font-size:11px">' + esc(r.url.replace(/^https?:\/\//, '').slice(0, 40)) + '</a>' : '') +
          '<div class="cp-meta">' + owner + due + kw + cluster + '</div>' +
          '</div>';
      }

      const columnsHtml = PIPELINE_STAGES.map(function (s) {
        const items = (byStage[s.id] || []).filter(function (r) { return r.property === currentProp; });
        return '<div class="cp-col" data-stage="' + esc(s.id) + '">' +
          '<div class="cp-col-head">' + esc(s.label) + ' <span class="cp-count">' + items.length + '</span></div>' +
          '<div class="cp-cards">' + items.map(cardHtml).join('') + '</div>' +
          '</div>';
      }).join('');

      function monthKey(d) { return d ? d.slice(0, 7) : '(no date)'; }
      const calendarRows = rows.filter(function (r) { return r.property === currentProp; }).sort(function (a, b) { return (a.due_date || '').localeCompare(b.due_date || ''); });
      const byMonth = {};
      calendarRows.forEach(function (r) {
        const m = monthKey(r.due_date);
        if (!byMonth[m]) byMonth[m] = [];
        byMonth[m].push(r);
      });
      const months = Object.keys(byMonth).sort();
      const calendarHtml = '<div class="cp-calendar">' + months.map(function (m) {
        return '<div class="cp-month"><div class="cp-month-head">' + esc(m) + '</div>' +
          '<div class="cp-month-cards">' + byMonth[m].map(cardHtml).join('') + '</div></div>';
      }).join('') + '</div>';

      const formHtml = '<details class="cp-add no-print"><summary>Add pipeline item</summary>' +
        '<form class="cp-form">' +
        '<input type="text" name="title" placeholder="Title *" required>' +
        '<select name="property">' + propOpts + '</select>' +
        '<select name="content_type"><option value="">Type</option>' + typeOpts + '</select>' +
        '<select name="stage">' + stageOpts + '</select>' +
        '<input type="text" name="owner" placeholder="Owner">' +
        '<input type="date" name="due_date">' +
        '<input type="text" name="target_keyword" placeholder="Target keyword">' +
        '<input type="text" name="cluster" placeholder="Cluster">' +
        '<input type="text" name="brief_goal" placeholder="Brief goal">' +
        '<input type="text" name="brief_keywords" placeholder="Brief keywords (comma separated)">' +
        '<input type="text" name="brief_competitors" placeholder="Competitor URLs (comma separated)">' +
        '<input type="number" name="brief_word_count" placeholder="Target word count">' +
        '<textarea name="brief_outline" placeholder="Brief outline" rows="3"></textarea>' +
        '<textarea name="notes" placeholder="Notes" rows="2"></textarea>' +
        '<button type="submit">Add</button>' +
        '</form></details>';

      const filterHtml = '<div class="table-tools no-print">' +
        '<select class="cp-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<input class="cp-search" type="search" placeholder="Search pipeline…">' +
        '<button class="cp-view-board active" type="button">Board</button>' +
        '<button class="cp-view-calendar" type="button">Calendar</button>' +
        '<span class="cp-total sub">' + rows.length + ' items</span></div>';

      el.innerHTML = '<h2>Content Pipeline</h2>' + filterHtml + formHtml +
        '<div class="cp-view" data-view="board"><div class="card cp-board">' + columnsHtml + '</div></div>' +
        '<div class="cp-view" data-view="calendar" style="display:none">' + calendarHtml + '</div>';
      initContentPipelineInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentPipelineInteractions() {
    const wrap = document.getElementById('panel-content-pipeline');
    if (!wrap) return;
    const propSel = wrap.querySelector('.cp-property');
    const search = wrap.querySelector('.cp-search');
    const form = wrap.querySelector('.cp-form');
    const boardBtn = wrap.querySelector('.cp-view-board');
    const calBtn = wrap.querySelector('.cp-view-calendar');
    const views = Array.prototype.slice.call(wrap.querySelectorAll('.cp-view'));
    const cols = Array.prototype.slice.call(wrap.querySelectorAll('.cp-col'));

    function setView(name) {
      views.forEach(function (v) { v.style.display = v.getAttribute('data-view') === name ? '' : 'none'; });
      if (boardBtn) boardBtn.classList.toggle('active', name === 'board');
      if (calBtn) calBtn.classList.toggle('active', name === 'calendar');
    }

    if (boardBtn) boardBtn.addEventListener('click', function () { setView('board'); });
    if (calBtn) calBtn.addEventListener('click', function () { setView('calendar'); });

    function filter() {
      const p = propSel ? propSel.value : 'all';
      const q = search ? search.value.toLowerCase() : '';
      cols.forEach(function (col) {
        const cards = Array.prototype.slice.call(col.querySelectorAll('.cp-card'));
        let shown = 0;
        cards.forEach(function (card) {
          const ok = (p === 'all' || card.getAttribute('data-property') === p) &&
                     (!q || card.textContent.toLowerCase().indexOf(q) > -1);
          card.style.display = ok ? '' : 'none';
          if (ok) shown++;
        });
        col.querySelector('.cp-count').textContent = shown;
      });
      // also filter calendar cards
      const calCards = Array.prototype.slice.call(wrap.querySelectorAll('.cp-calendar .cp-card'));
      calCards.forEach(function (card) {
        const ok = (p === 'all' || card.getAttribute('data-property') === p) &&
                   (!q || card.textContent.toLowerCase().indexOf(q) > -1);
        card.style.display = ok ? '' : 'none';
      });
    }

    if (propSel) propSel.addEventListener('change', filter);
    if (search) search.addEventListener('input', filter);

    if (form) {
      form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const fd = new FormData(form);
        const body = {};
        ['title', 'property', 'content_type', 'stage', 'owner', 'due_date', 'target_keyword', 'cluster', 'notes', 'brief_goal', 'brief_outline', 'brief_keywords', 'brief_competitors'].forEach(function (k) {
          const v = fd.get(k);
          if (v) body[k] = v;
        });
        const wc = fd.get('brief_word_count');
        if (wc) body.brief_word_count = parseInt(wc, 10);
        if (!body.property) body.property = 'vantagecircle';
        try {
          await fetch('/api/content_pipeline', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
          form.reset();
          loadContentPipeline();
        } catch (err) {
          alert('Save failed: ' + err.message);
        }
      });
    }
  }

  // ---------------------------------------------------------------- content clusters
  async function loadContentClusters() {
    const el = document.getElementById('panel-content-clusters');
    try {
      const data = await api('content_clusters');
      const clusters = data.clusters || [];
      const currentProp = 'vantagecircle';

      const propOpts = PIPELINE_PROPS.map(function (p) {
        return '<option value="' + esc(p.id) + '">' + esc(p.label) + '</option>';
      }).join('');

      const totalItems = clusters.reduce(function (sum, c) { return sum + (c.items || []).length; }, 0);
      const orphanCount = (data.inventory || []).length - totalItems;

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(clusters.length) + '</div><div class="label">Clusters</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(totalItems) + '</div><div class="label">Clustered items</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(Math.max(0, orphanCount)) + '</div><div class="label">Orphan items</div></div>' +
        '</div>';

      const listHtml = clusters.map(function (c) {
        const items = c.items || [];
        const kws = (c.target_keywords || '').split(',').map(function (k) { return k.trim(); }).filter(Boolean).map(function (k) {
          return '<span class="chip">' + esc(k) + '</span>';
        }).join('');
        const itemList = items.slice(0, 5).map(function (i) {
          return '<li><a href="' + esc(i.url) + '" target="_blank">' + esc(i.title || i.url) + '</a> <span class="sub">(' + esc(i.content_type) + ')</span></li>';
        }).join('');
        const more = items.length > 5 ? '<li class="sub">… and ' + (items.length - 5) + ' more</li>' : '';
        return '<div class="cc-card" data-property="' + esc(c.property) + '">' +
          '<h4>' + esc(c.cluster) + ' <span class="cc-count">' + items.length + ' items</span></h4>' +
          (c.pillar_url ? '<div class="sub" style="margin-bottom:8px">Pillar: <a href="' + esc(c.pillar_url) + '" target="_blank">' + esc(c.pillar_url) + '</a></div>' : '') +
          '<div style="margin-bottom:8px">' + (kws || '<span class="sub">No keywords</span>') + '</div>' +
          '<ul class="cc-items">' + itemList + more + '</ul>' +
          '</div>';
      }).join('');

      const filterHtml = '<div class="table-tools no-print">' +
        '<select class="cc-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<input class="cc-search" type="search" placeholder="Search clusters…">' +
        '</div>';

      el.innerHTML = '<h2>Topic Clusters</h2>' + kpiHtml + filterHtml +
        '<div class="card cc-grid">' + (listHtml || '<p class="sub">No clusters yet. Add them in Supabase <code>content_clusters</code> table.</p>') + '</div>';
      initContentClusterInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentClusterInteractions() {
    const wrap = document.getElementById('panel-content-clusters');
    if (!wrap) return;
    const propSel = wrap.querySelector('.cc-property');
    const search = wrap.querySelector('.cc-search');
    const cards = Array.prototype.slice.call(wrap.querySelectorAll('.cc-card'));
    function filter() {
      const p = propSel ? propSel.value : 'all';
      const q = search ? search.value.toLowerCase() : '';
      cards.forEach(function (c) {
        const ok = (p === 'all' || c.getAttribute('data-property') === p) &&
                   (!q || c.textContent.toLowerCase().indexOf(q) > -1);
        c.style.display = ok ? '' : 'none';
      });
    }
    if (propSel) propSel.addEventListener('change', filter);
    if (search) search.addEventListener('input', filter);
    filter();
  }

  // ---------------------------------------------------------------- content performance
  async function loadContentPerformance() {
    const el = document.getElementById('panel-content-performance');
    try {
      const data = await api('content_performance');
      const rows = data.rows || [];
      const summary = data.summary || {};
      const props = ['vantagecircle', 'vantagefit'];
      const currentProp = 'vantagecircle';

      const propOpts = props.map(function (p) {
        return '<option value="' + esc(p) + '"' + (p === currentProp ? ' selected' : '') + '>' + esc(PROPERTIES[p].label) + '</option>';
      }).join('');

      const clusterSet = {};
      rows.forEach(function (r) { if (r.cluster) clusterSet[r.cluster] = true; });
      const clusterOpts = Object.keys(clusterSet).sort().map(function (c) {
        return '<option value="' + esc(c) + '">' + esc(c) + '</option>';
      }).join('');

      const typeSet = {};
      rows.forEach(function (r) { if (r.content_type) typeSet[r.content_type] = true; });
      const typeOpts = Object.keys(typeSet).sort().map(function (t) {
        return '<option value="' + esc(t) + '">' + esc(t) + '</option>';
      }).join('');

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.total || rows.length) + '</div><div class="label">Pages</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.total_clicks || 0) + '</div><div class="label">Clicks (28d)</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.total_impressions || 0) + '</div><div class="label">Impressions</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.total_backlinks || 0) + '</div><div class="label">Backlinks</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.total_refdomains || 0) + '</div><div class="label">Ref domains</div></div>' +
        '<div class="kpi"><div class="num">' + (summary.avg_position || 0) + '</div><div class="label">Avg position</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.with_traffic || 0) + '</div><div class="label">With traffic</div></div>' +
        '</div>';

      function trendBadge(val) {
        if (val === undefined || val === null) return '';
        const cls = val > 0 ? 'up' : (val < 0 ? 'down' : 'flat');
        const arrow = val > 0 ? '↑' : (val < 0 ? '↓' : '—');
        return '<span class="cpf-trend ' + cls + '">' + arrow + ' ' + Math.abs(val) + '%</span>';
      }

      const tableRows = rows.map(function (r) {
        const actionClass = { monitor: '', optimize: 'amber', improve: 'you', expand: 'you', audit: 'rose' }[r.action] || '';
        const cluster = r.cluster ? '<span class="chip">' + esc(r.cluster) + '</span>' : '<span class="sub">—</span>';
        const rank = r.rank_position ? '<span class="pos-chip ' + (r.rank_position <= 10 ? 'up' : (r.rank_position <= 30 ? 'flat' : 'down')) + '">' + esc(String(r.rank_position)) + '</span>' : '—';
        const gscPos = r.gsc_position ? esc(String(Math.round(r.gsc_position * 10) / 10)) : '—';
        const ctr = r.ctr ? (r.ctr * 100).toFixed(2) + '%' : '—';
        const t = r.trends || {};
        const search = [r.title, r.url, r.cluster, r.content_type, r.action, r.reason].filter(Boolean).join(' ').toLowerCase();
        return '<tr data-search="' + esc(search) + '" data-property="' + esc(r.property) + '" data-type="' + esc(r.content_type) + '" data-cluster="' + esc(r.cluster || '') + '" data-clicks="' + (r.clicks || 0) + '" data-impressions="' + (r.impressions || 0) + '" data-backlinks="' + (r.backlinks || 0) + '" data-refdomains="' + (r.refdomains || 0) + '" data-trend7="' + (t.clicks_7d || 0) + '" data-trend28="' + (t.clicks_28d || 0) + '" data-trend90="' + (t.clicks_90d || 0) + '">' +
          '<td><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.title || r.slug) + '</a><br><span class="sub">' + esc(r.url.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 50)) + '</span></td>' +
          '<td>' + esc(r.content_type) + '</td>' +
          '<td>' + cluster + '</td>' +
          '<td class="num">' + fmtNum(r.clicks || 0) + '<br>' + trendBadge(t.clicks_28d) + '</td>' +
          '<td class="num">' + fmtNum(r.impressions || 0) + '</td>' +
          '<td class="num">' + fmtNum(r.backlinks || 0) + '</td>' +
          '<td class="num">' + fmtNum(r.refdomains || 0) + '</td>' +
          '<td class="num">' + ctr + '</td>' +
          '<td class="num">' + gscPos + '</td>' +
          '<td class="num">' + rank + '</td>' +
          '<td>' + (r.rank_keyword ? esc(r.rank_keyword) : '—') + '</td>' +
          '<td><span class="chip ' + actionClass + '">' + esc(r.action) + '</span> <span class="sub">' + esc(r.reason) + '</span></td>' +
          '</tr>';
      }).join('');

      const trendDays = data.trend_days || {};
      const trendNote = 'Trends vs ' + (trendDays.prev28 ? trendDays.prev28 : '—') + ' (28d)';
      const filterHtml = '<div class="table-tools no-print cpf-tools">' +
        '<select class="cpf-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<select class="cpf-type"><option value="all">All types</option>' + typeOpts + '</select>' +
        '<select class="cpf-cluster"><option value="">All clusters</option>' + clusterOpts + '</select>' +
        '<select class="cpf-trend-window"><option value="28">28d trend</option><option value="7">7d trend</option><option value="90">90d trend</option></select>' +
        '<input class="cpf-search" type="search" placeholder="Search title, URL, keyword…">' +
        '<button class="cpf-export" type="button">Export CSV</button>' +
        '<span class="cpf-count sub">' + fmtNum(rows.length) + ' pages</span></div>';

      const tableHtml = '<div class="card">' + filterHtml +
        '<table class="cpf-table"><thead><tr>' +
        '<th class="sortable" data-sort="title">Title <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="type">Type <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="cluster">Cluster <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="clicks">Clicks <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="impressions">Impr. <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="backlinks">BL <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="refdomains">RD <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="ctr">CTR <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="gsc_position">GSC pos <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="rank_position">Rank <span class="arrow"></span></th>' +
        '<th>Tracked kw</th>' +
        '<th>Action</th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div>';

      const note = (data.latest_gsc_day || data.latest_rank_day || data.latest_backlink_day) ?
        '<div class="sub" style="margin-top:8px">Latest data: GSC ' + esc(data.latest_gsc_day || '—') + ' | Rank ' + esc(data.latest_rank_day || '—') + ' | Backlinks ' + esc(data.latest_backlink_day || '—') + ' · ' + esc(trendNote) + '</div>' : '';

      el.innerHTML = '<h2>Content Performance</h2>' + kpiHtml + tableHtml + note;
      initContentPerformanceInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentPerformanceInteractions() {
    const wrap = document.getElementById('panel-content-performance');
    if (!wrap) return;
    const search = wrap.querySelector('.cpf-search');
    const propSel = wrap.querySelector('.cpf-property');
    const typeSel = wrap.querySelector('.cpf-type');
    const clusterSel = wrap.querySelector('.cpf-cluster');
    const trendSel = wrap.querySelector('.cpf-trend-window');
    const tbody = wrap.querySelector('tbody');
    const rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    const count = wrap.querySelector('.cpf-count');
    const ths = wrap.querySelectorAll('th.sortable');
    let sortKey = 'clicks', sortDir = -1;
    let trendWindow = '28';

    function trendForRow(r) {
      const v = parseFloat(r.getAttribute('data-trend' + trendWindow) || '0');
      return isNaN(v) ? 0 : v;
    }

    function renderTrend(r) {
      const cell = r.cells[3];
      const val = trendForRow(r);
      const cls = val > 0 ? 'up' : (val < 0 ? 'down' : 'flat');
      const arrow = val > 0 ? '↑' : (val < 0 ? '↓' : '—');
      const badge = '<span class="cpf-trend ' + cls + '">' + arrow + ' ' + Math.abs(val) + '%</span>';
      const num = cell ? cell.innerHTML.split('<br>')[0] : '';
      if (cell) cell.innerHTML = num + '<br>' + badge;
    }

    function applyFilter() {
      const q = search ? search.value.toLowerCase() : '';
      const p = propSel ? propSel.value : 'all';
      const t = typeSel ? typeSel.value : 'all';
      const c = clusterSel ? clusterSel.value : '';
      let n = 0;
      rows.forEach(function (r) {
        let ok = true;
        if (q && r.getAttribute('data-search').indexOf(q) === -1) ok = false;
        if (ok && p !== 'all' && r.getAttribute('data-property') !== p) ok = false;
        if (ok && t !== 'all' && r.getAttribute('data-type') !== t) ok = false;
        if (ok && c && r.getAttribute('data-cluster') !== c) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' pages';
    }

    function keyVal(r, k) {
      if (k === 'title') return r.cells[0].textContent.toLowerCase();
      if (k === 'type') return r.getAttribute('data-type');
      if (k === 'cluster') return r.getAttribute('data-cluster');
      if (k === 'clicks' || k === 'impressions' || k === 'backlinks' || k === 'refdomains') return parseInt(r.getAttribute('data-' + k) || '0', 10);
      if (k === 'trend') return trendForRow(r);
      if (k === 'ctr' || k === 'gsc_position' || k === 'rank_position') {
        const idx = k === 'ctr' ? 7 : (k === 'gsc_position' ? 8 : 9);
        const txt = r.cells[idx].textContent.replace('%', '').trim();
        return txt === '—' ? 0 : parseFloat(txt);
      }
      return '';
    }

    function cmp(a, b) {
      const va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey === 'clicks' || sortKey === 'impressions' || sortKey === 'backlinks' || sortKey === 'refdomains' || sortKey === 'ctr' || sortKey === 'gsc_position' || sortKey === 'rank_position' || sortKey === 'trend') {
        return (va - vb) * sortDir;
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        const arr = th.querySelector('.arrow');
        if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        const k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else { sortKey = k; sortDir = (k === 'title' || k === 'type' || k === 'cluster') ? 1 : -1; }
        applySort();
      });
    });

    if (trendSel) {
      trendSel.addEventListener('change', function () {
        trendWindow = trendSel.value;
        rows.forEach(renderTrend);
      });
    }

    [search, propSel, typeSel, clusterSel].forEach(function (el) {
      if (el) el.addEventListener('input', applyFilter);
    });

    const exportBtn = wrap.querySelector('.cpf-export');
    if (exportBtn) exportBtn.addEventListener('click', function () {
      const q = function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
      const visible = rows.filter(function (r) { return r.style.display !== 'none'; });
      const csv = ['title,url,type,cluster,clicks,impressions,backlinks,refdomains,ctr,gsc_position,rank_position,rank_keyword,action,reason'].concat(visible.map(function (r) {
        return [
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').textContent : r.cells[0].textContent),
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').href : ''),
          q(r.cells[1].textContent),
          q(r.cells[2].textContent),
          r.getAttribute('data-clicks'),
          r.getAttribute('data-impressions'),
          r.getAttribute('data-backlinks'),
          r.getAttribute('data-refdomains'),
          q(r.cells[7].textContent),
          q(r.cells[8].textContent),
          q(r.cells[9].textContent),
          q(r.cells[10].textContent),
          q(r.cells[11].querySelector('.chip') ? r.cells[11].querySelector('.chip').textContent : ''),
          q(r.cells[11].querySelector('.sub') ? r.cells[11].querySelector('.sub').textContent : '')
        ].join(',');
      })).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      a.download = 'content-performance-' + new Date().toISOString().slice(0, 10) + '.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    });

    applySort();
    applyFilter();
  }

  // ---------------------------------------------------------------- content decay
  async function loadContentDecay() {
    const el = document.getElementById('panel-content-decay');
    try {
      const data = await api('content_decay');
      const rows = data.rows || [];
      const summary = data.summary || {};
      const props = ['vantagecircle', 'vantagefit'];
      const risks = ['critical', 'high', 'medium', 'low'];

      const propOpts = props.map(function (p) {
        return '<option value="' + esc(p) + '">' + esc(PROPERTIES[p].label) + '</option>';
      }).join('');
      const riskOpts = risks.map(function (r) {
        return '<option value="' + esc(r) + '">' + esc(r) + '</option>';
      }).join('');

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.critical || 0) + '</div><div class="label">Critical</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.high || 0) + '</div><div class="label">High</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.medium || 0) + '</div><div class="label">Medium</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(summary.low || 0) + '</div><div class="label">Low</div></div>' +
        '</div>';

      const tableRows = rows.map(function (r) {
        const riskClass = { critical: 'rose', high: 'amber', medium: 'none', low: '' }[r.risk] || '';
        const actionClass = { refresh: 'rose', update: 'amber', optimize: 'amber', improve: 'you', cluster: '', monitor: '' }[r.action] || '';
        const updated = r.days_since_updated != null ? '<span class="sub">' + r.days_since_updated + 'd ago</span>' : '—';
        const cluster = r.cluster ? '<span class="chip">' + esc(r.cluster) + '</span>' : '<span class="sub">—</span>';
        const rank = r.rank_position ? '<span class="pos-chip ' + (r.rank_position <= 10 ? 'up' : (r.rank_position <= 30 ? 'flat' : 'down')) + '">' + esc(String(r.rank_position)) + '</span>' : '—';
        const search = [r.title, r.url, r.cluster, r.content_type, r.risk, r.action, r.reason].filter(Boolean).join(' ').toLowerCase();
        return '<tr data-search="' + esc(search) + '" data-property="' + esc(r.property) + '" data-risk="' + esc(r.risk) + '" data-score="' + (r.score || 0) + '" data-clicks="' + (r.clicks || 0) + '" data-impressions="' + (r.impressions || 0) + '">' +
          '<td><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.title || r.slug) + '</a><br><span class="sub">' + esc(r.url.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 45)) + '</span></td>' +
          '<td>' + esc(r.content_type) + '</td>' +
          '<td>' + cluster + '</td>' +
          '<td class="num">' + fmtNum(r.clicks || 0) + '</td>' +
          '<td class="num">' + fmtNum(r.impressions || 0) + '</td>' +
          '<td class="num">' + rank + '</td>' +
          '<td>' + updated + '</td>' +
          '<td><span class="chip ' + riskClass + '">' + esc(r.risk) + '</span></td>' +
          '<td><span class="chip ' + actionClass + '">' + esc(r.action) + '</span> <span class="sub">' + esc(r.reason) + '</span></td>' +
          '</tr>';
      }).join('');

      const filterHtml = '<div class="table-tools no-print cd-tools">' +
        '<select class="cd-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<select class="cd-risk"><option value="all">All risks</option>' + riskOpts + '</select>' +
        '<input class="cd-search" type="search" placeholder="Search decay queue…">' +
        '<button class="cd-export" type="button">Export CSV</button>' +
        '<span class="cd-count sub">' + fmtNum(rows.length) + ' candidates</span></div>';

      const tableHtml = '<div class="card">' + filterHtml +
        '<table class="cd-table"><thead><tr>' +
        '<th class="sortable" data-sort="title">Title <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="type">Type <span class="arrow"></span></th>' +
        '<th>Cluster</th>' +
        '<th class="sortable" data-sort="clicks">Clicks <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="impressions">Impr. <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="rank">Rank <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="updated">Updated <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="risk">Risk <span class="arrow"></span></th>' +
        '<th>Action</th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div>';

      el.innerHTML = '<h2>Content Decay / Refresh Queue</h2>' + kpiHtml + tableHtml;
      initContentDecayInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentDecayInteractions() {
    const wrap = document.getElementById('panel-content-decay');
    if (!wrap) return;
    const search = wrap.querySelector('.cd-search');
    const propSel = wrap.querySelector('.cd-property');
    const riskSel = wrap.querySelector('.cd-risk');
    const tbody = wrap.querySelector('tbody');
    const rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    const count = wrap.querySelector('.cd-count');
    const ths = wrap.querySelectorAll('th.sortable');
    let sortKey = 'score', sortDir = -1;

    function applyFilter() {
      const q = search ? search.value.toLowerCase() : '';
      const p = propSel ? propSel.value : 'all';
      const risk = riskSel ? riskSel.value : 'all';
      let n = 0;
      rows.forEach(function (r) {
        let ok = true;
        if (q && r.getAttribute('data-search').indexOf(q) === -1) ok = false;
        if (ok && p !== 'all' && r.getAttribute('data-property') !== p) ok = false;
        if (ok && risk !== 'all' && r.getAttribute('data-risk') !== risk) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' candidates';
    }

    function keyVal(r, k) {
      if (k === 'title') return r.cells[0].textContent.toLowerCase();
      if (k === 'type') return r.cells[1].textContent.toLowerCase();
      if (k === 'clicks' || k === 'impressions' || k === 'score') return parseInt(r.getAttribute('data-' + k) || '0', 10);
      if (k === 'rank') {
        const txt = r.cells[5].textContent.trim();
        return txt === '—' ? 999 : parseFloat(txt);
      }
      if (k === 'updated') {
        const txt = r.cells[6].textContent.replace(/\D/g, '').trim();
        return txt ? parseInt(txt, 10) : 0;
      }
      if (k === 'risk') {
        const order = { critical: 4, high: 3, medium: 2, low: 1, healthy: 0 };
        return order[r.getAttribute('data-risk')] || 0;
      }
      return '';
    }

    function cmp(a, b) {
      const va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey === 'clicks' || sortKey === 'impressions' || sortKey === 'score' || sortKey === 'rank' || sortKey === 'updated' || sortKey === 'risk') {
        return (va - vb) * sortDir;
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        const arr = th.querySelector('.arrow');
        if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        const k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else { sortKey = k; sortDir = (k === 'title' || k === 'type') ? 1 : -1; }
        applySort();
      });
    });

    [search, propSel, riskSel].forEach(function (el) {
      if (el) el.addEventListener('input', applyFilter);
    });

    const exportBtn = wrap.querySelector('.cd-export');
    if (exportBtn) exportBtn.addEventListener('click', function () {
      const q = function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
      const visible = rows.filter(function (r) { return r.style.display !== 'none'; });
      const csv = ['title,url,type,cluster,clicks,impressions,rank_position,days_since_updated,risk,action,reason'].concat(visible.map(function (r) {
        return [
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').textContent : r.cells[0].textContent),
          q(r.cells[0].querySelector('a') ? r.cells[0].querySelector('a').href : ''),
          q(r.cells[1].textContent),
          q(r.cells[2].textContent),
          r.getAttribute('data-clicks') || '0',
          r.getAttribute('data-impressions') || '0',
          q(r.cells[5].textContent),
          q(r.cells[6].textContent),
          q(r.getAttribute('data-risk')),
          q(r.cells[8].querySelector('.chip') ? r.cells[8].querySelector('.chip').textContent : ''),
          q(r.cells[8].querySelector('.sub') ? r.cells[8].querySelector('.sub').textContent : '')
        ].join(',');
      })).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      a.download = 'content-decay-' + new Date().toISOString().slice(0, 10) + '.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    });

    applySort();
    applyFilter();
  }

  // ---------------------------------------------------------------- content links
  async function loadContentLinks() {
    const el = document.getElementById('panel-content-links');
    try {
      const data = await api('content_links');
      const suggestions = data.suggestions || [];
      const props = ['vantagecircle', 'vantagefit'];
      const clusters = [''].concat((data.clusters || []).sort());

      const propOpts = props.map(function (p) {
        return '<option value="' + esc(p) + '">' + esc(PROPERTIES[p].label) + '</option>';
      }).join('');
      const clusterOpts = clusters.map(function (c) {
        return '<option value="' + esc(c) + '">' + (c ? esc(c) : 'All clusters') + '</option>';
      }).join('');

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(suggestions.length) + '</div><div class="label">Pages with link gaps</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(suggestions.reduce(function (s, r) { return s + (r.internal_links || 0); }, 0)) + '</div><div class="label">Current internal links</div></div>' +
        '</div>';

      const tableRows = suggestions.map(function (r) {
        const targets = r.targets.map(function (t) {
          return '<a href="' + esc(t.url) + '" target="_blank" rel="noopener" title="score ' + t.score + '">' + esc(t.title || t.url) + '</a>';
        }).join('<br>');
        const search = [r.source_title, r.source_url, r.cluster].filter(Boolean).join(' ').toLowerCase();
        return '<tr data-search="' + esc(search) + '" data-property="' + esc(r.source_property) + '" data-cluster="' + esc(r.cluster || '') + '">' +
          '<td><a href="' + esc(r.source_url) + '" target="_blank" rel="noopener">' + esc(r.source_title || r.source_url) + '</a></td>' +
          '<td>' + esc(r.cluster || '—') + '</td>' +
          '<td class="num">' + fmtNum(r.internal_links || 0) + '</td>' +
          '<td>' + targets + '</td>' +
          '</tr>';
      }).join('');

      const filterHtml = '<div class="table-tools no-print cl-tools">' +
        '<select class="cl-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<select class="cl-cluster"><option value="">All clusters</option>' + clusterOpts + '</select>' +
        '<input class="cl-search" type="search" placeholder="Search link gaps…">' +
        '<span class="cl-count sub">' + fmtNum(suggestions.length) + ' suggestions</span></div>';

      const tableHtml = '<div class="card">' + filterHtml +
        '<table class="cl-table"><thead><tr>' +
        '<th>Source page</th>' +
        '<th>Cluster</th>' +
        '<th>Current internal links</th>' +
        '<th>Suggested links</th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div>';

      el.innerHTML = '<h2>Internal Linking Suggestions</h2>' + kpiHtml + tableHtml;
      initContentLinksInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentLinksInteractions() {
    const wrap = document.getElementById('panel-content-links');
    if (!wrap) return;
    const search = wrap.querySelector('.cl-search');
    const propSel = wrap.querySelector('.cl-property');
    const clusterSel = wrap.querySelector('.cl-cluster');
    const tbody = wrap.querySelector('tbody');
    const rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    const count = wrap.querySelector('.cl-count');

    function applyFilter() {
      const q = search ? search.value.toLowerCase() : '';
      const p = propSel ? propSel.value : 'all';
      const c = clusterSel ? clusterSel.value : '';
      let n = 0;
      rows.forEach(function (r) {
        let ok = true;
        if (q && r.getAttribute('data-search').indexOf(q) === -1) ok = false;
        if (ok && p !== 'all' && r.getAttribute('data-property') !== p) ok = false;
        if (ok && c && r.getAttribute('data-cluster') !== c) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' suggestions';
    }

    [search, propSel, clusterSel].forEach(function (el) {
      if (el) el.addEventListener('input', applyFilter);
    });
    applyFilter();
  }

  // ---------------------------------------------------------------- content authors
  async function loadContentAuthors() {
    const el = document.getElementById('panel-content-authors');
    try {
      const data = await api('content_authors');
      const authors = data.authors || [];
      const props = ['vantagecircle', 'vantagefit'];

      const propOpts = props.map(function (p) {
        return '<option value="' + esc(p) + '">' + esc(PROPERTIES[p].label) + '</option>';
      }).join('');

      const kpiHtml = '<div class="kpis">' +
        '<div class="kpi"><div class="num">' + fmtNum(authors.length) + '</div><div class="label">Authors</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(authors.reduce(function (s, a) { return s + a.pages; }, 0)) + '</div><div class="label">Pages</div></div>' +
        '<div class="kpi"><div class="num">' + fmtNum(authors.reduce(function (s, a) { return s + a.clicks; }, 0)) + '</div><div class="label">Total clicks</div></div>' +
        '</div>';

      const tableRows = authors.map(function (a) {
        return '<tr data-property="all">' +
          '<td><b>' + esc(a.name) + '</b></td>' +
          '<td class="num">' + fmtNum(a.pages) + '</td>' +
          '<td class="num">' + fmtNum(a.clicks) + '</td>' +
          '<td class="num">' + fmtNum(a.impressions) + '</td>' +
          '<td class="num">' + fmtNum(a.top10) + '</td>' +
          '<td class="num">' + (a.avg_position || '—') + '</td>' +
          '<td class="num">' + fmtNum(a.backlinks) + '</td>' +
          '<td class="num">' + fmtNum(a.refdomains) + '</td>' +
          '</tr>';
      }).join('');

      const filterHtml = '<div class="table-tools no-print ca-tools">' +
        '<select class="ca-property"><option value="all">All properties</option>' + propOpts + '</select>' +
        '<input class="ca-search" type="search" placeholder="Search authors…">' +
        '<span class="ca-count sub">' + fmtNum(authors.length) + ' authors</span></div>';

      const tableHtml = '<div class="card">' + filterHtml +
        '<table class="ca-table"><thead><tr>' +
        '<th class="sortable" data-sort="name">Author <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="pages">Pages <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="clicks">Clicks <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="impressions">Impr. <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="top10">Top 10 <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="avg_position">Avg pos <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="backlinks">Backlinks <span class="arrow"></span></th>' +
        '<th class="sortable" data-sort="refdomains">Ref domains <span class="arrow"></span></th>' +
        '</tr></thead><tbody>' + tableRows + '</tbody></table></div>';

      const note = (data.latest_gsc_day || data.latest_rank_day || data.latest_backlink_day) ?
        '<div class="sub" style="margin-top:8px">Latest data: GSC ' + esc(data.latest_gsc_day || '—') + ' | Rank ' + esc(data.latest_rank_day || '—') + ' | Backlinks ' + esc(data.latest_backlink_day || '—') + '</div>' : '';

      el.innerHTML = '<h2>Author Performance</h2>' + kpiHtml + tableHtml + note;
      initContentAuthorsInteractions();
    } catch (e) {
      el.innerHTML = errorCard(e.message);
    }
  }

  function initContentAuthorsInteractions() {
    const wrap = document.getElementById('panel-content-authors');
    if (!wrap) return;
    const search = wrap.querySelector('.ca-search');
    const tbody = wrap.querySelector('tbody');
    const rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    const count = wrap.querySelector('.ca-count');
    const ths = wrap.querySelectorAll('th.sortable');
    let sortKey = 'clicks', sortDir = -1;

    function applyFilter() {
      const q = search ? search.value.toLowerCase() : '';
      let n = 0;
      rows.forEach(function (r) {
        const ok = !q || r.cells[0].textContent.toLowerCase().indexOf(q) !== -1;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' authors';
    }

    function keyVal(r, k) {
      if (k === 'name') return r.cells[0].textContent.toLowerCase();
      const map = { pages: 1, clicks: 2, impressions: 3, top10: 4, avg_position: 5, backlinks: 6, refdomains: 7 };
      const txt = r.cells[map[k]].textContent.replace(/,/g, '').trim();
      return txt === '—' ? 0 : parseFloat(txt);
    }

    function cmp(a, b) {
      const va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey !== 'name') return (va - vb) * sortDir;
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        const arr = th.querySelector('.arrow');
        if (arr) arr.textContent = th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        const k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else { sortKey = k; sortDir = k === 'name' ? 1 : -1; }
        applySort();
      });
    });

    if (search) search.addEventListener('input', applyFilter);
    applySort();
    applyFilter();
  }

  // ---------------------------------------------------------------- boot
  document.addEventListener('DOMContentLoaded', function () {
    initNavigation();
    Promise.all([
      loadSummary(),
      loadRank(),
      loadBacklinks(),
      loadFreshness(),
      loadCannibalization(),
      loadContentInventory(),
      loadContentPipeline(),
      loadContentClusters(),
      loadContentPerformance(),
      loadContentDecay(),
      loadContentLinks(),
      loadContentAuthors(),
      loadLLM(),
      loadLlmPrompts(),
      loadGscLlmQueries(),
      loadCompetitor(),
    ]).catch(function (e) {
      console.error('Dashboard load error:', e);
    }).finally(function () {
      // Re-apply the hash section/tab now that async content (prop tabs) exists.
      var r = parseHash();
      if (r) activateSection(r.section, r.tab);
    });
  });
})();
