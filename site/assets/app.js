/* 世界の中の日本 — グラフと切り替え（主役の国を選べる） */
(function () {
  "use strict";
  const body = document.body;
  const ROOT = body.dataset.root || "./";
  const LINKS = body.dataset.links || "pretty";
  const PAGE = body.dataset.page;
  const state = { group: "oecd", focus: "JPN", meta: null, latest: null, series: null, compare: null, colors: {} };
  const charts = {};

  // ---------------------------------------------------------------- 共通
  const css = (name) => getComputedStyle(body).getPropertyValue(name).trim();
  const href = (path) => ROOT + path + (LINKS === "index" && (path === "" || path.endsWith("/")) ? "index.html" : "");
  const countryHref = (iso) => (iso === "JPN" ? href("") : href("c/" + iso.toLowerCase() + "/"));
  // ページに埋め込まれたデータがあればそれを使い、なければファイルを読む
  const EMB = (() => { const el = document.getElementById("wij-data"); try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; } })();
  const getJSON = (p) => (p in EMB ? Promise.resolve(EMB[p]) : fetch(ROOT + p).then((r) => { if (!r.ok) throw new Error(p); return r.json(); }));
  const name = (iso) => (state.meta.names[iso] || iso);
  const nf = (v, d) => v.toLocaleString("ja-JP", { minimumFractionDigits: d, maximumFractionDigits: d });
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 保存できなくても動く */ } },
  };

  function fmt(m, v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const a = Math.abs(v);
    if (m.fmt === "money") {
      if (a >= 1e12) return nf(v / 1e12, 2) + "兆ドル";
      if (a >= 1e8) return nf(v / 1e8, 0) + "億ドル";
      return nf(v / 1e4, 0) + "万ドル";
    }
    if (m.fmt === "pop") {
      if (v >= 1e8) return nf(v / 1e8, 2) + "億人";
      if (v >= 1e4) return nf(v / 1e4, 0) + "万人";
      return nf(v, 0) + "人";
    }
    if (m.fmt === "count") {
      if (a >= 1e4) return nf(v / 1e4, 1) + "万" + m.u;
      return nf(v, 0) + m.u;
    }
    return nf(v, m.d) + m.u;
  }
  // 軸目盛り用の短い表記
  function fmtAxis(m, v) {
    const a = Math.abs(v);
    if (m.fmt === "money" || m.fmt === "pop" || m.fmt === "count") {
      if (a >= 1e12) return nf(v / 1e12, a >= 1e13 ? 0 : 1) + "兆";
      if (a >= 1e8) return nf(v / 1e8, a >= 1e9 ? 0 : 1) + "億";
      if (a >= 1e4) return nf(v / 1e4, 0) + "万";
      return nf(v, 0);
    }
    return nf(v, Math.abs(v) < 10 && m.d > 0 ? 1 : 0);
  }
  const narrow = () => window.innerWidth < 640;
  const orderLabel = (m) => (m.dir === -1 ? "低い順" : "高い順");

  // 比べる国のまとまり。「同じ地域」は主役の国によって中身が変わる
  function members(g) {
    if (g === "region") {
      const rk = state.meta.regionOf[state.focus];
      return Object.keys(state.meta.regionOf).filter((iso) => state.meta.regionOf[iso] === rk);
    }
    return state.meta.groups[g].members;
  }
  function groupName(g) {
    if (g === "region") return state.meta.regionNames[state.meta.regionOf[state.focus]] || "同じ地域";
    return state.meta.groups[g].name;
  }
  // 主役の国はまとまりに入っていなくても比べる対象に加える
  const inGroup = (g, iso) => { const mm = members(g); return !mm || mm.includes(iso) || iso === state.focus; };
  const defaultGroup = (iso) => (state.meta.groups.oecd.members.includes(iso) ? "oecd" : "region");

  function palette() {
    return {
      ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), grid: css("--grid"), surface: css("--surface"),
      jp: css("--jp"), bar: css("--bar"), ref: css("--s1"),
      series: [1, 2, 3, 4, 5, 6, 7].map((i) => css("--s" + i)),
    };
  }
  function baseOpt(c) {
    return {
      animation: false,
      textStyle: { fontFamily: css("--font"), color: c.ink2 },
      grid: { left: 8, right: 24, top: 36, bottom: 8, containLabel: true },
      tooltip: { backgroundColor: c.surface, borderColor: c.grid, textStyle: { color: c.ink } },
    };
  }
  function makeChart(id) {
    const el = document.getElementById(id);
    if (!el || !window.echarts) return null;
    if (charts[id]) charts[id].dispose();
    charts[id] = echarts.init(el, null, { renderer: "svg" });
    return charts[id];
  }
  window.addEventListener("resize", () => Object.values(charts).forEach((ch) => ch.resize()));

  function rankRows(m, slug, g) {
    const L = state.latest[slug] || {};
    const rows = Object.entries(L).filter(([iso]) => inGroup(g, iso)).map(([iso, [y, v]]) => ({ iso, y, v }));
    rows.sort((a, b) => (m.dir === -1 ? a.v - b.v : b.v - a.v));
    return rows;
  }

  function syncTabs() {
    document.querySelectorAll(".tabs .tab").forEach((x) => {
      x.classList.toggle("on", x.dataset.group === state.group);
      if (x.dataset.group === "region") x.textContent = groupName("region");
    });
  }
  function bindTabs(onChange) {
    document.querySelectorAll(".tabs .tab").forEach((b) => {
      b.addEventListener("click", () => { state.group = b.dataset.group; syncTabs(); onChange(); });
    });
    syncTabs();
  }

  // 国を選ぶ <select>。isos はそのページで選べる国
  function fillCountrySelect(sel, isos, current) {
    const sorted = isos.filter((iso) => iso !== "JPN").sort((a, b) => name(a).localeCompare(name(b), "ja"));
    if (isos.includes("JPN")) sorted.unshift("JPN");
    sel.innerHTML = sorted.map((iso) => `<option value="${iso}"${iso === current ? " selected" : ""}>${esc(name(iso))}</option>`).join("");
  }

  // ---------------------------------------------------------------- ランキング（横棒）
  function drawRank(slug) {
    const m = state.meta.indicators[slug];
    const ch = makeChart("chart-rank");
    if (!ch || !m.rank) return;
    const c = palette();
    const F = state.focus;
    let rows = rankRows(m, slug, state.group).map((r, i) => ({ ...r, rank: i + 1 }));
    const n = rows.length;
    if (n > 40) {
      const keep = new Set(rows.slice(0, 15).map((r) => r.iso));
      [F, "JPN"].forEach((iso) => {
        const j = rows.findIndex((r) => r.iso === iso);
        if (j >= 0) rows.slice(Math.max(0, j - 4), j + 5).forEach((r) => keep.add(r.iso));
      });
      const picked = [];
      let prev = -1;
      rows.forEach((r, i) => {
        if (!keep.has(r.iso)) return;
        if (prev >= 0 && i !== prev + 1) picked.push({ gap: true, iso: "gap" + i });
        picked.push(r); prev = i;
      });
      rows = picked;
    }
    const colorOf = (iso) => (iso === F ? c.jp : iso === "JPN" ? c.ref : c.bar);
    const cats = rows.map((r) => (r.gap ? "…" : r.rank + ". " + name(r.iso))).reverse();
    const data = rows.map((r) => r.gap ? { value: null } : ({
      value: r.v,
      itemStyle: { color: colorOf(r.iso), borderRadius: r.v >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] },
      label: { show: r.iso === F || r.iso === "JPN", position: r.v >= 0 ? "right" : "left", color: c.ink, fontWeight: r.iso === F ? 700 : 400, formatter: () => fmt(m, r.v) },
      _r: r,
    })).reverse();
    document.getElementById("chart-rank").style.height = Math.max(240, rows.length * 22 + 40) + "px";
    ch.resize();
    ch.setOption(Object.assign(baseOpt(c), {
      grid: { left: 8, right: 72, top: 8, bottom: 8, containLabel: true },
      tooltip: Object.assign(baseOpt(c).tooltip, {
        trigger: "item",
        formatter: (p) => { const r = p.data && p.data._r; return r ? `${r.rank}位 ${esc(name(r.iso))}<br><b>${fmt(m, r.v)}</b>（${r.y}年）` : ""; },
      }),
      xAxis: { type: "value", splitNumber: narrow() ? 2 : 5, axisLabel: { color: c.muted, hideOverlap: true, formatter: (v) => fmtAxis(m, v) }, splitLine: { lineStyle: { color: c.grid } } },
      yAxis: { type: "category", data: cats, axisTick: { show: false }, axisLine: { lineStyle: { color: c.grid } },
        axisLabel: { color: c.ink2, fontSize: 12 } },
      series: [{ type: "bar", data, barWidth: 14, barCategoryGap: "30%" }],
    }));
    const note = document.getElementById("rank-note");
    if (note) {
      const who = F === "JPN" ? "日本は赤" : `${name(F)}は赤、日本は青`;
      note.textContent = `${groupName(state.group)}（${n}か国・地域）を、各国の最新の値（${state.meta.recentYears}年以内）で比べています（${orderLabel(m)}）。${who}。` +
        (n > 40 ? `上位15位と${[F].concat(F !== "JPN" && rows.some((r) => r.iso === "JPN") ? ["JPN"] : []).map(name).join("・")}の前後を表示。` : "");
    }
  }

  // ---------------------------------------------------------------- 推移（折れ線）
  function colorFor(iso) {
    const c = palette();
    if (iso === state.focus) return c.jp;
    if (!(iso in state.colors)) state.colors[iso] = Object.keys(state.colors).length % c.series.length;
    return c.series[state.colors[iso]];
  }
  function resetColors() {
    state.colors = {};
    if (state.focus !== "JPN") state.colors.JPN = 0; // 日本はいつも青
  }
  function drawTrend(slug) {
    const m = state.meta.indicators[slug];
    const ch = makeChart("chart-trend");
    if (!ch) return;
    const c = palette();
    const { y0, v } = state.series;
    const len = Math.max(...Object.values(v).map((a) => a.length));
    const years = Array.from({ length: len }, (_, i) => y0 + i);
    const isos = state.compare.filter((iso) => v[iso]);
    if (!isos.length) { ch.clear(); return; }
    let first = len;
    isos.forEach((iso) => { const k = v[iso].findIndex((x) => x !== null); if (k >= 0 && k < first) first = k; });
    const xs = years.slice(first);
    const series = isos.map((iso) => ({
      name: name(iso), type: "line", showSymbol: false, connectNulls: true,
      data: v[iso].slice(first),
      lineStyle: { width: iso === state.focus ? 3 : 2, color: colorFor(iso) }, itemStyle: { color: colorFor(iso) },
      z: iso === state.focus ? 10 : 2,
      endLabel: { show: isos.length <= 6 && !narrow(), formatter: "{a}", color: c.ink2, fontSize: 12 },
      emphasis: { focus: "series" },
    }));
    ch.setOption(Object.assign(baseOpt(c), {
      grid: { left: 8, right: isos.length <= 6 && !narrow() ? 72 : 16, top: 16, bottom: 8, containLabel: true },
      tooltip: Object.assign(baseOpt(c).tooltip, {
        trigger: "axis", axisPointer: { type: "line", lineStyle: { color: c.muted } },
        formatter: (ps) => {
          const rows = ps.filter((p) => p.value !== null && p.value !== undefined)
            .sort((a, b) => b.value - a.value)
            .map((p) => `${p.marker}${esc(p.seriesName)}　<b>${fmt(m, p.value)}</b>`).join("<br>");
          return `${ps[0].axisValue}年<br>${rows}`;
        },
      }),
      xAxis: { type: "category", data: xs, boundaryGap: false, axisLabel: { color: c.muted }, axisLine: { lineStyle: { color: c.grid } }, axisTick: { show: false } },
      yAxis: { type: "value", scale: m.fmt === "num", axisLabel: { color: c.muted, formatter: (val) => fmtAxis(m, val) }, splitLine: { lineStyle: { color: c.grid } } },
      series,
    }));
  }
  function drawChips(slug) {
    const box = document.getElementById("chips");
    if (!box) return;
    const v = state.series.v;
    box.innerHTML = "";
    state.compare.forEach((iso) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip";
      const fixed = iso === state.focus;
      b.innerHTML = `<i style="background:${colorFor(iso)}"></i>${esc(name(iso))}` + (fixed ? "" : " <span aria-hidden=true>×</span>");
      if (!fixed) {
        b.setAttribute("aria-label", name(iso) + "を外す");
        b.addEventListener("click", () => { state.compare = state.compare.filter((x) => x !== iso); drawChips(slug); drawTrend(slug); });
      } else b.disabled = true;
      box.appendChild(b);
    });
    const sel = document.createElement("select");
    sel.className = "chip-add"; sel.id = "chip-add"; sel.setAttribute("aria-label", "比べる国を追加");
    sel.innerHTML = `<option value="">＋ 国を追加</option>` + Object.keys(v).filter((iso) => !state.compare.includes(iso))
      .sort((a, b) => name(a).localeCompare(name(b), "ja")).map((iso) => `<option value="${iso}">${esc(name(iso))}</option>`).join("");
    sel.addEventListener("change", () => { if (sel.value) { state.compare.push(sel.value); drawChips(slug); drawTrend(slug); } });
    box.appendChild(sel);
    const presets = document.createElement("span");
    presets.className = "presets";
    ["g7", "asia", "region"].forEach((g) => {
      const p = document.createElement("button");
      p.type = "button"; p.className = "chip ghost"; p.textContent = groupName(g) + "にする";
      p.addEventListener("click", () => {
        const list = members(g).filter((iso) => v[iso] && iso !== state.focus);
        state.compare = [state.focus].concat(g === "region" ? list.slice(0, 7) : list);
        drawChips(slug); drawTrend(slug);
      });
      presets.appendChild(p);
    });
    box.appendChild(presets);
  }
  function defaultCompare(slug) {
    const m = state.meta.indicators[slug];
    const v = state.series.v;
    if (!m.rank) return [state.focus];
    const list = [state.focus];
    if (state.focus !== "JPN") list.push("JPN");
    state.meta.compareDefault.forEach((iso) => { if (!list.includes(iso) && list.length < 6) list.push(iso); });
    return list.filter((iso) => v[iso]);
  }

  // ---------------------------------------------------------------- 主役の国の順位の推移
  function drawRankHist(slug) {
    const m = state.meta.indicators[slug];
    const ch = makeChart("chart-rankhist");
    if (!ch || !m.rank) return;
    const c = palette();
    const F = state.focus;
    const title = document.getElementById("rh-title");
    if (title) title.textContent = name(F) + "の順位の推移";
    const { y0, v } = state.series;
    const isos = Object.keys(v).filter((iso) => inGroup(state.group, iso));
    const len = Math.max(...Object.values(v).map((a) => a.length));
    const pts = [];
    const need = Math.max(5, Math.ceil(isos.length * 0.6));
    for (let i = 0; i < len; i++) {
      const vals = isos.map((iso) => ({ iso, x: v[iso][i] })).filter((o) => o.x !== null && o.x !== undefined);
      const me = vals.find((o) => o.iso === F);
      if (!me || vals.length < need) continue;
      const better = vals.filter((o) => (m.dir === -1 ? o.x < me.x : o.x > me.x)).length;
      pts.push({ year: y0 + i, rank: better + 1, n: vals.length });
    }
    const el = document.getElementById("chart-rankhist");
    const empty = document.getElementById("rh-empty");
    if (!pts.length) {
      ch.clear(); el.hidden = true;
      if (empty) { empty.hidden = false; empty.textContent = `${groupName(state.group)}では、${name(F)}の順位を出せるだけのデータがありません。`; }
      return;
    }
    el.hidden = false; if (empty) empty.hidden = true;
    ch.resize();
    const maxN = Math.max(...pts.map((p) => p.n));
    ch.setOption(Object.assign(baseOpt(c), {
      grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
      tooltip: Object.assign(baseOpt(c).tooltip, {
        trigger: "axis", formatter: (ps) => { const p = pts[ps[0].dataIndex]; return `${p.year}年<br>${esc(name(F))} <b>${p.rank}位</b> / ${p.n}か国・地域`; },
      }),
      xAxis: { type: "category", data: pts.map((p) => p.year), boundaryGap: false, axisLabel: { color: c.muted }, axisLine: { lineStyle: { color: c.grid } }, axisTick: { show: false } },
      yAxis: { type: "value", inverse: true, min: 1, max: maxN, minInterval: 1,
        axisLabel: { color: c.muted, formatter: (val) => val + "位" }, splitLine: { lineStyle: { color: c.grid } } },
      series: [{ type: "line", data: pts.map((p) => p.rank), showSymbol: pts.length < 30, symbolSize: 8,
        lineStyle: { width: 2, color: c.jp }, itemStyle: { color: c.jp } }],
    }));
  }

  // 指標ページの書き出し文と表の強調を、主役の国に合わせる
  function updateLead(slug) {
    const m = state.meta.indicators[slug];
    const F = state.focus;
    const lead = document.getElementById("lead");
    if (lead) {
      if (F === "JPN" && state.group === "oecd" && lead.dataset.static) lead.innerHTML = lead.dataset.static;
      else {
        if (!lead.dataset.static) lead.dataset.static = lead.innerHTML;
        const L = (state.latest[slug] || {})[F];
        if (!L) lead.textContent = `${name(F)}の最近のデータはありません。`;
        else if (!m.rank) lead.textContent = `${name(F)}は${L[0]}年に${fmt(m, L[1])}。`;
        else {
          const rows = rankRows(m, slug, state.group);
          const r = rows.findIndex((x) => x.iso === F) + 1;
          const all = rankRows(m, slug, "world");
          const wr = all.findIndex((x) => x.iso === F) + 1;
          lead.innerHTML = `${esc(name(F))}は${L[0]}年に${fmt(m, L[1])}で、${esc(groupName(state.group))}${rows.length}か国・地域中<strong>${r}位</strong>（${orderLabel(m)}）。` +
            (state.group !== "world" ? ` 全世界では${all.length}か国・地域中${wr}位。` : "");
        }
      }
    }
    document.querySelectorAll("table.rank tr[data-iso]").forEach((tr) => {
      tr.classList.remove("jp");
      tr.classList.toggle("focus", tr.dataset.iso === F);
      tr.classList.toggle("ref", tr.dataset.iso === "JPN" && F !== "JPN");
    });
    const link = document.getElementById("focus-link");
    if (link) {
      link.href = countryHref(F);
      link.textContent = `${name(F)}の強みと弱みを見る`;
      link.hidden = !state.meta.countryPages.includes(F);
    }
  }

  // ---------------------------------------------------------------- 強み・弱み（トップと国のページ）
  function swCards(items) {
    return items.map(({ slug, m, r, n, y, v }) =>
      `<li class="card"><a href="${href("i/" + slug + "/")}${state.focus !== "JPN" ? "#" + state.focus : ""}"><span class="card-rank">${r}<small>位 / ${n}</small></span>` +
      `<span class="card-title">${esc(m.name)}</span><span class="card-text">${fmt(m, v)}（${y}年・${orderLabel(m)}）</span></a></li>`).join("") ||
      '<li class="muted">該当なし</li>';
  }
  function drawSW() {
    const F = state.focus;
    const strong = [], weak = [], feat = [];
    Object.entries(state.meta.indicators).forEach(([slug, m]) => {
      if (!m.rank) return;
      const rows = rankRows(m, slug, state.group);
      const n = rows.length;
      const j = rows.findIndex((r) => r.iso === F);
      const mm = members(state.group);
      const size = mm ? new Set(mm.concat([F])).size : Object.keys(state.meta.names).length;
      if (n < Math.max(5, Math.ceil(size * 0.4)) || j < 0) return; // まとまりの4割以上の国にデータがある指標だけ使う
      const r = j + 1, q = Math.max(1, Math.round(n * 0.25));
      const it = { slug, m, r, n, y: rows[j].y, v: rows[j].v, p: r / n };
      if (m.dir !== 0) { if (r <= q) strong.push(it); else if (r > n - q) weak.push(it); }
      else if (r <= 3 || r > n - 3) feat.push(it);
    });
    strong.sort((a, b) => a.p - b.p);
    weak.sort((a, b) => b.p - a.p);
    feat.sort((a, b) => Math.min(a.p, 1 - a.p) - Math.min(b.p, 1 - b.p));
    document.getElementById("sw-strong").innerHTML = swCards(strong);
    document.getElementById("sw-weak").innerHTML = swCards(weak);
    document.getElementById("sw-feat").innerHTML = swCards(feat);
    document.getElementById("sw-group").textContent = groupName(state.group);
  }
  function drawHero(series) {
    const ch = makeChart("chart-hero");
    if (!ch) return;
    const c = palette();
    const m = state.meta.indicators["price-level"];
    const isos = ["JPN", "DEU", "GBR", "KOR", "CHN"].filter((iso) => series.v[iso]);
    const len = Math.max(...isos.map((iso) => series.v[iso].length));
    const years = Array.from({ length: len }, (_, i) => series.y0 + i);
    let first = len;
    isos.forEach((iso) => { const k = series.v[iso].findIndex((x) => x !== null); if (k >= 0 && k < first) first = k; });
    ch.setOption(Object.assign(baseOpt(c), {
      grid: { left: 8, right: narrow() ? 16 : 72, top: 40, bottom: 8, containLabel: true },
      legend: { top: 0, left: 0, textStyle: { color: c.ink2 }, icon: "roundRect", itemWidth: 14, itemHeight: 4 },
      tooltip: Object.assign(baseOpt(c).tooltip, {
        trigger: "axis",
        formatter: (ps) => `${ps[0].axisValue}年<br>` + ps.filter((p) => p.value != null).sort((a, b) => b.value - a.value)
          .map((p) => `${p.marker}${esc(p.seriesName)}　<b>${fmt(m, p.value)}</b>`).join("<br>"),
      }),
      xAxis: { type: "category", data: years.slice(first), boundaryGap: false, axisLabel: { color: c.muted }, axisLine: { lineStyle: { color: c.grid } }, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.grid } } },
      series: isos.map((iso) => ({
        name: name(iso), type: "line", showSymbol: false, connectNulls: true, data: series.v[iso].slice(first),
        lineStyle: { width: iso === "JPN" ? 3 : 2, color: colorFor(iso) }, itemStyle: { color: colorFor(iso) }, z: iso === "JPN" ? 10 : 2,
        endLabel: { show: !narrow(), formatter: "{a}", color: c.ink2, fontSize: 12 },
        markLine: iso === "JPN" ? { silent: true, symbol: "none", label: { formatter: "米国＝1", color: c.muted, position: "insideEndTop" },
          lineStyle: { color: c.muted, type: "dashed", width: 1 }, data: [{ yAxis: 1 }] } : undefined,
      })),
    }));
  }

  // 国のページへ移る <select>（トップ・国のページ・国の一覧）
  function bindCountryJump() {
    const sel = document.getElementById("country-jump");
    if (!sel) return;
    fillCountrySelect(sel, state.meta.countryPages, state.focus);
    sel.addEventListener("change", () => { if (sel.value && sel.value !== state.focus) location.href = countryHref(sel.value); });
  }

  // ---------------------------------------------------------------- 起動
  function whenCharts(fn) {
    if (window.echarts) return fn();
    let n = 0;
    const t = setInterval(() => {
      if (window.echarts) { clearInterval(t); fn(); return; }
      if (window.__chartsFailed || ++n > 400) {
        clearInterval(t);
        document.querySelectorAll(".chart").forEach((el) => {
          el.style.height = "auto";
          el.innerHTML = '<p class="muted pad">グラフを表示するためのプログラムを読み込めませんでした。通信状態を確かめて、ページを読み込み直してください。</p>';
        });
      }
    }, 50);
  }

  async function init() {
    if (!["home", "indicator", "country", "countries"].includes(PAGE)) return;
    state.meta = await getJSON("data/meta.json");
    if (PAGE === "countries") { bindCountryJump(); return; }
    state.latest = await getJSON("data/latest.json");
    const onScheme = (fn) => matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);

    if (PAGE === "home" || PAGE === "country") {
      state.focus = body.dataset.focus || "JPN";
      state.group = body.dataset.group || defaultGroup(state.focus);
      bindTabs(drawSW);
      bindCountryJump();
      drawSW();
      if (PAGE === "home") {
        const hero = await getJSON("data/i/price-level.json").catch(() => null);
        whenCharts(() => { if (hero) drawHero(hero); });
        onScheme(() => hero && drawHero(hero));
      }
      return;
    }

    // 指標ページ：主役の国は「#KOR」のようなページ内リンク、前回の選択、日本の順で決める
    const slug = body.dataset.slug;
    state.series = await getJSON("data/i/" + slug + ".json");
    const valid = (iso) => iso && state.meta.names[iso];
    const fromHash = location.hash.replace("#", "").toUpperCase();
    state.focus = valid(fromHash) ? fromHash : (valid(store.get("wij-focus")) ? store.get("wij-focus") : "JPN");
    state.group = defaultGroup(state.focus);
    resetColors();
    state.compare = defaultCompare(slug);

    const drawAll = () => { updateLead(slug); drawRank(slug); drawChips(slug); drawTrend(slug); drawRankHist(slug); };
    const setFocus = (iso) => {
      if (!valid(iso) || iso === state.focus) return;
      state.focus = iso;
      store.set("wij-focus", iso);
      state.group = defaultGroup(iso);
      syncTabs();
      resetColors();
      state.compare = defaultCompare(slug);
      const sel = document.getElementById("focus-sel");
      if (sel) sel.value = iso;
      whenCharts(drawAll);
    };
    const sel = document.getElementById("focus-sel");
    if (sel) {
      fillCountrySelect(sel, Object.keys(state.meta.names), state.focus);
      sel.addEventListener("change", () => {
        setFocus(sel.value);
        try { history.replaceState(null, "", "#" + sel.value); } catch (e) { /* 変えられなくても動く */ }
      });
    }
    window.addEventListener("hashchange", () => setFocus(location.hash.replace("#", "").toUpperCase()));
    bindTabs(() => { updateLead(slug); drawRank(slug); drawRankHist(slug); });
    updateLead(slug);
    whenCharts(() => { drawRank(slug); drawChips(slug); drawTrend(slug); drawRankHist(slug); });
    onScheme(() => whenCharts(drawAll));
  }
  init().catch((e) => console.error(e));
})();
