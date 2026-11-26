/* 跨球館平台示範頁（純前端，資料在 platform-data.js，全部是模擬資料） */
(function () {
  "use strict";
  const D = window.PLATFORM_DATA;
  const M = D.meta, CUTS = M.cuts;
  const VENUE = Object.fromEntries(D.venues.map(v => [v.id, v]));
  const PLAYER = Object.fromEntries(D.players.map(p => [p.id, p]));
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const f2 = x => (x >= 0 ? "" : "−") + Math.abs(x).toFixed(2);
  const pct = x => Math.round(x * 100) + "%";

  const SHOWCASE = [
    { id: "U0051", title: "自報 5 級，跨 3 館", sub: "比賽紀錄只有約 3 級", venue: "V03" },
    { id: "U0025", title: "自報 3 級，其實更強", sub: "報新手友善館會被擋", venue: "V04" },
    { id: "U0006", title: "才打 7 局的新面孔", sub: "還說不準，給試打", venue: "V03" },
    { id: "U0134", title: "跨 3 館的高手", sub: "進階場直接放行", venue: "V03" },
  ];

  // ---------- 統計小工具 ----------
  function erf(x) { // Abramowitz-Stegun 7.1.26
    const t = 1 / (1 + 0.3275911 * Math.abs(x));
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return x >= 0 ? y : -y;
  }
  const Phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
  const plogis = x => 1 / (1 + Math.exp(-x));
  function levelProbs(theta, se) {
    const edges = [-Infinity, ...CUTS, Infinity];
    const out = [];
    for (let j = 0; j < 5; j++) out.push(Phi((edges[j + 1] - theta) / se) - Phi((edges[j] - theta) / se));
    return out;
  }
  const levelOf = th => 1 + CUTS.filter(c => th >= c).length;
  function raceWin(p, T) { // 每球得分機率 p，先拿 T 分的機率（不計 deuce）
    let s = 0, lp = T * Math.log(p), lq = Math.log(1 - p), lc = 0;
    for (let j = 0; j < T; j++) {
      if (j > 0) lc += Math.log(T - 1 + j) - Math.log(j);
      s += Math.exp(lc + lp + j * lq);
    }
    return s;
  }
  function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  // ---------- 狀態 ----------
  const state = { pid: "U0051", newbie: null, venue: "V03", night: 0, truth: false };
  const cur = () => state.newbie || PLAYER[state.pid];

  function makeNewbie(level, home) {
    const v = VENUE[home];
    // 與批次估計同一個中心：全體平均實力 = 0
    const meanPrior = D.players.reduce((a, p) => a + p.prior, 0) / D.players.length;
    const theta = v.alpha + M.beta * (level - 3) - meanPrior;
    return { id: "NEW", isNew: true, gender: "—", years: 0, pos: "不限", self: level, home, theta: +theta.toFixed(3),
      se: +Math.sqrt(M.sigma ** 2 + v.alpha_se ** 2).toFixed(3), sets: 0, nv: 0, prior: theta, venues: [], recent: [],
      atk: { att: 0, kill: 0, err: 0, ace: 0, dig: 0 }, trace: [], truth: null };
  }

  // ---------- 判斷報名 ----------
  function gate(p, v) {
    if (v.level_min == null && v.level_max == null) return { kind: "free" };
    let P, cut, text, selfOk;
    if (v.level_min != null) {
      cut = CUTS[v.level_min - 2]; P = 1 - Phi((cut - p.theta) / p.se);
      text = `限 ${v.level_min} 級以上`; selfOk = p.self >= v.level_min;
    } else {
      cut = CUTS[v.level_max - 1]; P = Phi((cut - p.theta) / p.se);
      text = `限 ${v.level_max} 級以下`; selfOk = p.self <= v.level_max;
    }
    const kind = P >= M.rule.pass ? "pass" : P <= M.rule.block ? "block" : "trial";
    return { kind, P, cut, text, selfOk, upper: v.level_max != null };
  }
  const KIND_ZH = { pass: "放行", trial: "試打名額", block: "擋下", free: "不設門檻" };

  // ---------- 選球員 ----------
  function initChooser() {
    const sel = $("#player-select");
    const ids = D.players.map(p => p.id);
    sel.innerHTML = `<option value="" disabled>新球員（自建檔案）</option>` + ids.map(id => {
      const p = PLAYER[id];
      return `<option value="${id}">${id}｜自報 ${p.self} 級｜${p.sets} 局｜${p.nv} 館</option>`;
    }).join("");
    sel.value = state.pid;
    sel.onchange = () => { state.pid = sel.value; state.newbie = null; renderAll(); };
    $("#chips").innerHTML = SHOWCASE.map(s => `<button type="button" class="chip" data-id="${s.id}" data-venue="${s.venue}" aria-pressed="false">${esc(s.title)}<small>${s.id} · ${esc(s.sub)}</small></button>`).join("");
    $("#chips").onclick = e => {
      const b = e.target.closest(".chip"); if (!b) return;
      state.pid = b.dataset.id; state.venue = b.dataset.venue; state.newbie = null; sel.value = state.pid; renderAll();
    };
    $("#nb-home").innerHTML = D.venues.map(v => `<option value="${v.id}">${esc(v.name)}</option>`).join("");
    $("#nb-go").onclick = () => { state.newbie = makeNewbie(+$("#nb-level").value, $("#nb-home").value); renderAll(); };
    $("#truth-toggle").onchange = e => { state.truth = e.target.checked; renderAll(); };
  }

  // ---------- ① 個人檔案 ----------
  function renderProfile() {
    const p = cur();
    document.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", String(!p.isNew && c.dataset.id === p.id)));
    const home = VENUE[p.home];
    $("#profile-sub").textContent = p.isNew
      ? `新建立的檔案：還沒有任何比賽紀錄，主場 ${home.name}。`
      : `${p.id}｜${p.gender}｜球齡 ${p.years} 年｜${p.pos}｜主場 ${home.name}`;

    const probs = levelProbs(p.theta, p.se);
    const est = probs.indexOf(Math.max(...probs)) + 1;
    const conf = Math.max(...probs);
    const confLv = conf >= 0.7 ? ["hi", "高"] : conf >= 0.45 ? ["mid", "中"] : ["lo", "低"];
    const d = p.self - est;
    const gapBadge = d > 0 ? `<span class="badge up">自報高 ${d} 級</span>` : d < 0 ? `<span class="badge down">自報低 ${-d} 級</span>` : `<span class="badge same">一致</span>`;
    const lo = p.theta - 1.96 * p.se, hi = p.theta + 1.96 * p.se;
    $("#kpis").innerHTML = `
      <div class="card kpi"><div class="label">自報程度</div><div class="value">${p.self}<span class="unit">級</span></div><div class="sub">建立檔案時自己填的</div></div>
      <div class="card kpi"><div class="label">平台估計程度</div><div class="value">${est}<span class="unit">級</span> ${gapBadge}</div><div class="sub">95% 區間約 ${levelOf(lo)}~${levelOf(hi)} 級（實力 ${f2(lo)} ~ ${f2(hi)}）</div></div>
      <div class="card kpi"><div class="label">可信度</div><div class="value sm"><span class="badge ${confLv[0]}" style="font-size:18px;vertical-align:4px">${confLv[1]}</span></div><div class="sub">最可能等級的機率 ${pct(conf)}</div></div>
      <div class="card kpi"><div class="label">累積紀錄</div><div class="value">${p.sets}<span class="unit">局</span></div><div class="sub">${p.isNew ? "尚未出賽" : `去過 ${p.nv} 間球館`}</div></div>`;

    $("#level-bars").innerHTML = probs.map((q, j) => `
      <div class="lb${j + 1 === p.self ? " self" : ""}${j + 1 === est ? " top" : ""}">
        <span class="name">${j + 1} 級</span><span class="track"><span class="fill" style="width:${(q * 100).toFixed(1)}%"></span></span><span class="pct">${pct(q)}</span>
      </div>`).join("");
    let gap;
    if (p.isNew) gap = `還沒打過球，估計完全來自自報與主場球館的平均，所以區間很寬。打幾局之後就會往比賽紀錄靠。`;
    else if (d > 0) gap = `比賽紀錄顯示你比自報低 ${d} 級：只看自報，你會被排進程度太高的場次。`;
    else if (d < 0) gap = `比賽紀錄顯示你比自報高 ${-d} 級：只看自報，你會被排進新手場，對其他人不公平。`;
    else gap = `自報和比賽紀錄一致。`;
    if (state.truth && p.truth != null) gap += `<span class="truth-line" style="display:block">模擬真值：實力 ${f2(p.truth)}，相當於 ${levelOf(p.truth)} 級。${p.truth >= lo && p.truth <= hi ? "落在 95% 區間內。" : "落在 95% 區間外。"}</span>`;
    $("#gap-text").innerHTML = gap;

    renderTrace(p);

    // 各館紀錄
    if (p.isNew) {
      $("#venue-table").innerHTML = `<tr><td class="muted">還沒有出賽紀錄。</td></tr>`;
      $("#bridge-note").textContent = "";
    } else {
      $("#venue-table").innerHTML = `<thead><tr><th>球館</th><th class="num">晚數</th><th class="num">局數</th><th class="num">勝率</th><th class="num">得失分</th></tr></thead><tbody>` +
        p.venues.map(r => `<tr><td>${esc(VENUE[r.v].name)}${r.v === p.home ? '<span class="tag-home">主場</span>' : ""}</td><td class="num">${r.nights}</td><td class="num">${r.sets}</td><td class="num">${pct(r.wins / r.sets)}</td><td class="num">${r.pf}:${r.pa}</td></tr>`).join("") + "</tbody>";
      $("#bridge-note").textContent = p.nv >= 2
        ? `你是「橋接球員」：在 ${p.nv} 間館都打過，讓模型能把不同球館的分級放在同一把尺上（150 人裡只有 17 位）。`
        : "只在一間球館打過。跨館比較靠其他去過多館的球員串起來。";
    }
    if (p.isNew || !p.recent.length) { $("#recent-table").innerHTML = `<tr><td class="muted">—</td></tr>`; $("#atk-note").textContent = ""; }
    else {
      $("#recent-table").innerHTML = `<thead><tr><th>日期</th><th>球館</th><th class="num">比分</th><th>結果</th></tr></thead><tbody>` +
        p.recent.map(r => `<tr><td>${r.d.slice(5).replace("-", "/")} ${r.s}</td><td>${esc(VENUE[r.v].name.replace(/（.*）/, ""))}</td><td class="num">${r.pf}:${r.pa}</td><td class="${r.w ? "w" : "l"}">${r.w ? "勝" : "敗"}</td></tr>`).join("") + "</tbody>";
      const a = p.atk;
      $("#atk-note").textContent = a.att ? `攻擊 ${a.att} 次、得分 ${a.kill}、失誤 ${a.err}（攻擊效率 ${((a.kill - a.err) / a.att).toFixed(2)}）；發球得分 ${a.ace}、防守 ${a.dig}。攻擊數據只做描述，不進評分模型。` : "";
    }
  }

  function renderTrace(p) {
    const el = $("#trace-chart");
    const pts = [[0, p.prior - (p.isNew ? 0 : M.shift), M.sigma], ...p.trace];
    if (p.isNew) pts.length = 1;
    const W = 520, H = 260, L = 44, R = 14, T = 12, B = 34;
    const xmax = Math.max(10, pts[pts.length - 1][0]);
    const ys = pts.flatMap(q => [q[1] - 1.96 * q[2], q[1] + 1.96 * q[2]]).concat(CUTS);
    const ymin = Math.min(...ys) - 0.05, ymax = Math.max(...ys) + 0.05;
    const X = x => L + (x / xmax) * (W - L - R), Y = y => T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B);
    const band = pts.map(q => `${X(q[0]).toFixed(1)},${Y(q[1] + 1.96 * q[2]).toFixed(1)}`).concat(pts.slice().reverse().map(q => `${X(q[0]).toFixed(1)},${Y(q[1] - 1.96 * q[2]).toFixed(1)}`)).join(" ");
    const line = pts.map(q => `${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`).join(" ");
    const xt = []; const step = xmax > 100 ? 40 : xmax > 40 ? 20 : xmax > 15 ? 10 : 5;
    for (let x = 0; x <= xmax; x += step) xt.push(x);
    const last = pts[pts.length - 1];
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="估計實力隨局數變化">`;
    CUTS.forEach((c, i) => {
      if (c > ymin && c < ymax) svg += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${Y(c)}" y2="${Y(c)}" stroke-dasharray="4 4"/><text x="${W - R}" y="${Y(c) - 4}" text-anchor="end">${i + 1}|${i + 2} 級</text>`;
    });
    svg += `<line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
    xt.forEach(x => svg += `<text x="${X(x)}" y="${H - B + 16}" text-anchor="middle">${x}</text>`);
    svg += `<text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">已打局數</text>`;
    svg += `<text x="12" y="${(T + H - B) / 2}" transform="rotate(-90 12 ${(T + H - B) / 2})" text-anchor="middle">估計實力</text>`;
    svg += `<polygon points="${band}" fill="var(--series-1)" opacity=".16"/>`;
    if (pts.length > 1) svg += `<polyline points="${line}" fill="none" stroke="var(--series-1)" stroke-width="2.2" stroke-linejoin="round"/>`;
    svg += `<circle cx="${X(0)}" cy="${Y(pts[0][1])}" r="4.5" fill="var(--surface)" stroke="var(--accent)" stroke-width="2"><title>只有自報時的起點</title></circle>`;
    svg += `<text x="${X(0) + 8}" y="${Y(pts[0][1]) - 8}" class="t-strong">自報起點</text>`;
    if (pts.length > 1) svg += `<circle cx="${X(last[0])}" cy="${Y(last[1])}" r="4.5" fill="var(--series-1)"><title>目前：${f2(last[1])} ± ${(1.96 * last[2]).toFixed(2)}</title></circle>`;
    if (state.truth && p.truth != null) svg += `<line x1="${L}" x2="${W - R}" y1="${Y(p.truth)}" y2="${Y(p.truth)}" stroke="var(--todo-text)" stroke-width="1.5"/><text x="${L + 4}" y="${Y(p.truth) - 4}" fill="var(--todo-text)" style="fill:var(--todo-text)">模擬真值</text>`;
    svg += `</svg>`;
    el.innerHTML = svg;
  }

  // ---------- ② 報名 ----------
  function renderSignup() {
    const p = cur();
    $("#venue-cards").innerHTML = D.venues.map(v => {
      const g = gate(p, v);
      const lim = v.level_min != null ? `限 ${v.level_min} 級以上` : v.level_max != null ? `限 ${v.level_max} 級以下` : "不設程度門檻";
      return `<button type="button" class="venue" role="radio" aria-checked="${v.id === state.venue}" data-v="${v.id}">
        <h4>${esc(v.name)}</h4>
        <div class="vmeta">${v.region}｜${v.days}<br>${v.sessions.map(s => `${s.name} ${s.start}`).join("、")}｜打 ${v.target.join(" 或 ")} 分</div>
        <div class="vfoot"><span class="vlimit${v.level_min != null || v.level_max != null ? " on" : ""}">${lim}</span><span class="pill ${g.kind === "free" ? "free" : g.kind}">${KIND_ZH[g.kind]}</span></div>
      </button>`;
    }).join("");
    $("#venue-cards").onclick = e => { const b = e.target.closest(".venue"); if (!b) return; state.venue = b.dataset.v; renderSignup(); renderSplit(); };

    const v = VENUE[state.venue], g = gate(p, v), box = $("#decision");
    box.className = "card decision " + g.kind;
    const who = "你";
    if (g.kind === "free") {
      box.innerHTML = `<div class="verdict"><div class="big">報名成功</div><div class="muted">${esc(v.name)}不設程度門檻，所有人都能報。平台仍會記錄這晚的比賽，累積到${who}的檔案裡。</div></div>
        <p class="muted small" style="margin-bottom:0">試試看右邊有門檻的兩間：進階場（限 4 級以上）和新手友善館（限 3 級以下）。</p>`;
      return;
    }
    const lo = p.theta - 1.96 * p.se, hi = p.theta + 1.96 * p.se;
    const headline = { pass: "放行", trial: "給試打名額", block: "擋下" }[g.kind];
    const what = g.upper ? `實力低於 ${v.level_max}|${v.level_max + 1} 級切點` : `實力達到 ${v.level_min - 1}|${v.level_min} 級切點`;
    let why;
    if (g.kind === "pass") why = g.upper ? "比賽紀錄很確定你沒有超過這個館的程度上限。" : "比賽紀錄很確定你達到門檻，誤放的風險低。";
    else if (g.kind === "block") why = g.upper ? "比賽紀錄很確定你的程度高於新手場上限。讓你進來，其他新手的體驗會變差。" : "比賽紀錄很確定你還沒達到門檻。放行的話，同場其他人的體驗會變差（型一錯誤）。";
    else why = "資料還不夠判斷。給一個試打名額（例如每隊最多一位），這晚打的局數會回到檔案裡，下次判斷更準。";
    // 還要打幾局才可能判定（假設估計值不變）
    let more = "";
    if (g.kind === "trial") {
      const zNeed = 0.8416; // Φ(0.8416) = 0.8
      const dist = Math.abs(p.theta - g.cut);
      if (dist < 0.02) more = "你的估計值幾乎就在切點上，要打非常多局才分得出來。";
      else {
        const need = Math.ceil(((zNeed / dist) ** 2 - 1 / p.se ** 2) / M.prec_per_set);
        more = need > 0 ? `若估計值維持不變，大約再打 ${need} 局，P 就會${p.theta > g.cut === !g.upper ? "超過 0.8" : "低於 0.2"}。` : "";
      }
    }
    const selfRes = g.selfOk ? "放行" : "擋下";
    const selfAgree = (g.selfOk && g.kind === "pass") || (!g.selfOk && g.kind === "block");
    box.innerHTML = `
      <div class="verdict">
        <div class="big ${g.kind}">${headline}</div>
        <div class="pnum">${esc(v.name)}｜${g.text}<br>P（${what}）＝ <b>${g.P.toFixed(2)}</b></div>
      </div>
      <div class="pscale" aria-hidden="true"><div class="bar"><span></span><span></span><span></span></div><div class="mk" style="left:${(g.P * 100).toFixed(1)}%"></div>
        <div class="ticks"><span style="left:0%">0</span><span style="left:20%">0.2</span><span style="left:80%">0.8</span><span style="left:100%">1</span></div></div>
      <p style="margin:14px 0 0">${why} ${more}</p>
      <div class="compare-self">
        <div><h5>平台怎麼算</h5>你的估計實力 ${f2(p.theta)}（95% 區間 ${f2(lo)} ~ ${f2(hi)}，${p.sets} 局），門檻切點 ${f2(g.cut)}。在常態後驗下，${what}的機率是 ${pct(g.P)}。</div>
        <div><h5>如果只看自報</h5>自報 ${p.self} 級 → <b>${selfRes}</b>。${selfAgree ? "和平台的判斷一樣。" : g.kind === "trial" ? "平台認為還說不準，改給試打名額。" : "<b>和平台的判斷不同</b>：這就是自報失準造成的誤放或誤擋。"}</div>
      </div>
      ${state.truth && p.truth != null ? `<div class="truth-line">模擬真值 ${f2(p.truth)}：${(g.upper ? p.truth < g.cut : p.truth >= g.cut) ? "真的符合門檻" : "其實不符合門檻"}。${verdictCheck(g, p)}</div>` : ""}`;
  }
  function verdictCheck(g, p) {
    const ok = g.upper ? p.truth < g.cut : p.truth >= g.cut;
    if (g.kind === "pass") return ok ? "放行正確。" : "這是一次誤放（型一錯誤）。";
    if (g.kind === "block") return ok ? "這是一次誤擋（型二錯誤）。" : "擋下正確。";
    return "試打名額讓資料來決定。";
  }

  // ---------- ③ 分隊 ----------
  const SETTER_W = 0.1;
  function chooseN(n) { let k = Math.max(2, Math.ceil(n / 6)); return Math.min(k, 6, Math.floor(n / 4)); }
  function sizes(n, k) { const b = Math.floor(n / k), e = n % k; return Array.from({ length: k }, (_, i) => b + (i < e ? 1 : 0)); }
  function deal(order, sz) {
    const teams = sz.map(() => []); const n = sz.length; let idx = 0, fwd = true;
    for (const p of order) {
      for (;;) { const t = fwd ? idx : n - 1 - idx; idx++; if (idx === n) { idx = 0; fwd = !fwd; } if (teams[t].length < sz[t]) { teams[t].push(p); break; } }
    }
    return teams;
  }
  const strength = (t, key) => t.reduce((s, p) => s + key(p), 0) / t.length + M.delta * t.length;
  function score(teams, key) {
    const s = teams.map(t => strength(t, key));
    const mean = s.reduce((a, b) => a + b, 0) / s.length;
    const varr = s.reduce((a, b) => a + (b - mean) ** 2, 0) / s.length;
    const c = teams.map(t => t.filter(p => p.pos === "舉球").length);
    const want = Math.min(c.reduce((a, b) => a + b, 0), teams.length);
    return Math.max(...s) - Math.min(...s) + 0.1 * varr + SETTER_W * (want - c.filter(x => x > 0).length);
  }
  function shuffled(arr, r) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
  function snakeSplit(ps, k, r) { const o = shuffled(ps, r); o.sort((a, b) => b.self - a.self); return deal(o, sizes(ps.length, k)); }
  function balancedSplit(ps, k, r) {
    const key = p => p.theta;
    const o = shuffled(ps, r); o.sort((a, b) => b.theta - a.theta);
    const teams = deal(o, sizes(ps.length, k));
    let best = score(teams, key);
    for (let round = 0; round < 200; round++) {
      let sw = null;
      for (let a = 0; a < k; a++) for (let b = a + 1; b < k; b++) for (let i = 0; i < teams[a].length; i++) for (let j = 0; j < teams[b].length; j++) {
        [teams[a][i], teams[b][j]] = [teams[b][j], teams[a][i]];
        const v = score(teams, key);
        if (v < best - 1e-12) { best = v; sw = [a, i, b, j]; }
        [teams[a][i], teams[b][j]] = [teams[b][j], teams[a][i]];
      }
      if (!sw) break;
      const [a, i, b, j] = sw; [teams[a][i], teams[b][j]] = [teams[b][j], teams[a][i]];
    }
    return teams;
  }

  function initNights() {
    $("#night-select").innerHTML = D.nights.map((n, i) => `<option value="${i}">${esc(VENUE[n.venue].name)}｜${n.date.slice(5).replace("-", "/")} ${n.session}｜${n.players.length} 人</option>`).join("");
    $("#night-select").onchange = e => { state.night = +e.target.value; renderSplit(); };
    $("#add-me").onchange = renderSplit;
  }
  function renderSplit() {
    const n = D.nights[state.night], v = VENUE[n.venue], p = cur();
    let roster = n.players.map(id => PLAYER[id]);
    const g = gate(p, v);
    let note = "";
    if ($("#add-me").checked) {
      if (roster.some(x => x.id === p.id)) note = `${p.id} 本來就在這晚的名單裡。`;
      else if (g.kind === "block") note = `${p.isNew ? "這位新球員" : p.id}在${v.name}的報名被擋下，所以沒有加進名單。`;
      else { roster = roster.concat([p]); note = `已把${p.isNew ? "新球員" : p.id}加進名單（${KIND_ZH[g.kind]}）。`; }
    }
    const k = chooseN(roster.length), T = v.target_by[k] || v.target[0];
    $("#night-info").textContent = `${roster.length} 人，分 ${k} 隊，每局打 ${T} 分。${note}`;
    const r1 = rng(20261126 + state.night), r2 = rng(20261126 + state.night);
    const methods = [
      { name: "只看自報：蛇形分配", sub: "現況做法。依自報等級高到低輪流發給各隊。", teams: snakeSplit(roster, k, r1) },
      { name: "平台評分最佳化", sub: "用跨館估計實力分隊，讓最強與最弱隊差距最小。", teams: balancedSplit(roster, k, r2), best: true },
    ];
    const truthKey = x => (x.truth == null ? x.theta : x.truth);
    $("#split-compare").innerHTML = methods.map(m => {
      const s = m.teams.map(t => strength(t, x => x.theta));
      const imax = s.indexOf(Math.max(...s)), imin = s.indexOf(Math.min(...s));
      const gap = s[imax] - s[imin];
      const win = raceWin(plogis(gap), T);
      let truthHtml = "";
      if (state.truth) {
        const st = m.teams.map(t => strength(t, truthKey));
        const gt = Math.max(...st) - Math.min(...st);
        truthHtml = `<div class="stat"><div class="k">以模擬真值算：強弱勝率</div><div class="v">${pct(raceWin(plogis(gt), T))}</div></div>`;
      }
      const smin = -0.4, smax = 0.4, pos = x => Math.max(0, Math.min(100, (x - smin) / (smax - smin) * 100));
      return `<div class="card split-card${m.best ? " best" : ""}">
        <h3>${m.name}${m.best ? ' <span class="badge same">平台使用</span>' : ""}</h3>
        <p class="muted small" style="margin:0">${m.sub}</p>
        <div class="split-sum">
          <div class="stat"><div class="k">最強隊對最弱隊勝率</div><div class="v">${pct(win)}</div></div>
          <div class="stat"><div class="k">隊伍強度差</div><div class="v">${gap.toFixed(2)}</div></div>
          ${truthHtml}
        </div>
        <p class="muted small" style="margin:0 0 6px">每人右邊是「自報→平台估計」等級；「舉」＝舉球員。</p>
        <div class="teams">${m.teams.map((t, i) => `<div class="team">
          <h4>第 ${i + 1} 隊 <span>${f2(s[i])}</span></h4>
          <div class="strength-bar" title="隊伍強度"><i style="left:${pos(s[i])}%"></i></div>
          <ul>${t.slice().sort((a, b) => b.theta - a.theta).map(x => `<li class="${x.id === p.id ? "me" : ""}"><span>${x.isNew ? "新球員" : x.id}${x.pos === "舉球" ? " 舉" : ""}</span><span class="lv">${x.self}→${levelOf(x.theta)}</span></li>`).join("")}</ul>
        </div>`).join("")}</div>
      </div>`;
    }).join("");
  }

  // ---------- 驗證小卡 ----------
  function renderValidity() {
    $("#validity").innerHTML = `<h4>這份模擬資料上，模型可信嗎？</h4>
      <div class="vgrid">
        <div class="stat"><div class="k">估計 vs 真值 Spearman</div><div class="v">${M.spearman_model.toFixed(2)}</div></div>
        <div class="stat"><div class="k">只看自報 vs 真值</div><div class="v">${M.spearman_self.toFixed(2)}</div></div>
        <div class="stat"><div class="k">95% 區間涵蓋率</div><div class="v">${pct(M.coverage)}</div></div>
        <div class="stat"><div class="k">線上更新 vs 批次估計相關</div><div class="v">${M.online_batch_cor.toFixed(2)}</div></div>
      </div>
      <p class="muted small" style="margin:10px 0 0">${M.n_players} 人、${M.n_games} 局。自報每升一級，實力先驗平均加 β = ${M.beta.toFixed(2)}；個人實力的先驗標準差 σ = ${M.sigma.toFixed(2)}，球館之間 σ<sub>v</sub> = ${M.sigma_v.toFixed(2)}。涵蓋率高於 95% 是因為區間保守（包含自報先驗的不確定性）。</p>`;
  }

  // ---------- 分區切換（#home / #report / #signup / #how） ----------
  const PANELS = ["home", "report", "signup", "how"];
  function route() {
    let h = location.hash.slice(1);
    if (h === "split") h = "signup";
    if (!PANELS.includes(h)) h = "home";
    PANELS.forEach(k => document.getElementById("p-" + k).classList.toggle("active", k === h));
    document.querySelectorAll(".tabs a").forEach(a => {
      if (a.getAttribute("href") === "#" + h) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (location.hash.slice(1) === "split") document.getElementById("split").scrollIntoView();
    else window.scrollTo(0, 0);
  }

  // ---------- 身分列與首頁入口摘要 ----------
  function renderPersona() {
    const p = cur(), probs = levelProbs(p.theta, p.se);
    const est = probs.indexOf(Math.max(...probs)) + 1, conf = Math.max(...probs);
    const confZh = conf >= 0.7 ? "高" : conf >= 0.45 ? "中" : "低";
    $("#avatar").textContent = p.isNew ? "新" : p.id.slice(-2);
    $("#persona-name").textContent = p.isNew ? "新球員（剛建立檔案）" : `目前身分：${p.id}`;
    $("#persona-sub").textContent = `主場 ${VENUE[p.home].name}｜自報 ${p.self} 級｜${p.sets} 局`;
    if ($("#player-select").value !== p.id) $("#player-select").value = p.isNew ? "" : p.id;
    const d = p.self - est;
    $("#entry-report").innerHTML = `<span class="badge same">平台估計 ${est} 級</span><span class="badge ${conf >= 0.7 ? "hi" : conf >= 0.45 ? "mid" : "lo"}">可信度${confZh}</span>` +
      (d ? `<span class="badge ${d > 0 ? "up" : "down"}">自報${d > 0 ? "高" : "低"} ${Math.abs(d)} 級</span>` : "");
    $("#entry-signup").innerHTML = D.venues.filter(v => v.level_min != null || v.level_max != null).map(v => {
      const g = gate(p, v); return `<span class="pill ${g.kind}">${v.name.replace(/虛構球館 . ?（(.*)）/, "$1")}：${KIND_ZH[g.kind]}</span>`;
    }).join("");
  }

  function renderAll() { renderPersona(); renderProfile(); renderSignup(); renderSplit(); }
  initChooser(); initNights(); renderValidity(); renderAll();
  addEventListener("hashchange", route); route();
})();
