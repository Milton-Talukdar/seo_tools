#!/usr/bin/env python3
"""
dashboard.py — generate a self-contained HTML dashboard from seo_suite.db.

One page with a left sidebar tool-switcher: Executive Summary, Rank Tracker
(one page per property — Vantage Circle, Vantage Fit — grouped under a
"Rank Tracker" sidebar heading, each searchable/sortable), Backlinks, and
LLM Visibility (share-of-voice trend, volumes, discovered prompts, silent
citations, latest run). Every panel hides cleanly when its table is missing
or empty.

Usage:
    python3 dashboard.py           # writes index.html and prints its path
    python3 dashboard.py --open    # also opens it in your browser
"""
import argparse
import html
import json
import os
import sqlite3
import webbrowser
from datetime import datetime
from pathlib import Path

from common import DASHBOARD_CSS, DB_PATH
from llm_visibility import BRANDS, MY_DOMAIN, PLATFORMS, PROMPTS_CSV

# Optional Cloudflare Worker endpoint for one-click keyword research.
# Set at build time: KR_WORKER_URL and KR_WORKER_KEY
WORKER_URL = os.environ.get("KR_WORKER_URL", "")
WORKER_KEY = os.environ.get("KR_WORKER_KEY", "")
from rank_track import PROPERTIES

OUT = Path(__file__).parent / "index.html"  # index.html = clean GitHub Pages URL
YOU = BRANDS[0]  # first brand in the list = your brand
NOT_FOUND = 101  # rank sentinel: deeper than the tracked top 100

