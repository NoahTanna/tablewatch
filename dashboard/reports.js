// Reports tab: end-of-night and weekly numbers from /api/reports/*.
// Times come in seconds; everything here is formatting and two small bar charts.
(function () {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const dash = "–";
  const min = (s) => {
    if (s == null) return dash;
    const m = Math.round(s / 60);
    return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`;
  };
  const hours = (s) => (s == null ? dash : s >= 3600 ? `${(s / 3600).toFixed(1)} h` : `${Math.round(s / 60)} min`);
  const hourLabel = (h) => (h == null ? dash : `${((h + 11) % 12) + 1} ${h < 12 ? "AM" : "PM"}`);
  const timeOf = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const addDays = (isoDay, n) => { const d = new Date(isoDay + "T12:00:00"); d.setDate(d.getDate() + n); return iso(d); };

  let mode = "night", day = null, today = null, data = null, loading = false;

  // Single-series bar chart. Bars sit on the baseline with rounded tops; only the
  // tallest bar is labeled, and tapping any bar shows its value under the chart.
  function bars(items, { max, fmt, axis }) {
    const W = 640, H = 210, L = 44, B = 28, T = 22, R = 8;
    const n = items.length, slot = (W - L - R) / Math.max(1, n), bw = Math.min(46, slot * 0.62);
    const y = (v) => T + (H - T - B) * (1 - v / max);
    let out = "";
    for (const g of axis) {
      out += `<line x1="${L}" x2="${W - R}" y1="${y(g.v)}" y2="${y(g.v)}" stroke="var(--line)" stroke-width="1"/>` +
        `<text x="${L - 8}" y="${y(g.v) + 4}" text-anchor="end" font-size="12" fill="var(--muted)">${g.label}</text>`;
    }
    const top = items.reduce((a, b, i) => (b.value > (items[a] ? items[a].value : -1) ? i : a), 0);
    items.forEach((it, i) => {
      const x = L + slot * i + (slot - bw) / 2, h = Math.max(0, y(0) - y(it.value)), r = Math.min(4, h / 2, bw / 2);
      const yt = y(0) - h;
      const path = h > 0 ? `M${x},${y(0)}V${yt + r}Q${x},${yt} ${x + r},${yt}H${x + bw - r}Q${x + bw},${yt} ${x + bw},${yt + r}V${y(0)}Z` : "";
      out += `<g data-tip="${esc(it.tip)}"><rect x="${L + slot * i}" y="${T}" width="${slot}" height="${H - T - B + 4}" fill="transparent"/>` +
        (path ? `<path class="bar" d="${path}"/>` : "") +
        `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="12.5" fill="var(--muted)">${esc(it.label)}</text>` +
        (i === top && it.value > 0 ? `<text x="${x + bw / 2}" y="${yt - 6}" text-anchor="middle" font-size="13" font-weight="700" fill="var(--text)">${fmt(it.value)}</text>` : "") +
        `<title>${esc(it.tip)}</title></g>`;
    });
    out += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted)" stroke-width="1"/>`;
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">${out}</svg><div class="tip">Tap a bar to see its number.</div>`;
  }

  function tile(k, v, s) { return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`; }

  function nightHtml(r) {
    if (!r.parties) return `<div class="r-empty">No finished parties for this night yet.</div>`;
    const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
    const busy = r.busy_hours.map((h) => ({ label: hourLabel(h.hour).replace(" ", "").toLowerCase(), value: Math.round(h.busy * 100), tip: `${hourLabel(h.hour)}: ${Math.round(h.busy * 100)}% of tables had guests` }));
    return `
      <div class="tiles">
        ${tile("Parties seated", r.parties, `<b>${r.turns_per_table.toFixed(1)}</b> per table`)}
        ${tile("Typical meal", min(r.avg_stay), "sit down to leave")}
        ${tile("First service", min(r.avg_first_service), `<b>${plural(r.late_starts, "table")}</b> waited ${min(r.late_after)}+`)}
        ${tile("Wait to clear", min(r.avg_clear_wait), `<b>${plural(r.went_red, "table")}</b> went red`)}
      </div>
      <div class="panel"><h3>How full the room was</h3><div class="sub">Share of tables with guests, hour by hour.</div>
        ${bars(busy, { max: 100, fmt: (v) => `${v}%`, axis: [{ v: 0, label: "0%" }, { v: 50, label: "50%" }, { v: 100, label: "100%" }] })}</div>
      <div class="panels">
        <div class="panel"><h3>Table time not earning</h3><div class="sub">Dirty after guests left, plus clean but empty before the next party.</div>
          <div class="big">${hours(r.idle_table_time)}</div>
          <div class="split"><span>dirty <b>${hours(r.dirty_table_time)}</b></span><span>empty <b>${hours(r.idle_table_time - r.dirty_table_time)}</b></span><span>empty between parties <b>${min(r.avg_empty_between)}</b> on average</span></div>
          <div class="est">${r.extra_parties_estimate != null ? `On a night with a wait, that's roughly <b>${r.extra_parties_estimate.toFixed(1)} more parties</b> at a typical meal length. An estimate, not a promise.` : ""}</div>
        </div>
        <div class="panel"><h3>Slowest moments</h3><div class="sub">Longest waits tonight.</div>
          <ul class="items">
            ${r.worst_clear_wait ? `<li>Table ${esc(r.worst_clear_wait.table)} waited to be cleared <span>${min(r.worst_clear_wait.seconds)}</span></li>` : ""}
            ${r.slowest_first_service.map((x) => `<li>Table ${esc(x.table)}, seated ${timeOf(x.at)}, first service after <span>${min(x.seconds)}</span></li>`).join("")}
          </ul>
        </div>
      </div>
      <div class="panel"><h3>By table</h3>
        <div class="scroll-x"><table class="r">
          <thead><tr><th>Table</th><th class="n">Parties</th><th class="n">Typical meal</th><th class="n">First service</th><th class="n">Wait to clear</th><th class="n">Went red</th></tr></thead>
          <tbody>${r.tables.map((t) => `<tr><td>${esc(t.table)} <span style="color:var(--muted)">· ${t.seats || "?"} seats</span></td><td class="n">${t.parties}</td><td class="n">${min(t.avg_stay)}</td>
            <td class="n">${min(t.avg_first_service)}</td><td class="n">${min(t.avg_clear_wait)}</td><td class="n ${t.went_red ? "flag" : ""}">${t.went_red || dash}</td></tr>`).join("")}</tbody>
        </table></div></div>`;
  }

  function weekHtml(w) {
    if (!w.parties) return `<div class="r-empty">No finished parties in these 7 nights.</div>`;
    const top = Math.max(...w.nights.map((n) => n.parties));
    const nice = top <= 10 ? 10 : Math.ceil(top / 20) * 20;
    const perNight = w.nights.map((n) => ({ label: n.short, value: n.parties, tip: `${n.label}: ${n.parties} parties` }));
    return `
      <div class="tiles">
        ${tile("Parties seated", w.parties, `over 7 nights`)}
        ${tile("Tables went red", w.went_red, "waited 3+ min to be cleared")}
        ${tile("Late first service", w.late_starts, `${min(w.late_after)}+ before anything arrived`)}
        ${tile("Table time not earning", hours(w.idle_table_time), w.extra_parties_estimate ? `roughly <b>${Math.round(w.extra_parties_estimate)}</b> more parties on busy nights` : "")}
      </div>
      <div class="panel"><h3>Parties per night</h3><div class="sub">${w.slowest_clearing_night ? `Slowest clearing: <b>${esc(w.slowest_clearing_night)}</b>.` : ""}</div>
        ${bars(perNight, { max: nice, fmt: (v) => `${v}`, axis: [{ v: 0, label: "0" }, { v: nice / 2, label: `${nice / 2}` }, { v: nice, label: `${nice}` }] })}</div>
      <div class="panel"><h3>Night by night</h3><div class="sub">Tap a night to open its report.</div>
        <div class="scroll-x"><table class="r">
          <thead><tr><th>Night</th><th class="n">Parties</th><th class="n">Typical meal</th><th class="n">First service</th><th class="n">Wait to clear</th><th class="n">Went red</th><th class="n">Busiest</th></tr></thead>
          <tbody>${w.nights.map((n) => `<tr class="go" data-day="${n.day}"><td>${esc(n.label)}</td><td class="n">${n.parties || dash}</td><td class="n">${min(n.avg_stay)}</td>
            <td class="n">${min(n.avg_first_service)}</td><td class="n">${min(n.avg_clear_wait)}</td><td class="n ${n.went_red ? "flag" : ""}">${n.went_red || dash}</td><td class="n">${hourLabel(n.busiest_hour)}</td></tr>`).join("")}</tbody>
        </table></div></div>`;
  }

  function title() {
    if (!data) return "Reports";
    if (mode === "night") return data.label + (day === today ? " (tonight)" : "");
    const fmt = (d) => new Date(d + "T12:00:00").toLocaleDateString([], { month: "short", day: "numeric" });
    return `${fmt(data.start)} to ${fmt(data.end)}`;
  }

  function draw() {
    const el = document.getElementById("reports-view");
    const atToday = day === today;
    el.innerHTML = `
      <div class="r-bar">
        <h2>${esc(title())}</h2>
        <div class="seg" role="group" aria-label="Report">
          <button type="button" data-rmode="night" aria-pressed="${mode === "night"}">Night</button>
          <button type="button" data-rmode="week" aria-pressed="${mode === "week"}">Week</button>
        </div>
        <div class="stepper">
          <button type="button" data-step="-1" aria-label="Earlier">‹</button>
          <button type="button" data-step="1" aria-label="Later" ${atToday ? "disabled" : ""}>›</button>
        </div>
      </div>
      ${mode === "night" && atToday ? `<p class="r-note">So far tonight. A party counts once it has left.</p>` : ""}
      ${!data ? `<div class="r-empty">${loading ? "Loading…" : "Couldn't load the report. Check the connection and try again."}</div>` : mode === "night" ? nightHtml(data) : weekHtml(data)}`;
  }

  async function load() {
    loading = true; draw();
    try {
      const url = mode === "night" ? `/api/reports/night${day ? `?day=${day}` : ""}` : `/api/reports/week${day ? `?end=${day}` : ""}`;
      const r = await fetch(url);
      data = r.ok ? await r.json() : null;
      if (data && !today) { today = mode === "night" ? data.day : data.end; day = today; }
    } catch (e) { data = null; }
    loading = false; draw();
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#reports-view")) return;
    const m = e.target.closest("[data-rmode]"), s = e.target.closest("[data-step]"), row = e.target.closest("tr[data-day]"), tip = e.target.closest("[data-tip]");
    if (m && m.dataset.rmode !== mode) { mode = m.dataset.rmode; data = null; load(); }
    else if (s && !s.disabled && today) { day = addDays(day || today, Number(s.dataset.step) * (mode === "week" ? 7 : 1)); if (day > today) day = today; data = null; load(); }
    else if (row) { mode = "night"; day = row.dataset.day; data = null; load(); }
    else if (tip) {
      const box = tip.closest(".panel").querySelector(".tip");
      tip.closest("svg").querySelectorAll(".bar.on").forEach((b) => b.classList.remove("on"));
      const bar = tip.querySelector(".bar"); if (bar) bar.classList.add("on");
      box.innerHTML = `<b>${esc(tip.dataset.tip)}</b>`;
    }
  });

  // Called by app.js when the Reports tab opens, and every few minutes while it's open.
  window.Reports = { open() { load(); }, refresh() { if (day === today && !loading) load(); } };
})();
