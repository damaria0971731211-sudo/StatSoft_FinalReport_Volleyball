/* 分頁切換、圖表與球員查詢 */
(function () {
  'use strict';

  /* ---------- 分頁 ---------- */
  var panels = Array.prototype.slice.call(document.querySelectorAll('.panel'));
  var tabLinks = Array.prototype.slice.call(document.querySelectorAll('.tabs a'));
  var ids = panels.map(function (p) { return p.id.replace(/^p-/, ''); });

  function show(id, scroll) {
    if (ids.indexOf(id) < 0) id = 'overview';
    panels.forEach(function (p) { p.classList.toggle('active', p.id === 'p-' + id); });
    tabLinks.forEach(function (a) {
      if (a.getAttribute('href') === '#' + id) {
        a.setAttribute('aria-current', 'page');
        var ul = a.closest('ul'), li = a.parentNode;
        if (ul && (li.offsetLeft < ul.scrollLeft || li.offsetLeft + li.offsetWidth > ul.scrollLeft + ul.clientWidth)) ul.scrollLeft = li.offsetLeft - 16;
      } else a.removeAttribute('aria-current');
    });
    if (scroll) window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', function () { show(location.hash.slice(1), true); });
  show(location.hash.slice(1) || 'overview', true);
  window.addEventListener('load', function () { window.scrollTo(0, 0); });

  /* ---------- 工具 ---------- */
  var NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function txt(parent, x, y, s, attrs) {
    var t = el('text', Object.assign({ x: x, y: y }, attrs || {}), parent);
    t.textContent = s;
    return t;
  }
  var tip = document.getElementById('tooltip');
  function bindTip(node, html) {
    function move(ev) {
      var x = ev.clientX, y = ev.clientY;
      tip.innerHTML = html;
      tip.classList.add('show');
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var left = Math.min(x + 14, window.innerWidth - w - 8);
      var top = y - h - 12 < 8 ? y + 16 : y - h - 12;
      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }
    node.addEventListener('mousemove', move);
    node.addEventListener('mouseenter', move);
    node.addEventListener('mouseleave', function () { tip.classList.remove('show'); });
  }
  function pct(v, d) { return (v * 100).toFixed(d == null ? 1 : d) + '%'; }
  function niceTicks(lo, hi, n) {
    var step = Math.pow(10, Math.floor(Math.log10((hi - lo) / n)));
    var err = (hi - lo) / n / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }

  /* 點＋區間圖（水平） */
  function dotWhisker(container, opts) {
    var rows = opts.rows, W = 360, rowH = 34, top = 40, bottom = 28, left = opts.left || 92, right = 16;
    var H = top + rows.length * rowH + bottom;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': opts.title });
    container.appendChild(svg);
    txt(svg, 0, 16, opts.title, { class: 't-strong', 'font-size': 14 });
    if (opts.subtitle) txt(svg, 0, 32, opts.subtitle, { 'font-size': 11 });
    var x0 = opts.min, x1 = opts.max;
    var sx = function (v) { return left + (v - x0) / (x1 - x0) * (W - left - right); };
    niceTicks(x0, x1, 4).forEach(function (t) {
      el('line', { x1: sx(t), x2: sx(t), y1: top - 4, y2: H - bottom, class: 'gridline' }, svg);
      txt(svg, sx(t), H - bottom + 16, opts.fmt(t), { 'text-anchor': 'middle', 'font-size': 11 });
    });
    rows.forEach(function (r, i) {
      var y = top + i * rowH + rowH / 2;
      txt(svg, left - 10, y + 4, r.label, { 'text-anchor': 'end' });
      el('line', { x1: sx(r.lo), x2: sx(r.hi), y1: y, y2: y, stroke: r.color, class: 'whisker' }, svg);
      el('circle', { cx: sx(r.mean), cy: y, r: 6, fill: r.color, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
      if (opts.direct) txt(svg, sx(r.hi) + 6, y + 4, opts.fmt(r.mean), { 'font-size': 11 });
      var hit = el('rect', { x: left, y: y - rowH / 2, width: W - left - right, height: rowH, class: 'hit' }, svg);
      bindTip(hit, '<div>' + r.label + '</div><b>' + opts.fmtTip(r.mean) + '</b><div class="small">95% 區間 ' + opts.fmtTip(r.lo) + '～' + opts.fmtTip(r.hi) + '</div>' + (r.extra || ''));
    });
  }

  /* ---------- 圖 1：三種分隊方法 ---------- */
  var M = [
    { key: '隨機', color: 'var(--series-1)' },
    { key: '自評程度蛇形', color: 'var(--series-2)' },
    { key: '評分最佳化', color: 'var(--series-3)' }
  ];
  var S = {
    close: { '隨機': [0.3355, 0.3236, 0.3471], '自評程度蛇形': [0.3813, 0.3690, 0.3940], '評分最佳化': [0.4108, 0.3990, 0.4230] },
    blow:  { '隨機': [0.1269, 0.1175, 0.1360], '自評程度蛇形': [0.0862, 0.0790, 0.0930], '評分最佳化': [0.0720, 0.0650, 0.0790] },
    margin:{ '隨機': [5.526, 5.433, 5.614], '自評程度蛇形': [5.047, 4.968, 5.124], '評分最佳化': [4.831, 4.755, 4.907] }
  };
  var cm = document.getElementById('chart-methods');
  if (cm) {
    [
      { k: 'close', title: '接近比賽比例', sub: '分差 ≤ 3，越高越好', min: 0.30, max: 0.45, fmt: function (v) { return pct(v, 0); }, fmtTip: function (v) { return pct(v); } },
      { k: 'blow', title: '懸殊比賽比例', sub: '分差 ≥ 10，越低越好', min: 0.05, max: 0.15, fmt: function (v) { return pct(v, 0); }, fmtTip: function (v) { return pct(v); } },
      { k: 'margin', title: '平均分差', sub: '每局兩隊得分差，越低越好', min: 4.5, max: 6, fmt: function (v) { return v.toFixed(1); }, fmtTip: function (v) { return v.toFixed(2) + ' 分'; } }
    ].forEach(function (c) {
      var d = document.createElement('div'); d.className = 'chart'; cm.appendChild(d);
      dotWhisker(d, {
        title: c.title, subtitle: c.sub, min: c.min, max: c.max, fmt: c.fmt, fmtTip: c.fmtTip, direct: true,
        rows: M.map(function (m) { var v = S[c.k][m.key]; return { label: m.key, mean: v[0], lo: v[1], hi: v[2], color: m.color }; })
      });
    });
  }

  /* ---------- 球員分析 ---------- */
  var D = window.SITE_DATA;
  if (!D) return;
  var players = D.players.slice().sort(function (a, b) { return b.theta - a.theta; });
  var rank = {}; players.forEach(function (p, i) { rank[p.id] = i + 1; });
  var byId = {}; players.forEach(function (p) { byId[p.id] = p; });
  var fmtN = function (n) { return n.toLocaleString('zh-TW'); };
  var setText = function (id, v) { var e = document.getElementById(id); if (e) e.textContent = v; };
  setText('n-pairs', fmtN(D.nPairs));
  setText('n-pairs5', fmtN(D.nPairsGe5));

  // 位置圖與表
  var pos = D.positions.filter(function (p) { return p.att > 0; });
  var cp = document.getElementById('chart-position');
  if (cp) {
    dotWhisker(cp, {
      title: '各位置攻擊得分率', subtitle: '點：得分率；線：95% 區間', min: 0.24, max: 0.36, left: 56, direct: true,
      fmt: function (v) { return pct(v, 0); }, fmtTip: function (v) { return pct(v); },
      rows: pos.map(function (p) { return { label: p.pos, mean: p.rate, lo: p.ci[0], hi: p.ci[1], color: 'var(--series-1)', extra: '<div class="small">' + fmtN(p.kill) + ' / ' + fmtN(p.att) + ' 次</div>' }; })
    });
  }
  var pt = document.querySelector('#position-table tbody');
  if (pt) D.positions.forEach(function (p) {
    var tr = document.createElement('tr');
    tr.innerHTML = '<td>' + p.pos + '</td><td class="num">' + p.n + '</td><td class="num">' + fmtN(p.att) + '</td><td class="num">' + (p.rate == null ? '—' : pct(p.rate)) + '</td><td class="num">' + (p.eff == null ? '—' : pct(p.eff)) + '</td>';
    pt.appendChild(tr);
  });
  var tp = document.querySelector('#toppairs-table tbody');
  if (tp) D.topPairs.forEach(function (p) {
    var tr = document.createElement('tr');
    tr.innerHTML = '<td>' + p.a + ' ＋ ' + p.b + '</td><td class="num">' + p.n + '</td>';
    tp.appendChild(tr);
  });

  // 森林圖（全部球員）
  var forest = document.getElementById('chart-forest');
  var forestMarks = {};
  if (forest) {
    var W = 360, H = 260, L = 34, R = 10, T = 10, B = 26;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': '80 位球員估計實力與 95% 區間' });
    forest.appendChild(svg);
    var lo = Math.min.apply(null, players.map(function (p) { return p.lo; }));
    var hi = Math.max.apply(null, players.map(function (p) { return p.hi; }));
    lo = Math.floor(lo * 2) / 2; hi = Math.ceil(hi * 2) / 2;
    var sy = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var sx = function (i) { return L + (i + 0.5) / players.length * (W - L - R); };
    niceTicks(lo, hi, 4).forEach(function (t) {
      el('line', { x1: L, x2: W - R, y1: sy(t), y2: sy(t), class: 'gridline' }, svg);
      txt(svg, L - 6, sy(t) + 4, t.toFixed(1), { 'text-anchor': 'end', 'font-size': 10 });
    });
    txt(svg, L, H - 8, '← 實力較高', { 'font-size': 10 });
    txt(svg, W - R, H - 8, '實力較低 →', { 'font-size': 10, 'text-anchor': 'end' });
    var bw = (W - L - R) / players.length;
    players.forEach(function (p, i) {
      var g = el('g', {}, svg);
      var line = el('line', { x1: sx(i), x2: sx(i), y1: sy(p.hi), y2: sy(p.lo), stroke: 'var(--muted-mark)', 'stroke-width': 1.5 }, g);
      var dot = el('circle', { cx: sx(i), cy: sy(p.theta), r: 2.6, fill: 'var(--series-1)' }, g);
      var hit = el('rect', { x: sx(i) - bw / 2, y: T, width: bw, height: H - T - B, class: 'hit' }, g);
      hit.style.cursor = 'pointer';
      hit.addEventListener('click', function () { select(p.id); });
      bindTip(hit, '<div>' + p.id + '（第 ' + (i + 1) + ' 名）</div><b>' + p.theta.toFixed(2) + '</b><div class="small">95% 區間 ' + p.lo.toFixed(2) + '～' + p.hi.toFixed(2) + '</div>');
      forestMarks[p.id] = { line: line, dot: dot, g: g };
    });
  }

  var sel = document.getElementById('player-select');
  function select(id) {
    var p = byId[id]; if (!p) return;
    if (sel.value !== id) sel.value = id;
    setText('player-sub', '自評程度 ' + p.level + ' · 位置 ' + p.pos);
    var rate = p.att ? pct(p.kill / p.att) : '—';
    var eff = p.att ? pct((p.kill - p.err - p.blk) / p.att) : '—';
    var stats = [
      ['實力排名', rank[p.id] + ' / ' + players.length],
      ['實力估計', p.theta.toFixed(2)],
      ['95% 區間', p.lo.toFixed(2) + '～' + p.hi.toFixed(2)],
      ['上場局數', p.games + ' 局'],
      ['勝率', p.games ? pct(p.wins / p.games, 0) : '—'],
      ['攻擊得分率', rate],
      ['攻擊效率', eff]
    ];
    document.getElementById('player-stats').innerHTML = stats.map(function (s) {
      return '<div class="stat"><div class="k">' + s[0] + '</div><div class="v">' + s[1] + '</div></div>';
    }).join('');
    var tb = document.querySelector('#partner-table tbody');
    tb.innerHTML = p.partners.map(function (q) {
      var g = q.g == null ? '—' : (q.g >= 0 ? '+' : '') + q.g.toFixed(2) + '（' + q.lo.toFixed(2) + '～' + q.hi.toFixed(2) + '）';
      return '<tr><td><a href="#players" data-pid="' + q.id + '">' + q.id + '</a></td><td class="num">' + q.n + '</td><td>' + g + '</td></tr>';
    }).join('');
    Array.prototype.forEach.call(tb.querySelectorAll('a[data-pid]'), function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); select(a.getAttribute('data-pid')); });
    });
    for (var k in forestMarks) {
      var m = forestMarks[k], on = k === id;
      m.line.setAttribute('stroke', on ? 'var(--accent)' : 'var(--muted-mark)');
      m.line.setAttribute('stroke-width', on ? 3 : 1.5);
      m.dot.setAttribute('fill', on ? 'var(--accent)' : 'var(--series-1)');
      m.dot.setAttribute('r', on ? 4.5 : 2.6);
      if (on) m.g.parentNode.appendChild(m.g);
    }
  }
  if (sel) {
    D.players.slice().sort(function (a, b) { return a.id < b.id ? -1 : 1; }).forEach(function (p) {
      var o = document.createElement('option'); o.value = p.id; o.textContent = p.id + '（程度 ' + p.level + '，' + p.pos + '）'; sel.appendChild(o);
    });
    sel.addEventListener('change', function () { select(sel.value); });
    select(players[0].id);
  }
})();