# vanilla JS: sidebar panel switching (incl. grouped project pages) +
# per-table live search / tag filter / column sorting.
# (plain string, not an f-string — the braces are literal JS/CSS)
SCRIPT = """
(function () {
  // ---- sidebar panel switching ----
  var items = document.querySelectorAll('.nav-item');
  items.forEach(function (it) {
    it.addEventListener('click', function () {
      var p = it.getAttribute('data-panel');
      if (p) {
        items.forEach(function (n) { n.classList.remove('active'); });
        it.classList.add('active');
        document.querySelectorAll('.panel').forEach(function (el) {
          el.classList.remove('active');
        });
        var el = document.getElementById('panel-' + p);
        if (el) el.classList.add('active');
        window.scrollTo(0, 0);
      }
      var t = it.getAttribute('data-target');
      if (t) {
        var te = document.getElementById(t);
        if (te) te.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  // ---- rank tracker: per-property search + tag filter + sorting ----
  document.querySelectorAll('.rank-prop').forEach(function (box) {
    var search = box.querySelector('.rank-search');
    var tagSel = box.querySelector('.tag-filter');
    var tbody = box.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var count = box.querySelector('.rank-count');
    var ths = box.querySelectorAll('th.sortable');
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
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' keywords';
    }

    function keyVal(r, k) {
      var v = r.getAttribute('data-' + k);
      if (k === 'keyword') return v;
      return v === '' || v === null ? null : parseFloat(v);  // '' = unranked / no data
    }

    function cmp(a, b) {
      var va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey !== 'keyword') {          // missing values always sort last
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
        if (arr) arr.textContent =
          th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else {
          sortKey = k;
          // keyword + position: best/ascending first; volume/traffic/kd: biggest first
          sortDir = (k === 'keyword' || k === 'position') ? 1 : -1;
        }
        applySort();
      });
    });

    if (search) search.addEventListener('input', applyFilter);
    if (tagSel) tagSel.addEventListener('change', applyFilter);
    applySort();
    applyFilter();
  });

  // ---- keyword research: one-click search via Cloudflare Worker ----
  (function () {
    var form = document.querySelector('.research-form[data-worker-url]');
    if (!form) return;
    var btn = form.querySelector('.research-search-btn');
    var ta = form.querySelector('.research-seed-input');
    var status = form.parentNode.querySelector('.research-status');
    if (!btn || !ta) return;
    btn.addEventListener('click', function () {
      var seed = ta.value.trim();
      if (!seed) {
        if (status) { status.textContent = 'Please enter a seed keyword.'; status.className = 'research-status sub err'; }
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Searching…';
      if (status) { status.textContent = 'Sending request…'; status.className = 'research-status sub'; }
      fetch(form.getAttribute('data-worker-url'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Research-Key': form.getAttribute('data-worker-key')
        },
        body: JSON.stringify({ seed: seed, limit: '100' })
      }).then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok || !data.ok) throw new Error(data.error || 'Request failed');
          if (status) { status.textContent = 'Research started. Results appear in ~1 minute. Refresh the dashboard.'; status.className = 'research-status sub ok'; }
          ta.value = '';
        });
      }).catch(function (e) {
        if (status) { status.textContent = 'Error: ' + e.message; status.className = 'research-status sub err'; }
      }).finally(function () {
        btn.disabled = false;
        btn.textContent = 'Search';
      });
    });
  })();

  // ---- keyword research: seed / search / volume / KD filters ----
  (function () {
    var wrap = document.querySelector('.research-wrap');
    if (!wrap) return;
    var seed = wrap.querySelector('.research-seed');
    var search = wrap.querySelector('.research-search');
    var volMin = wrap.querySelector('.research-vol-min');
    var volMax = wrap.querySelector('.research-vol-max');
    var kdMin = wrap.querySelector('.research-kd-min');
    var kdMax = wrap.querySelector('.research-kd-max');
    var rows = Array.prototype.slice.call(wrap.querySelectorAll('tbody tr'));
    var count = wrap.querySelector('.research-count');
    function num(v) { return v === '' || v == null ? NaN : parseFloat(v); }
    function apply() {
      var s = seed ? seed.value : '';
      var q = search ? search.value.toLowerCase() : '';
      var vmin = num(volMin ? volMin.value : ''), vmax = num(volMax ? volMax.value : '');
      var kmin = num(kdMin ? kdMin.value : ''), kmax = num(kdMax ? kdMax.value : '');
      var n = 0;
      rows.forEach(function (r) {
        var ok = true;
        if (s && r.getAttribute('data-seed') !== s) ok = false;
        if (ok && q && r.getAttribute('data-keyword').indexOf(q) === -1) ok = false;
        var v = parseFloat(r.getAttribute('data-volume'));
        if (ok && !isNaN(vmin) && v < vmin) ok = false;
        if (ok && !isNaN(vmax) && v > vmax) ok = false;
        var k = parseFloat(r.getAttribute('data-kd'));
        if (ok && !isNaN(kmin) && k < kmin) ok = false;
        if (ok && !isNaN(kmax) && k > kmax) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' keywords';
    }
    [seed, search, volMin, volMax, kdMin, kdMax].forEach(function (el) {
      if (el) el.addEventListener('input', apply);
    });
    apply();
  })();

  // ---- keyword research: show seed details card when a seed is selected ----
  (function () {
    var seedSel = document.querySelector('.research-wrap .research-seed');
    var cards = document.querySelectorAll('.seed-detail-card');
    if (!seedSel || !cards.length) return;
    function update() {
      var val = seedSel.value;
      cards.forEach(function (c) {
        c.style.display = c.getAttribute('data-seed') === val ? 'block' : 'none';
      });
    }
    seedSel.addEventListener('change', update);
    update();
  })();

  // ---- keyword research: click any keyword to populate the search box ----
  (function () {
    var wrap = document.querySelector('.research-wrap');
    var form = document.querySelector('.research-form[data-worker-url]');
    if (!wrap || !form) return;
    var ta = form.querySelector('.research-seed-input');
    if (!ta) return;
    wrap.querySelectorAll('tbody td:first-child').forEach(function (td) {
      td.style.cursor = 'pointer';
      td.title = 'Click to search this keyword';
      td.addEventListener('click', function () {
        var kw = td.textContent.replace(/\s+/g, ' ').trim();
        // remove the seed badge text if present
        kw = kw.replace(/seed\s*$/i, '').trim();
        ta.value = kw;
        ta.focus();
        window.scrollTo({ top: form.offsetTop - 20, behavior: 'smooth' });
      });
    });
  })();

  // ---- competitor tracker tabs / filters / export ----
  (function () {
    function fmtDate(iso) {
      var d = new Date(iso);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    function daysAgo(n) {
      var d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - n); return d;
    }
    function inRange(ts, days) {
      if (days === 0) return true;
      return new Date(ts) >= daysAgo(days);
    }
    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
    }
    function sectionOf(url) {
      try {
        var locale = { 'en': 1, 'fr': 1, 'es': 1, 'de': 1, 'it': 1, 'pt': 1, 'ja': 1, 'ko': 1, 'zh': 1, 'en-us': 1, 'en-gb': 1, 'en-au': 1, 'en-in': 1, 'en-ca': 1, 'fr-ca': 1 };
        var p = new URL(url).pathname.replace(/^\/+/, '').split('/').filter(Boolean);
        if (p.length > 1 && locale[p[0]]) p.shift();
        return p[0] || 'home';
      } catch (e) { return 'other'; }
    }
    function typeLabel(t, n) {
      var map = {
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
      var pair = map[t] || [t, t + 's'];
      return pair[n === 1 ? 0 : 1];
    }
    function renderCompetitorCharts(box, changes, competitors, selfDomain) {
      var np = changes.filter(function (c) { return c.change_type === 'new_page'; });
      // new pages by competitor
      var counts = {}, colors = ['#4f46e5', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2', '#7c3aed'];
      np.forEach(function (c) { counts[c.domain] = (counts[c.domain] || 0) + 1; });
      var sorted = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; });
      var max = Math.max.apply(null, Object.values(counts).concat([1]));
      var html = sorted.map(function (d, i) {
        return "<div class='comp-hbar'><span class='name'>" + escapeHtml(d) + "</span>" +
          "<div class='track'><div class='fill' style='width:" + (counts[d] / max * 100) + "%;background:" + colors[i % colors.length] + "'></div></div>" +
          "<b>" + counts[d] + "</b></div>";
      }).join('');
      box.querySelector('.chart-new-pages').innerHTML = html || '<p class="sub">No new pages in range.</p>';

      // section matrix
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
          return '<tr><td><b>' + escapeHtml(d) + '</b></td>' + cells + '<td><b>' + rowTotal + '</b></td></tr>';
        }).join('');
        box.querySelector('.chart-sections').innerHTML = "<div class='comp-matrix'><table><thead><tr><th>Competitor</th>" +
          topSections.map(function (s) { return '<th>/' + escapeHtml(s) + '</th>'; }).join('') + "<th>Total</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
      } else {
        box.querySelector('.chart-sections').innerHTML = '<p class="sub">No new pages in range.</p>';
      }

      // net words
      var words = {};
      changes.filter(function (c) { return c.change_type === 'content_update' && c.details && c.details.word_count_change; })
        .forEach(function (c) { words[c.domain] = (words[c.domain] || 0) + c.details.word_count_change; });
      var wSorted = Object.keys(words).sort(function (a, b) { return Math.abs(words[b]) - Math.abs(words[a]); });
      var wMax = Math.max.apply(null, Object.values(words).map(Math.abs).concat([1]));
      box.querySelector('.chart-words').innerHTML = wSorted.map(function (d) {
        var v = words[d];
        var color = v >= 0 ? '#059669' : '#dc2626';
        return "<div class='comp-hbar'><span class='name'>" + escapeHtml(d) + "</span>" +
          "<div class='track'><div class='fill' style='width:" + (Math.abs(v) / wMax * 100) + "%;background:" + color + "'></div></div>" +
          "<b style='color:" + color + "'>" + (v > 0 ? '+' : '') + v + "</b></div>";
      }).join('') || '<p class="sub">No content updates in range.</p>';

      // type breakdown
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

      // weekly trend (last 12 weeks)
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
    function renderCompetitorPanel(box) {
      var data = JSON.parse(box.getAttribute('data-competitor-json') || '{}');
      var changes = data.changes || [];
      var competitors = data.competitors || {};
      var selfDomain = data.self_domain || '';
      var days = parseInt(box.querySelector('.comp-days').value, 10) || 30;
      var filtered = changes.filter(function (c) { return inRange(c.timestamp, days); });
      var compFilter = box.querySelector('.comp-filter-competitor');
      var typeFilter = box.querySelector('.comp-filter-type');
      if (compFilter && compFilter.value) filtered = filtered.filter(function (c) { return c.domain === compFilter.value; });
      if (typeFilter && typeFilter.value) filtered = filtered.filter(function (c) { return c.change_type === typeFilter.value; });

      // overview stats
      var totalPages = Object.values(competitors).reduce(function (s, d) { return s + (d.total_urls || 0); }, 0);
      var selfNew = filtered.filter(function (c) { return c.change_type === 'new_page' && c.domain === selfDomain; }).length;
      var rivalDomains = Object.keys(competitors).filter(function (d) { return d !== selfDomain; });
      var rivalNew = filtered.filter(function (c) { return c.change_type === 'new_page' && c.domain !== selfDomain; }).length;
      var rivalAvg = rivalDomains.length ? Math.round(rivalNew / rivalDomains.length) : 0;
      var kpis = box.querySelector('.comp-kpis');
      kpis.innerHTML = [
        "<div class='comp-kpi'><div class='num'>" + Object.keys(competitors).length + "</div><div class='label'>Tracked competitors</div></div>",
        "<div class='comp-kpi'><div class='num'>" + totalPages.toLocaleString() + "</div><div class='label'>Pages indexed</div></div>",
        "<div class='comp-kpi'><div class='num'>" + filtered.filter(function (c) { return c.change_type === 'new_page'; }).length + "</div><div class='label'>New pages</div></div>",
        "<div class='comp-kpi'><div class='num'>" + filtered.filter(function (c) { return c.change_type === 'content_update'; }).length + "</div><div class='label'>Content updates</div></div>",
        "<div class='comp-kpi'><div class='num'>" + filtered.length + "</div><div class='label'>All changes</div></div>",
        "<div class='comp-kpi'><div class='num' style='color:" + (selfNew >= rivalAvg ? '#059669' : '#dc2626') + "'>" + selfNew + " : " + rivalAvg + "</div><div class='label'>You vs rival avg</div></div>"
      ].join('');

      // competitor cards
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
        return "<div class='comp-card" + (isSelf ? ' you' : '') + "'><div class='comp-card-head'><h4>" + escapeHtml(d.name || domain) +
          (isSelf ? "<span class='comp-you-badge'>you</span>" : '') + "</h4><div class='domain'>" + escapeHtml(domain) + "</div></div>" +
          "<div class='row'><span>Pages</span><b>" + (d.total_urls || 0).toLocaleString() + "</b></div>" +
          "<div class='row'><span>New</span><b style='color:#059669'>" + dc.filter(function (c) { return c.change_type === 'new_page'; }).length + "</b></div>" +
          "<div class='row'><span>Updates</span><b style='color:#d97706'>" + dc.filter(function (c) { return c.change_type === 'content_update'; }).length + "</b></div>" +
          "<div class='row'><span>Total</span><b>" + dc.length + "</b></div>" +
          "<div class='row'><span>Top section</span><b>" + (topSec ? escapeHtml(topSec[0]) + ' (' + topSec[1] + ')' : '—') + "</b></div>" +
          "<div class='bar'><div style='width:" + ((d.total_urls || 0) / maxPages * 100).toFixed(0) + "%;background:" + color + "'></div></div>";
      }).join('');

      // recent timeline (overview)
      box.querySelector('.comp-overview-timeline').innerHTML = renderTimelineList(filtered.slice(0, 10), true);

      // changes tab timeline
      box.querySelector('.comp-changes-timeline').innerHTML = renderTimelineList(filtered, false);

      // seo moves
      var seo = filtered.filter(function (c) { return ['title_change', 'meta_change', 'h1_change', 'schema_change'].indexOf(c.change_type) > -1; });
      box.querySelector('.comp-seo-list').innerHTML = seo.slice(0, 200).map(function (c) {
        var det = c.details || {};
        var body;
        if (c.change_type === 'schema_change') {
          body = (det.added_schemas || []).map(function (s) { return "<span class='comp-seo-tag up'>+" + escapeHtml(s) + "</span>"; }).join(' ') +
            (det.removed_schemas || []).map(function (s) { return "<span class='comp-seo-tag down'>-" + escapeHtml(s) + "</span>"; }).join(' ');
        } else {
          var oldVal = det.old_title || det.old_meta || det.old_h1 || '';
          var newVal = det.new_title || det.new_meta || det.new_h1 || '';
          body = "<div class='sub'>" + escapeHtml(oldVal) + "</div><div>→</div><div>" + escapeHtml(newVal) + "</div>";
        }
        return "<div class='card' style='margin:8px 0;padding:12px 14px'><div style='display:flex;gap:10px;align-items:center;margin-bottom:6px'>" +
          "<span class='comp-badge " + c.change_type + "'>" + typeLabel(c.change_type, 1) + "</span>" +
          "<b>" + escapeHtml(c.competitor) + "</b> <a href='" + escapeHtml(c.url) + "' target='_blank' class='sub'>" + escapeHtml(c.title || c.url) + "</a></div>" + body + "</div>";
      }).join('') || '<p class="sub">No on-page SEO changes in range.</p>';

      // activity charts
      renderCompetitorCharts(box, filtered, competitors, selfDomain);
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
        if (g.day !== lastDay) { html += "<div class='comp-day'>" + g.day + "</div>"; lastDay = g.day; }
        var counts = {};
        g.items.forEach(function (c) { counts[c.change_type] = (counts[c.change_type] || 0) + 1; });
        var summary = Object.entries(counts).sort(function (a, b) { return b[1] - a[1]; }).map(function (e) {
          return e[1] + ' ' + typeLabel(e[0], e[1]);
        }).join(' · ');
        html += "<div class='comp-group'>" +
          "<div class='comp-group-head' onclick=\\\"this.parentElement.classList.toggle('open')\\\">" +
          "<span class='comp-group-name'>" + escapeHtml(g.competitor) + "</span>" +
          "<span class='comp-group-summary'>" + summary + "</span></div>" +
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
        tags += "<span class='comp-seo-tag'>" + det.word_count.toLocaleString() + "w</span>";
      } else if (c.change_type === 'redirect' && det.status_code) {
        tags += "<span class='comp-seo-tag'>" + det.status_code + "</span>";
      }
      var detailHtml = '';
      if (!compact) {
        var parts = [];
        if (det.old_title && det.new_title) parts.push('Title: "' + escapeHtml(det.old_title) + '" → "' + escapeHtml(det.new_title) + '"');
        if (det.old_meta && det.new_meta) parts.push('Meta: "' + escapeHtml(det.old_meta) + '" → "' + escapeHtml(det.new_meta) + '"');
        if (det.old_h1 && det.new_h1) parts.push('H1: "' + escapeHtml(det.old_h1) + '" → "' + escapeHtml(det.new_h1) + '"');
        if (det.redirect && det.redirect_to) parts.push('Redirect → <a href="' + escapeHtml(det.redirect_to) + '" target="_blank">' + escapeHtml(det.redirect_to) + '</a>');
        if (det.added && det.added.length) parts.push('<div style="color:#059669"><b>+ added</b><br>' + det.added.map(escapeHtml).join('<br>') + '</div>');
        if (det.removed && det.removed.length) parts.push('<div style="color:#dc2626"><b>- removed</b><br>' + det.removed.map(escapeHtml).join('<br>') + '</div>');
        if (parts.length) detailHtml = "<div class='comp-row-detail'>" + parts.join('<br>') + "</div>";
      }
      return "<div>" +
        "<div class='comp-row' onclick=\\\"this.nextElementSibling.classList.toggle('open')\\\">" +
        "<span class='comp-badge " + c.change_type + "'>" + typeLabel(c.change_type, 1) + "</span>" +
        "<span style='flex:1'>" + escapeHtml(c.title || c.url) + "</span>" +
        "<span class='sub'>" + escapeHtml(sectionOf(c.url)) + "</span>" + tags + "</div>" +
        detailHtml + "</div>";
    }
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
      box.querySelector('.comp-export').addEventListener('click', function () {
        var data = JSON.parse(box.getAttribute('data-competitor-json') || '{}');
        var rows = data.changes || [];
        var csv = ['timestamp,property,competitor,domain,url,change_type,title,details'].join('\\n') +
          rows.map(function (c) {
            return [c.timestamp, c.property, c.competitor, c.domain, c.url, c.change_type, c.title, JSON.stringify(c.details || {})]
              .map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
          }).join('\\n');
        var blob = new Blob([csv], { type: 'text/csv' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'competitor_changes_' + data.property + '.csv';
        a.click();
      });
    });
  })();

  // ---- content freshness: search + filters + sorting ----
  (function () {
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
        if (arr) arr.textContent =
          th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
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
  })();
})();
"""


def esc(s):
    return html.escape(str(s), quote=True)


def brand_chip(brand):
    cls = "chip you" if brand == YOU else "chip"
    return f'<span class="{cls}">{esc(brand)}</span>'


def fmt_pos(pos):
    return str(pos) if pos is not None and pos < NOT_FOUND else "—"


def table_days(con, table, limit=2):
    try:
        return [r[0] for r in con.execute(
            f"SELECT DISTINCT day FROM {table} ORDER BY day DESC LIMIT {limit}")]
    except sqlite3.OperationalError:
        return []


# ---------------------------------------------------------------- exec summary
def exec_summary(con):
    cards = []

    # rank KPIs — aggregate each property's latest full-coverage day
    rprops = [(p, prop_days(con, p)) for p in PROPERTIES]
    rprops = [(p, days) for p, days in rprops if days]
    if rprops:
        rows, prev = [], {}
        latest_day, prev_day = "", ""
        for p, days in rprops:
            rows += con.execute(
                "SELECT keyword, position FROM rank_snapshots "
                "WHERE day=? AND property=?", (days[0], p)).fetchall()
            latest_day = max(latest_day, days[0])
            if len(days) > 1:
                for k, pos in con.execute(
                        "SELECT keyword, position FROM rank_snapshots "
                        "WHERE day=? AND property=?", (days[1], p)):
                    prev[(p, k)] = pos
                prev_day = max(prev_day, days[1])
        ranked = [p for _, p in rows if p is not None]
        cards.append((
            f"{sum(p <= 3 for p in ranked)}",
            f"keywords in Google top 3<br>{sum(p <= 10 for p in ranked)} in top 10 "
            f"· {sum(p <= 50 for p in ranked)} in top 50<br>"
            f"<span class='sub'>{len(ranked)}/{len(rows)} ranked ({esc(latest_day)})</span>"))
        if prev:
            movers = sorted(
                (((prev.get((p, k)) or NOT_FOUND) - (pos or NOT_FOUND), k)
                 for p, days in rprops
                 for k, pos in con.execute(
                     "SELECT keyword, position FROM rank_snapshots "
                     "WHERE day=? AND property=?", (days[0], p)).fetchall()
                 if (prev.get((p, k)) or NOT_FOUND) != (pos or NOT_FOUND)),
                key=lambda m: -m[0])
            if movers:
                d, k = movers[0]
                cls, arrow = ("up", "▲") if d > 0 else ("down", "▼")
                cards.append((
                    f"<span class='delta {cls}'>{arrow}{abs(d)}</span>",
                    f"biggest rank move vs {esc(prev_day)}<br>{esc(k[:60])}"))

    # backlink KPI
    bdays = table_days(con, "backlink_snapshots")
    if bdays:
        latest = con.execute(
            "SELECT refdomains FROM backlink_snapshots WHERE day=?",
            (bdays[0],)).fetchone()
        if len(bdays) > 1:
            prev = con.execute(
                "SELECT refdomains FROM backlink_snapshots WHERE day=?",
                (bdays[1],)).fetchone()
            net = latest[0] - prev[0]
            cls, arrow = ("up", "+") if net >= 0 else ("down", "-")
            delta_html = (f"<span class='delta {cls}'>{arrow}{abs(net):,} "
                          f"vs {esc(bdays[1])}</span>")
        else:
            delta_html = "<span class='sub'>first run</span>"
        cards.append((f"{latest[0]:,}",
                      f"referring domains<br>{delta_html}"))

    # AI share-of-voice KPI
    ldays = table_days(con, "llm_snapshots")
    if ldays:
        rows = con.execute(
            "SELECT mentions FROM llm_snapshots WHERE day=?", (ldays[0],)).fetchall()
        n = len(rows) or 1
        sov = sum(json.loads(m).get(YOU, False) for m, in rows) / n * 100
        cards.append((f"{sov:.0f}%",
                      f"AI share of voice<br>"
                      f"<span class='sub'>{esc(ldays[0])} · {len(rows)} answers</span>"))

    if not cards:
        return ""
    kpis = "".join(f"<div class='kpi'><div class='num'>{num}</div>"
                   f"<div class='label'>{label}</div></div>" for num, label in cards)
    return f"<h2>Executive summary</h2><div class='kpis'>{kpis}</div>"


# ---------------------------------------------------------------- rank tracker
INTENT_SHORT = {"informational": "info", "navigational": "nav",
                "commercial": "com", "transactional": "trans"}


def prop_days(con, prop, limit=2):
    counts = con.execute(
        "SELECT day, COUNT(*) FROM rank_snapshots WHERE property=? "
        "GROUP BY day ORDER BY day DESC", (prop,)).fetchall()
    if not counts:
        return []
    # ignore partial days (e.g. --limit smoke tests): keep days covering
    # at least half of the fullest day's keywords
    fullest = max(c for _, c in counts)
    return [d for d, c in counts if c >= fullest / 2][:limit]


def pos_cell(prev, cur, has_prev):
    """Ahrefs-style: current position, 'from prev', colored change chip."""
    cur_s = fmt_pos(cur)
    if not has_prev:
        return f"<td class='num'><b>{cur_s}</b></td>", ""
    if prev is None and cur is None:
        return "<td class='num'>—</td>", ""
    if prev is None:  # previously unranked, now ranking
        return (f"<td class='num'><b>{cur_s}</b> "
                f"<span class='pos-chip new'>New</span></td>",
                str(NOT_FOUND - cur))
    if cur is None:
        return (f"<td class='num'>— <span class='sub'>from {prev}</span> "
                f"<span class='pos-chip down'>▼{NOT_FOUND - prev if False else 'out'}</span></td>",
                str((prev or NOT_FOUND) - NOT_FOUND))
    d = prev - cur
    if d > 0:
        chip = f"<span class='pos-chip up'>▲{d}</span>"
    elif d < 0:
        chip = f"<span class='pos-chip down'>▼{abs(d)}</span>"
    else:
        chip = "<span class='pos-chip flat'>·</span>"
    prev_s = f" <span class='sub'>from {prev}</span>" if d else ""
    return f"<td class='num'><b>{cur_s}</b>{prev_s} {chip}</td>", str(d)


def traffic_cell(meta):
    cur, prev = meta.get("traffic_cur"), meta.get("traffic_prev")
    if cur is None:
        return "<td class='num sub'>—</td>", ""
    cur_s = f"{cur:,.0f}"
    if prev is None:
        return f"<td class='num'>{cur_s}</td>", str(cur)
    d = cur - prev
    if d > 0:
        delta = f" <span class='delta up'>+{d:,.0f}</span>"
    elif d < 0:
        delta = f" <span class='delta down'>{d:,.0f}</span>"
    else:
        delta = ""
    return f"<td class='num'>{cur_s}{delta}</td>", str(cur)


def intent_cell(meta):
    try:
        flags = json.loads(meta.get("intent") or "{}")
    except (TypeError, ValueError):
        flags = {}
    labels = [short for name, short in INTENT_SHORT.items() if flags.get(name)]
    if not labels:
        return "<td class='sub'>—</td>"
    return "<td>" + " ".join(f"<span class='feat-chip'>{l}</span>"
                             for l in labels) + "</td>"


def features_cell(meta):
    try:
        feats = json.loads(meta.get("serp_features") or "[]")
    except (TypeError, ValueError):
        feats = []
    if not feats:
        return "<td class='sub'>—</td>"
    shown = "".join(f"<span class='feat-chip'>{esc(f)}</span>" for f in feats[:4])
    more = f"<span class='sub'>+{len(feats) - 4}</span>" if len(feats) > 4 else ""
    return f"<td>{shown}{more}</td>"


def rank_property_block(con, prop):
    cfg = PROPERTIES[prop]
    days = prop_days(con, prop)
    if not days:
        return ""
    rows = con.execute(
        "SELECT keyword, position, url FROM rank_snapshots "
        "WHERE day=? AND property=?", (days[0], prop)).fetchall()
    if not rows:
        return ""
    prev = {}
    if len(days) > 1:
        prev = dict(con.execute(
            "SELECT keyword, position FROM rank_snapshots "
            "WHERE day=? AND property=?", (days[1], prop)).fetchall())
    meta = {}
    for r in con.execute(
            "SELECT keyword, tag, volume, kd, cpc, intent, branded, serp_features,"
            " traffic_prev, traffic_cur FROM keyword_meta WHERE property=?",
            (prop,)):
        meta[r[0]] = {"tag": r[1] or "", "volume": r[2], "kd": r[3], "cpc": r[4],
                      "intent": r[5], "branded": r[6], "serp_features": r[7],
                      "traffic_prev": r[8], "traffic_cur": r[9]}
    rows.sort(key=lambda r: (r[1] is None, r[1] or NOT_FOUND, r[0]))
    tags = sorted({m["tag"] for m in meta.values() if m["tag"]})

    out = [f"<div class='rank-prop active' id='rank-{prop}'>"
           f"<div class='card'>"
           f"<div class='table-tools no-print'>"
           f"<input class='rank-search' type='search' placeholder='Search keywords or tags…'>"
           f"<select class='tag-filter'>"
           f"<option value=''>All tags</option>"]
    for t in tags:
        out.append(f"<option value='{esc(t.lower())}'>{esc(t)}</option>")
    out.append(f"<option value='__untagged__'>Untagged</option></select>"
               f"<span class='rank-count sub'>{len(rows)} keywords</span></div>"
               f"<table class='rank-table'><thead><tr>"
               f"<th class='sortable' data-sort='keyword'>Keyword <span class='arrow'></span></th>"
               f"<th>Tag</th>"
               f"<th class='sortable' data-sort='position'>Position <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='volume'>Volume <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='traffic'>Traffic <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='kd'>KD <span class='arrow'></span></th>"
               f"<th>Intent</th><th>Branded</th><th>SERP features</th><th>URL</th>"
               f"</tr></thead><tbody>")
    for keyword, pos, url in rows:
        m = meta.get(keyword, {"tag": "", "volume": None, "kd": None, "cpc": None,
                               "intent": None, "branded": 0, "serp_features": None,
                               "traffic_prev": None, "traffic_cur": None})
        prev_pos = prev.get(keyword) if days and len(days) > 1 else None
        has_prev = len(days) > 1 and keyword in prev
        pos_html, data_change = pos_cell(prev_pos, pos, has_prev)
        traffic_html, data_traffic = traffic_cell(m)
        short_url = url.replace("https://", "").replace("http://", "")[:50]
        vol = m["volume"]
        kd = m["kd"]
        out.append(
            f"<tr data-keyword='{esc(keyword.lower())}' "
            f"data-search='{esc((keyword + ' ' + m['tag']).lower())}' "
            f"data-tag='{esc(m['tag'].lower())}' "
            f"data-position='{'' if pos is None else pos}' "
            f"data-change='{data_change}' "
            f"data-volume='{'' if vol is None else vol}' "
            f"data-traffic='{data_traffic}' "
            f"data-kd='{'' if kd is None else kd}'>"
            f"<td>{esc(keyword)}</td>"
            f"<td class='tag-cell'>{esc(m['tag']) or '—'}</td>"
            f"{pos_html}"
            f"<td class='num'>{f'{vol:,}' if vol is not None else '<span class=sub>—</span>'}</td>"
            f"{traffic_html}"
            f"<td class='num'>{f'{kd:.0f}' if kd is not None else '<span class=sub>—</span>'}</td>"
            f"{intent_cell(m)}"
            f"<td>{'<span class=badge-b>B</span>' if m['branded'] else ''}</td>"
            f"{features_cell(m)}"
            f"<td class='sub'>{esc(short_url)}</td></tr>")
    out.append("</tbody></table><p class='sub'>Google US top 100 for "
               f"{esc(cfg['domain'])} — current: {esc(days[0])}"
               + (f", previous: {esc(days[1])}" if len(days) > 1 else "")
               + ". Volume / traffic / KD / intent from keyword_meta "
               "(Ahrefs overview import + monthly enrich.py). "
               "— = unranked or no data. "
               "<span class='no-print'>Type to filter, pick a tag, click a column header to sort.</span></p>"
               "</div></div>")
    return "".join(out)


def rank_property_page(con, prop):
    """Full rank-tracker page body for one property; '' when it has no data."""
    cfg = PROPERTIES[prop]
    days = prop_days(con, prop)
    if not days:
        return ""
    block = rank_property_block(con, prop)
    if not block:
        return ""
    return (f"<h2>Rank Tracker — {esc(cfg['label'])} · Google US top 100 "
            f"<span class='sub'>({esc(days[0])})</span></h2>" + block)


# ---------------------------------------------------------------- backlinks
def backlinks_section(con):
    days = table_days(con, "backlink_snapshots", limit=8)
    if not days:
        return ""
    out = ["<h2>Backlinks</h2>"]
    rows = [con.execute(
        "SELECT day, backlinks, refdomains, rank FROM backlink_snapshots "
        "WHERE day=?", (d,)).fetchone() for d in reversed(days)]
    mx = max(r[2] for r in rows) or 1
    out.append("<div class='card'><b>Profile totals</b><table>"
               "<tr><th>date</th><th>backlinks</th><th>refdomains</th>"
               "<th></th><th>DFS rank</th></tr>")
    for day, backlinks, refdomains, rank in rows:
        out.append(f"<tr><td><b>{esc(day)}</b></td>"
                   f"<td class='vol'>{backlinks:,}</td>"
                   f"<td class='vol'>{refdomains:,}</td>"
                   f"<td><div class='bar'><div style='width:{refdomains / mx * 100:.0f}%'>"
                   f"</div></div></td><td>{rank}</td></tr>")
    out.append("</table></div>")

    edays = table_days(con, "refdomain_events", limit=2)
    if edays:
        events = con.execute(
            "SELECT day, event, domain, rank FROM refdomain_events "
            "WHERE day IN (?, ?) ORDER BY day DESC, event, rank DESC",
            (edays[0], edays[-1])).fetchall()
        if events:
            out.append("<div class='card'><b>Recent new / lost referring domains</b>"
                       "<table><tr><th>date</th><th>event</th><th>domain</th>"
                       "<th>rank</th></tr>")
            for day, event, domain, rank in events[:40]:
                chip = (f"<span class='chip you'>{event}</span>" if event == "new"
                        else f"<span class='chip none'>{event}</span>")
                if domain == "(total)":
                    out.append(f"<tr><td>{esc(day)}</td><td>{chip}</td>"
                               f"<td class='sub'>API aggregate count</td>"
                               f"<td class='vol'>{rank}</td></tr>")
                else:
                    out.append(f"<tr><td>{esc(day)}</td><td>{chip}</td>"
                               f"<td>{esc(domain)}</td>"
                               f"<td class='vol'>{rank if rank is not None else '—'}</td></tr>")
            out.append("</table><p class='sub'>Weekly API runs record aggregate "
                       "counts; per-domain detail comes from the one-time Ahrefs "
                       "import (import_ahrefs.py).</p></div>")
    return "".join(out)


# ---------------------------------------------------------------- LLM sections
def sov_trend_section(con):
    try:
        rows = con.execute("SELECT day, mentions FROM llm_snapshots").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    agg = {}
    for day, mj in rows:
        m = json.loads(mj)
        slot = agg.setdefault(day, {b: [0, 0] for b in BRANDS})
        for b in BRANDS:
            slot[b][0] += bool(m.get(b))
            slot[b][1] += 1
    days = sorted(agg, reverse=True)
    head = "".join(
        f"<th>{esc(b)}{' (you)' if b == YOU else ''}</th>" for b in BRANDS)
    body = ""
    for day in days:
        cells = ""
        for b in BRANDS:
            got, total = agg[day][b]
            pct = got / total * 100 if total else 0
            cls = "bar you" if b == YOU else "bar"
            cells += (f'<td><div class="{cls}"><div style="width:{pct:.0f}%"></div></div>'
                      f'<span class="sub">{pct:.0f}%</span></td>')
        body += f"<tr><td><b>{esc(day)}</b></td>{cells}</tr>"
    return (f"<h2>AI share of voice trend</h2><div class='card'><table>"
            f"<tr><th>run date</th>{head}</tr>{body}</table>"
            f"<p class='sub'>% of prompt × platform answers mentioning each brand.</p></div>")


def volume_section(con):
    try:
        rows = con.execute(
            "SELECT v.keyword, v.ai_search_volume, v.trend_json FROM volumes v "
            "JOIN (SELECT keyword, MAX(day) d FROM volumes GROUP BY keyword) m "
            "ON v.keyword = m.keyword AND v.day = m.d "
            "ORDER BY v.ai_search_volume DESC").fetchall()
    except sqlite3.OperationalError:
        return ""  # llm_discover.py has not run yet
    if not rows:
        return ""
    out = ["<h2>AI search volume — your seed keywords</h2><div class='card'><table>"
           "<tr><th>keyword</th><th>AI searches/mo</th><th>12-month trend</th></tr>"]
    for kw, vol, tj in rows:
        months = json.loads(tj or "[]")
        vals = [m.get("ai_search_volume") or 0 for m in reversed(months)]  # oldest → newest
        mx = max(vals) or 1
        spark = "".join(f"<i style='height:{max(1, round(v / mx * 18))}px'></i>"
                        for v in vals)
        out.append(f"<tr><td>{esc(kw)}</td><td class='vol'>{vol}</td>"
                   f"<td><span class='spark'>{spark}</span></td></tr>")
    out.append("</table><p class='sub'>How often each phrase is typed into AI tools per "
               "month (US). Updated monthly by llm_discover.py.</p></div>")
    return "".join(out)


def discovered_section(con):
    try:
        rows = con.execute(
            "SELECT query, platform, ai_search_volume, seed FROM discovered "
            "ORDER BY ai_search_volume DESC LIMIT 40").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    tracked = {l.strip().lower() for l in open(PROMPTS_CSV, encoding="utf-8")
               if l.strip() and not l.startswith("#")}
    out = ["<h2>Discovered prompts — what people really ask AI</h2>"
           "<div class='card'><table>"
           "<tr><th>question</th><th>platform</th><th>AI searches/mo</th>"
           "<th>tracked?</th></tr>"]
    for q, platform, vol, seed in rows:
        mark = ("<span class='chip tracked'>in tracker</span>" if q.lower() in tracked
                else "<span class='chip'>—</span>")
        out.append(f"<tr><td>{esc(q)}</td>"
                   f"<td><span class='chip'>{esc(platform)}</span></td>"
                   f"<td class='vol'>{vol}</td><td>{mark}</td></tr>")
    out.append("</table><p class='sub'>Real user questions from the LLM Mentions "
               "database matched to your seeds. Add high-volume ones to prompts.csv "
               "to track them weekly.</p></div>")
    return "".join(out)


def silent_section(con):
    try:
        days = [r[0] for r in con.execute(
            "SELECT DISTINCT day FROM silent ORDER BY day DESC LIMIT 2")]
    except sqlite3.OperationalError:
        return ""
    if not days:
        return ""
    rows = con.execute(
        "SELECT query, platform, ai_search_volume FROM silent "
        "WHERE day=? ORDER BY ai_search_volume DESC", (days[0],)).fetchall()
    prev = None
    if len(days) > 1:
        prev = con.execute("SELECT COUNT(*) FROM silent WHERE day=?",
                           (days[1],)).fetchone()[0]
    trend = f" · was {prev} at previous check" if prev is not None else ""
    out = [f"<h2>Silent citations — your content, no brand credit "
           f"<span class='sub'>({len(rows)} found{esc(trend)})</span></h2>"
           f"<div class='card'><table>"
           f"<tr><th>query</th><th>platform</th><th>AI searches/mo</th></tr>"]
    for q, platform, vol in rows:
        out.append(f"<tr><td>{esc(q)}</td>"
                   f"<td><span class='chip'>{esc(platform)}</span></td>"
                   f"<td class='vol'>{vol}</td></tr>")
    out.append("</table><p class='sub'>AI answers that cite "
               f"{esc(MY_DOMAIN)} as a source but never name your brand. Fix: weave "
               "brand references into these pages so the AI lifts the name along "
               "with the content. Checked monthly (top-100 sample of answers "
               "referencing your domain).</p></div>")
    return "".join(out)


def latest_llm_section(con):
    try:
        row = con.execute("SELECT MAX(day) FROM llm_snapshots").fetchone()
    except sqlite3.OperationalError:
        return ""
    if not row or not row[0]:
        return ""
    day = row[0]
    rows = con.execute(
        "SELECT prompt, platform, mentions, cited_mine, answer "
        "FROM llm_snapshots WHERE day=? ORDER BY prompt, platform", (day,)).fetchall()
    by_prompt = {}
    for prompt, platform, mj, cited, answer in rows:
        by_prompt.setdefault(prompt, []).append((platform, json.loads(mj), cited, answer))
    out = [f"<h2>Latest LLM run — {esc(day)}</h2>"]
    for prompt, entries in by_prompt.items():
        chips = []
        for platform, m, cited, _ in entries:
            found = [b for b in BRANDS if m.get(b)]
            tag = " ".join(brand_chip(b) for b in found) if found else '<span class="chip none">no brands</span>'
            cite = '<span class="chip cite">your site cited</span>' if cited else ""
            chips.append(f'<div><span class="plat">{esc(platform)}</span> {tag} {cite}</div>')
        answers = "".join(
            f"<div><span class='plat'>{esc(p)}</span></div>"
            f"<div class='answer'>{esc(a[:4000])}</div>"
            for p, _, _, a in entries)
        out.append(f"<div class='card'><b>{esc(prompt)}</b>{''.join(chips)}"
                   f"<details><summary>show raw answers</summary>{answers}</details></div>")
    return "".join(out)


def keyword_row_html(seed, keyword, vol, kd, cpc, comp, intent, feats, is_seed=False):
    """Format one keyword/seed row for the research table."""
    feats_list = []
    try:
        feats_list = json.loads(feats or "[]") or []
    except (TypeError, ValueError):
        pass
    feat_html = "".join(f"<span class='feat-chip'>{esc(f)}</span>" for f in feats_list[:4])
    if len(feats_list) > 4:
        feat_html += f"<span class='sub'>+{len(feats_list) - 4}</span>"
    intent_html = (f"<span class='feat-chip'>{esc(intent)}</span>" if intent else "")
    vol_v = vol if vol is not None else ""
    kd_v = kd if kd is not None else ""
    cls = "seed-row" if is_seed else ""
    label = "<span class='seed-badge'>seed</span>" if is_seed else ""
    return (
        f"<tr class='{cls}' data-keyword='{esc(keyword.lower())}' "
        f"data-seed='{esc(seed)}' "
        f"data-volume='{vol_v}' data-kd='{kd_v}'>"
        f"<td>{esc(keyword)}{label}</td>"
        f"<td class='tag-cell'>{esc(seed)}</td>"
        f"<td class='num'>{f'{vol:,}' if vol is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'{kd:.0f}' if kd is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'${cpc:.2f}' if cpc is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'{comp:.2f}' if comp is not None else '<span class=sub>—</span>'}</td>"
        f"<td>{intent_html or '<span class=sub>—</span>'}</td>"
        f"<td>{feat_html or '<span class=sub>—</span>'}</td>"
        f"</tr>")


def seed_details_card(con):
    """Hidden-by-default details card populated by JS when a seed is selected."""
    try:
        rows = con.execute(
            "SELECT seed, volume, kd, cpc, competition, intent, "
            "serp_features, fetched FROM seed_overview "
            "ORDER BY seed").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    cards = []
    for seed, vol, kd, cpc, comp, intent, feats, fetched in rows:
        intent_html = (f"<span class='feat-chip'>{esc(intent)}</span>" if intent else "")
        cards.append(
            f"<div class='seed-detail-card card' data-seed='{esc(seed)}' style='display:none;'>"
            f"<div class='seed-detail-head'>"
            f"<div class='seed-detail-keyword'>{esc(seed)}</div>"
            f"<div class='seed-detail-meta'>seed keyword</div></div>"
            f"<div class='seed-detail-kpis'>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{vol:,}' if vol is not None else '—'}</div>"
            f"<div class='seed-detail-label'>Volume</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{kd:.0f}' if kd is not None else '—'}</div>"
            f"<div class='seed-detail-label'>KD</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'${cpc:.2f}' if cpc is not None else '—'}</div>"
            f"<div class='seed-detail-label'>CPC</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{comp:.2f}' if comp is not None else '—'}</div>"
            f"<div class='seed-detail-label'>Competition</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{intent_html or '—'}</div>"
            f"<div class='seed-detail-label'>Intent</div></div>"
            f"</div></div>")
    return f"<div class='seed-detail-wrap'>{''.join(cards)}</div>"


def research_section(con):
    """Keyword Research panel: search card + seed details + ideas table."""
    rows = con.execute(
        "SELECT seed, keyword, volume, kd, cpc, competition, intent, "
        "serp_features, fetched FROM keyword_research "
        "ORDER BY seed, volume DESC NULLS LAST, keyword").fetchall()
    details = seed_details_card(con)
    if not rows:
        return details + _research_empty_card()

    seeds = sorted({r[0] for r in rows})
    seed_options = "".join(f"<option value='{esc(s)}'>{esc(s)}</option>" for s in seeds)

    body = [f"<h2>Keyword Research</h2>{_research_empty_card()}{details}"
            f"<div class='card research-wrap'>"
            f"<div class='table-tools no-print research-tools'>"
            f"<select class='research-seed'><option value=''>All seeds</option>"
            f"{seed_options}</select>"
            f"<input class='research-search' type='search' placeholder='Search keywords…'>"
            f"<input class='research-vol-min' type='number' placeholder='Min vol' min='0'>"
            f"<input class='research-vol-max' type='number' placeholder='Max vol' min='0'>"
            f"<input class='research-kd-min' type='number' placeholder='Min KD' min='0' max='100'>"
            f"<input class='research-kd-max' type='number' placeholder='Max KD' min='0' max='100'>"
            f"<span class='research-count sub'>{len(rows)} keywords</span></div>"
            f"<table class='research-table'><thead><tr>"
            f"<th>Keyword</th><th>Seed</th><th>Volume</th><th>KD</th>"
            f"<th>CPC</th><th>Competition</th><th>Intent</th><th>SERP features</th>"
            f"</tr></thead><tbody>"]

    # render seed rows first, then idea rows
    by_seed = {}
    for seed, keyword, vol, kd, cpc, comp, intent, feats, fetched in rows:
        by_seed.setdefault(seed, []).append((keyword, vol, kd, cpc, comp, intent, feats, fetched))

    for seed in sorted(by_seed):
        # seed overview from seed_overview table
        ov = con.execute(
            "SELECT volume, kd, cpc, competition, intent, serp_features "
            "FROM seed_overview WHERE seed=?", (seed,)).fetchone()
        if ov:
            body.append(keyword_row_html(seed, seed, *ov, is_seed=True))
        # idea rows
        for keyword, vol, kd, cpc, comp, intent, feats, fetched in by_seed[seed]:
            if keyword.lower() == seed.lower():
                continue  # already rendered as seed row
            body.append(keyword_row_html(seed, keyword, vol, kd, cpc, comp, intent, feats))

    body.append("</tbody></table></div>")
    return "".join(body)


def _research_empty_card():
    workflow_url = ("https://github.com/Milton-Talukdar/seo_tools/actions/workflows/"
                    "keyword-research.yml")
    if WORKER_URL and WORKER_KEY:
        return (f"<div class='card research-empty'>"
                f"<h3>Keywords Explorer</h3>"
                f"<p class='sub'>Get keyword ideas with Search Volume, Keyword Difficulty, "
                f"CPC and SERP features. Type a seed keyword and click Search.</p>"
                f"<div class='research-form no-print' data-worker-url='{esc(WORKER_URL)}' "
                f"data-worker-key='{esc(WORKER_KEY)}'>"
                f"<textarea class='research-seed-input' placeholder='Enter keywords separated by commas or new lines'>"
                f"</textarea>"
                f"<div class='research-form-foot'>"
                f"<span>🌎 United States</span>"
                f"<button type='button' class='research-search-btn'>Search</button></div></div>"
                f"<p class='research-status sub'></p>"
                f"</div>")
    return (f"<div class='card research-empty'>"
            f"<h3>Keywords Explorer</h3>"
            f"<p class='sub'>Get keyword ideas with Search Volume, Keyword Difficulty, "
            f"CPC and SERP features. Add seed keywords below, then run research on GitHub.</p>"
            f"<div class='research-form no-print'>"
            f"<textarea class='research-seed-input' placeholder='Enter keywords separated by commas or new lines'>"
            f"</textarea>"
            f"<div class='research-form-foot'>"
            f"<span>🌎 United States</span>"
            f"<a class='research-btn' href='{esc(workflow_url)}' target='_blank'>"
            f"Run on GitHub Actions →</a></div></div>"
            f"<p class='sub'>The workflow uses repository secrets, so API credentials are never exposed. "
            f"Copy the keywords above and paste them into the <b>seed</b> field.</p>"
            f"</div>")


# ---------------------------------------------------------------- competitor tracker
COMPETITOR_PROPERTIES = {
    "vantagecircle": {"label": "Vantage Circle", "domain": "vantagecircle.com"},
    "vantagefit": {"label": "Vantage Fit", "domain": "vantagefit.io"},
}
COMPETITOR_TYPE_OPTIONS = [
    ("", "All types"),
    ("new_page", "New page"),
    ("content_update", "Content update"),
    ("title_change", "Title change"),
    ("meta_change", "Meta change"),
    ("h1_change", "H1 change"),
    ("schema_change", "Schema change"),
    ("redirect", "Redirect"),
    ("page_removed", "Page removed"),
    ("url_case_change", "URL case change"),
]


def competitor_property_data(con, prop):
    cfg = COMPETITOR_PROPERTIES[prop]
    self_domain = cfg["domain"]
    try:
        changes = con.execute(
            "SELECT timestamp, property, competitor, domain, url, change_type, title, details_json "
            "FROM competitor_changes WHERE property=? ORDER BY timestamp DESC", (prop,)
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    if not changes:
        return None

    try:
        snap_rows = con.execute(
            "SELECT competitor, domain, total_urls, last_successful_crawl "
            "FROM competitor_snapshots WHERE property=? "
            "AND day=(SELECT MAX(day) FROM competitor_snapshots WHERE property=?)",
            (prop, prop),
        ).fetchall()
    except sqlite3.OperationalError:
        snap_rows = []

    competitors = {}
    for comp, domain, total_urls, last_crawl in snap_rows:
        competitors[domain] = {"name": comp, "total_urls": total_urls or 0,
                               "last_successful_crawl": last_crawl or ""}

    change_list = []
    for ts, _, competitor, domain, url, ctype, title, details_json in changes:
        det = json.loads(details_json or "{}")
        change_list.append({
            "timestamp": ts, "property": prop, "competitor": competitor,
            "domain": domain, "url": url, "change_type": ctype,
            "title": title or "", "details": det,
        })
        if domain not in competitors:
            competitors[domain] = {"name": competitor, "total_urls": 0, "last_successful_crawl": ""}

    # build competitor dropdown options
    comp_options = "".join(
        f"<option value='{esc(d)}'>{esc(c['name'])}</option>"
        for d, c in sorted(competitors.items(), key=lambda x: x[1]["name"]))
    type_options = "".join(
        f"<option value='{esc(v)}'>{esc(l)}</option>" for v, l in COMPETITOR_TYPE_OPTIONS)

    last_run = change_list[0]["timestamp"][:19].replace("T", " ") if change_list else "—"
    json_payload = json.dumps({
        "property": prop, "self_domain": self_domain,
        "competitors": competitors, "changes": change_list,
    }, default=str)

    html = (f"<h2>Competitor Tracker — {esc(cfg['label'])} "
            f"<span class='sub'>(last run: {esc(last_run)} UTC)</span></h2>"
            f"<div class='card competitor-box' data-competitor-json='{esc(json_payload)}'>"
            f"<div class='comp-tabs no-print'>"
            f"<button class='comp-tab active' data-tab='overview'>Overview</button>"
            f"<button class='comp-tab' data-tab='changes'>Changes</button>"
            f"<button class='comp-tab' data-tab='seo'>SEO Moves</button>"
            f"<button class='comp-tab' data-tab='activity'>Activity</button>"
            f"<button class='comp-export'>Export CSV</button></div>"
            # overview
            f"<div class='comp-panel active' data-tab='overview'>"
            f"<div class='comp-kpis'></div>"
            f"<div class='comp-cards'></div>"
            f"<h4 style='margin-top:20px'>Recent changes</h4>"
            f"<div class='comp-overview-timeline comp-timeline'></div></div>"
            # changes
            f"<div class='comp-panel' data-tab='changes'>"
            f"<div class='comp-filters no-print'>"
            f"<select class='comp-filter-competitor'><option value=''>All competitors</option>{comp_options}</select>"
            f"<select class='comp-filter-type'><option value=''>All types</option>{type_options}</select>"
            f"<select class='comp-days'><option value='1'>Last 24 hours</option>"
            f"<option value='7'>Last 7 days</option>"
            f"<option value='14'>Last 14 days</option>"
            f"<option value='30' selected>Last 30 days</option>"
            f"<option value='90'>Last 90 days</option>"
            f"<option value='0'>All time</option></select></div>"
            f"<div class='comp-changes-timeline comp-timeline'></div></div>"
            # seo moves
            f"<div class='comp-panel' data-tab='seo'>"
            f"<p class='sub'>On-page SEO edits competitors made to existing pages — title rewrites, meta changes, H1 swaps, and schema changes.</p>"
            f"<div class='comp-seo-list'></div></div>"
            # activity
            f"<div class='comp-panel' data-tab='activity'>"
            f"<div class='comp-chart'><h4>New pages by competitor</h4><div class='chart-new-pages'></div></div>"
            f"<div class='comp-chart'><h4>New pages by section</h4><div class='chart-sections'></div></div>"
            f"<div class='comp-chart'><h4>Net content investment (words)</h4><div class='chart-words'></div></div>"
            f"<div class='comp-chart'><h4>Change type breakdown</h4><div class='chart-types'></div></div>"
            f"<div class='comp-chart'><h4>Weekly trend</h4><div class='chart-trend'></div></div></div>"
            f"</div>")
    return html


def competitor_tracker_pages(con):
    """Return list of (panel_id, label, html) for properties with data."""
    pages = []
    for prop in COMPETITOR_PROPERTIES:
        body = competitor_property_data(con, prop)
        if body:
            pages.append((f"comp-{prop}", COMPETITOR_PROPERTIES[prop]["label"], body))
    return pages


# ---------------------------------------------------------------- content freshness

def freshness_section(con):
    """Content Freshness / Decay panel: KPIs + candidates + full table."""
    latest = con.execute("SELECT MAX(day) FROM freshness_scores").fetchone()[0]
    if not latest:
        return ""

    rows = con.execute(
        """SELECT url, property, page_type, title, age_days, word_count,
                  freshness_score, depth_score, decay_risk, target_keyword,
                  position, volume, action, reason, priority_score,
                  traffic_28d, traffic_drop_pct, rank_drop_30d
           FROM freshness_scores WHERE day=? ORDER BY priority_score DESC""",
        (latest,),
    ).fetchall()
    if not rows:
        return ""

    total = len(rows)
    high_risk = sum(1 for r in rows if r[8] == "HIGH")
    avg_age = int(sum(r[4] for r in rows if r[4] < 9000) / max(1, sum(1 for r in rows if r[4] < 9000)))
    action_counts = {}
    for r in rows:
        action_counts[r[12]] = action_counts.get(r[12], 0) + 1

    def risk_chip(risk):
        cls = {"LOW": "you", "MEDIUM": "cite", "HIGH": "none"}.get(risk, "")
        return f"<span class='chip {cls}'>{esc(risk)}</span>"

    def action_chip(action):
        cls = {"UPDATE": "none", "REFRESH": "cite", "EXPAND": "cite",
               "PRUNE": "none", "FIX": "none", "MONITOR": "you"}.get(action, "")
        return f"<span class='chip {cls}'>{esc(action)}</span>"

    def bar(score, color_class=""):
        return (f"<div class='bar {color_class}'><div style='width:{max(0, min(100, score))}%'"
                f" title='{score}'></div></div>")

    # KPI cards
    cards = [
        ("Pages monitored", f"{total}", f"as of {latest}"),
        ("High decay risk", f"{high_risk}", f"{round(high_risk/total*100, 1)}% of pages"),
        ("Average age", f"{avg_age}", "days since last update"),
        ("Needs action", f"{sum(v for k, v in action_counts.items() if k != 'MONITOR')}", "refresh/update/prune/fix"),
    ]
    kpi_html = "<div class='kpis'>" + "".join(
        f"<div class='kpi'><div class='num'>{esc(num)}</div><div class='label'>{esc(label)}"
        f"<br><span class='sub'>{esc(sub)}</span></div></div>"
        for label, num, sub in cards
    ) + "</div>"

    # Top candidates
    candidates = [r for r in rows if r[12] != "MONITOR"][:15]
    candidates_html = ""
    if candidates:
        cand_rows = []
        for r in candidates:
            url, prop, ptype, title, age, wc, fresh, depth, risk, kw, pos, vol, action, reason, prio, t28, tdrop, rdrop = r
            display = (title or url).replace("https://", "").replace("http://", "")
            if len(display) > 65:
                display = display[:62] + "…"
            cand_rows.append(
                f"<tr>"
                f"<td><a href='{esc(url)}' target='_blank'>{esc(display)}</a></td>"
                f"<td>{esc(prop)}</td>"
                f"<td>{age}</td>"
                f"<td>{action_chip(action)}</td>"
                f"<td>{prio}</td>"
                f"<td class='sub'>{esc(reason)}</td>"
                f"</tr>"
            )
        candidates_html = (
            f"<div class='card'><b>Top action candidates</b>"
            f"<table><thead><tr><th>Page</th><th>Property</th><th>Age</th>"
            f"<th>Action</th><th>Priority</th><th>Reason</th></tr></thead><tbody>"
            f"{''.join(cand_rows)}</tbody></table></div>")

    # Full table
    table_rows = []
    for r in rows:
        url, prop, ptype, title, age, wc, fresh, depth, risk, kw, pos, vol, action, reason, prio, t28, tdrop, rdrop = r
        display = (title or url).replace("https://", "").replace("http://", "")
        if len(display) > 70:
            display = display[:67] + "…"
        search = " ".join(str(x).lower() for x in (url, title, kw, prop, ptype, action, reason, risk) if x)
        table_rows.append(
            f"<tr data-search='{esc(search)}' data-property='{esc(prop)}' data-type='{esc(ptype)}'"
            f" data-action='{esc(action)}' data-risk='{esc(risk)}' data-age='{age}' data-priority='{prio}'>"
            f"<td><a href='{esc(url)}' target='_blank'>{esc(display)}</a></td>"
            f"<td>{esc(prop)}</td><td>{esc(ptype)}</td><td>{age}</td><td>{wc}</td>"
            f"<td>{fresh}</td><td>{depth}</td><td>{risk_chip(risk)}</td>"
            f"<td>{esc(kw or '')}</td><td>{pos if pos and pos <= 100 else '—'}</td><td>{vol or '—'}</td>"
            f"<td>{action_chip(action)}</td><td class='sub'>{esc(reason)}</td>"
            f"</tr>"
        )

    properties = sorted({r[1] for r in rows})
    types = sorted({r[2] for r in rows})
    actions = sorted({r[12] for r in rows})
    risks = sorted({r[8] for r in rows})

    prop_opts = "<option value=''>All properties</option>" + "".join(f"<option value='{esc(p)}'>{esc(p)}</option>" for p in properties)
    type_opts = "<option value=''>All types</option>" + "".join(f"<option value='{esc(t)}'>{esc(t)}</option>" for t in types)
    action_opts = "<option value=''>All actions</option>" + "".join(f"<option value='{esc(a)}'>{esc(a)}</option>" for a in actions)
    risk_opts = "<option value=''>All risks</option>" + "".join(f"<option value='{esc(r)}'>{esc(r)}</option>" for r in risks)

    table_html = (
        f"<div class='card freshness-wrap'>"
        f"<div class='table-tools no-print freshness-tools'>"
        f"<input class='freshness-search' type='search' placeholder='Search pages…'>"
        f"<select class='freshness-property'>{prop_opts}</select>"
        f"<select class='freshness-type'>{type_opts}</select>"
        f"<select class='freshness-action'>{action_opts}</select>"
        f"<select class='freshness-risk'>{risk_opts}</select>"
        f"<span class='freshness-count sub'>{total} pages</span></div>"
        f"<table class='freshness-table'><thead><tr>"
        f"<th class='sortable' data-sort='display'>Page <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='property'>Property <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='type'>Type <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='age'>Age <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='word_count'>Words <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='freshness'>Fresh <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='depth'>Depth <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='risk'>Risk <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='keyword'>Keyword <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='position'>Pos <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='volume'>Vol <span class='arrow'></span></th>"
        f"<th class='sortable' data-sort='action'>Action <span class='arrow'></span></th>"
        f"<th>Reason</th>"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>")

    return f"<h2>Content Freshness</h2>{kpi_html}{candidates_html}{table_html}"


# ---------------------------------------------------------------- page assembly
def build_panels(con):
    """[(panel_id, label, html, [(sub_id, sub_label), ...], group), ...] — only
    modules that actually have data. Panels sharing a group name are bundled
    under one sidebar heading, each as its own page."""
    panels = []
    ex = exec_summary(con)
    if ex:
        panels.append(("exec", "Executive Summary", ex, [], None))
    for prop in PROPERTIES:                     # one page per project
        page = rank_property_page(con, prop)
        if page:
            panels.append((f"rank-{prop}", PROPERTIES[prop]["label"],
                           page, [], "Rank Tracker"))
    comp_pages = competitor_tracker_pages(con)
    if comp_pages:
        for pid, label, body in comp_pages:
            panels.append((pid, label, body, [], "Competitor Tracker"))
    bl = backlinks_section(con)
    if bl:
        panels.append(("backlinks", "Backlinks", bl, [], None))
    fr = freshness_section(con)
    if fr:
        panels.append(("freshness", "Content Freshness", fr, [], None))
    rs = research_section(con)
    if rs:
        panels.append(("research", "Keyword Research", rs, [], None))
    llm_subs = [(sid, label, section)
                for sid, label, section in [
                    ("llm-sov", "Share of voice", sov_trend_section(con)),
                    ("llm-vol", "AI search volume", volume_section(con)),
                    ("llm-disc", "Discovered prompts", discovered_section(con)),
                    ("llm-silent", "Silent citations", silent_section(con)),
                    ("llm-latest", "Latest run", latest_llm_section(con))]
                if section]
    if llm_subs:
        body = "".join(f"<div id='{sid}'>{section}</div>"
                       for sid, _, section in llm_subs)
        panels.append(("llm", "LLM Visibility", body,
                       [(sid, label) for sid, label, _ in llm_subs], None))
    return panels


def sidebar_html(panels, generated):
    nav, last_group, first = [], None, True
    for pid, label, _, subs, group in panels:
        if group != last_group:
            if group:
                nav.append(f"<div class='nav-group'>{esc(group)}</div>")
            last_group = group
        cls = "nav-item" + (" sub" if group else "") + (" active" if first else "")
        nav.append(f"<a class='{cls}' data-panel='{pid}'>{esc(label)}</a>")
        first = False
        for sid, slabel in subs:
            nav.append(f"<a class='nav-item sub' data-panel='{pid}' "
                       f"data-target='{sid}'>{esc(slabel)}</a>")
    return (f"<nav class='sidebar'>"
            f"<div class='side-brand'>Vantage Circle<span>SEO Suite</span></div>"
            f"{''.join(nav)}"
            f"<div class='side-foot'>{len(panels)} modules<br>"
            f"generated {esc(generated)}</div></nav>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    panels = build_panels(con)
    generated = f"{datetime.now():%Y-%m-%d %H:%M}"

    if panels:
        panels_html = "".join(
            f"<section class='panel{' active' if i == 0 else ''}' "
            f"id='panel-{pid}'>{body}</section>"
            for i, (pid, _, body, _, _) in enumerate(panels))
    else:
        panels_html = ("<div class='card'>No data yet — run the collectors "
                       "(rank_track.py, backlinks.py, llm_visibility.py) first.</div>")

    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Vantage Circle SEO Suite</title>"
            f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
            f"<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
            f"<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap' rel='stylesheet'>"
            f"<style>{DASHBOARD_CSS}</style>"
            f"<script>document.documentElement.className += ' has-js';</script>"
            f"</head><body>"
            f"{sidebar_html(panels, generated)}"
            f"<div class='content'><div class='wrap'>"
            f"<div class='hero'>"
            f"<div class='eyebrow'>rank tracking · backlinks · AI search analytics</div>"
            f"<h1>Vantage Circle SEO Suite</h1>"
            f"<div class='sub'>domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {generated}</div></div>"
            f"{panels_html}"
            f"</div></div>"
            f"<script>{SCRIPT}</script>"
            f"</body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
