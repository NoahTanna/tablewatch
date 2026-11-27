// TableWatch host-stand screen: live table states over Server-Sent Events,
// shown as a floor map (with meal rings) or as lanes by what to do.
//
// Quiet by design: only two things raise the alert strip and chime (a table to
// clear, a table nobody has served). Stages, hints and timers are plain text.

const tables = {};       // table id -> { info (from floor.json), t (from the server) }
let floor = null;
let clockOffset = 0;     // server time - local time, in seconds
let lastEventAt = null;  // server time of the camera's last report
let summary = null;
let view = "map", theme = "light";
const CAMERA_STALE_S = 120;
const MEAL_TYPICAL_S = 75 * 60; // only used to draw how far round the meal ring is

const nowServer = () => Date.now() / 1000 + clockOffset;
const mins = (s) => { s = Math.max(0, Math.floor(s / 60)); return s >= 60 ? `${Math.floor(s / 60)} h ${String(s % 60).padStart(2, "0")}` : `${s} min`; };
const clock = (s) => { s = Math.max(0, Math.floor(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ICON = { FREE: "free", SEATED: "seat", WAIT: "wait", EATING: "eat", FINISHING: "check", LEFT: "left", CLEAR: "clear" };

// ---------- Settings remembered on this iPad ----------
function load(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } }
function save(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode: fine */ } }

// ---------- What each table shows ----------
function status(t) {
  const n = nowServer();
  let key = { SERVED: "EATING", CLEAR: "CLEAR", LEFT: "LEFT", FINISHING: "FINISHING", SEATED: "SEATED", FREE: "FREE" }[t.stage] || "FREE";
  if (t.alert === "not_served") key = "WAIT";
  const seatedFor = t.seated_at != null ? n - t.seated_at : 0;
  let label = "", time = "", age = 0;
  switch (key) {
    case "CLEAR": label = "Clear table"; age = n - t.unattended_since; time = clock(age); break;
    case "LEFT": label = "Guests left"; age = n - t.unattended_since; time = clock(age); break;
    case "WAIT": label = "Nothing served"; age = seatedFor; time = mins(age); break;
    case "SEATED": label = "Just seated"; time = seatedFor >= 60 ? mins(seatedFor) : ""; break;
    case "EATING": label = "Eating"; time = seatedFor >= 60 ? mins(seatedFor) : ""; break;
    case "FINISHING": label = "Plates gone"; time = n - t.plates_gone_since >= 60 ? mins(n - t.plates_gone_since) : ""; break;
    default: {
      const emptyFor = t.free_since != null && n - t.free_since >= 60;
      label = emptyFor ? "Empty for" : "Free"; time = emptyFor ? mins(n - t.free_since) : "";
    }
  }
  const alert = key === "CLEAR" ? "clear" : key === "WAIT" ? "wait" : null;
  return { key, label, time, age, alert, hints: t.hints || [], seatedFor };
}
const HINT_TEXT = { check: "check?", long_stay: "long stay" };

// ---------- Map view ----------
const W = 1000, H = 700;
function geo(info) {
  const shape = info.shape || "square";
  const base = { round: [74, 74], square: [90, 90], booth: [118, 84], rect: [60 + 26 * (info.seats || 6), 66] }[shape] || [90, 90];
  return { x: info.x * W / 100, y: info.y * H / 100, w: info.w ? info.w * W / 100 : base[0], h: info.h ? info.h * H / 100 : base[1], shape, seats: info.seats || 4 };
}
function chairs(g) {
  const out = [], { x, y, w, h } = g;
  const r = (cx, cy, cw, ch) => out.push(`<rect x="${cx - cw / 2}" y="${cy - ch / 2}" width="${cw}" height="${ch}" rx="6" style="fill:var(--chair)"/>`);
  if (g.shape === "round") { r(x - w / 2 - 15, y, 16, 34); r(x + w / 2 + 15, y, 16, 34); }
  else if (g.shape === "booth") { r(x - w / 2 - 16, y, 20, h + 12); r(x + w / 2 + 16, y, 20, h + 12); }
  else if (g.shape === "rect") {
    const perSide = Math.max(1, Math.round((g.seats - 2) / 2)), step = w / perSide;
    for (let i = 0; i < perSide; i++) { const cx = x - w / 2 + step * (i + 0.5); r(cx, y - h / 2 - 14, Math.min(40, step - 8), 14); r(cx, y + h / 2 + 14, Math.min(40, step - 8), 14); }
    r(x - w / 2 - 14, y, 14, 36); r(x + w / 2 + 14, y, 14, 36);
  } else { r(x, y - h / 2 - 14, 36, 14); r(x, y + h / 2 + 14, 36, 14); r(x - w / 2 - 14, y, 14, 36); r(x + w / 2 + 14, y, 14, 36); }
  return out.join("");
}
function shapeEl(g, style, extra = "") {
  return g.shape === "round"
    ? `<circle cx="${g.x}" cy="${g.y}" r="${g.w / 2}" style="${style}" ${extra}/>`
    : `<rect x="${g.x - g.w / 2}" y="${g.y - g.h / 2}" width="${g.w}" height="${g.h}" rx="${g.shape === "rect" ? 14 : 12}" style="${style}" ${extra}/>`;
}
function mealRing(g, s) {
  let p = 0;
  if (s.key === "SEATED" || s.key === "WAIT") p = 0.1;
  else if (s.key === "EATING") p = Math.min(0.8, 0.25 + (s.seatedFor / MEAL_TYPICAL_S) * 0.55);
  else if (s.key === "FINISHING") p = 0.9;
  const pad = 9;
  if (g.shape === "round") {
    const r = g.w / 2 + pad, L = 2 * Math.PI * r;
    return `<circle cx="${g.x}" cy="${g.y}" r="${r}" fill="none" style="stroke:var(--track)" stroke-width="7"/>` +
      (p ? `<circle cx="${g.x}" cy="${g.y}" r="${r}" fill="none" style="stroke:var(--seat)" stroke-width="7" stroke-linecap="round" stroke-dasharray="${p * L} ${L}" transform="rotate(-90 ${g.x} ${g.y})"/>` : "");
  }
  const w = g.w + pad * 2, h = g.h + pad * 2, L = 2 * (w + h);
  const box = `x="${g.x - w / 2}" y="${g.y - h / 2}" width="${w}" height="${h}" rx="16" fill="none" stroke-width="7"`;
  return `<rect ${box} style="stroke:var(--track)"/>` + (p ? `<rect ${box} style="stroke:var(--seat)" stroke-linecap="round" pathLength="${L}" stroke-dasharray="${p * L} ${L}"/>` : "");
}
function roomEl() {
  const room = (floor && floor.room) || {};
  let out = `<rect x="20" y="24" width="960" height="652" rx="6" style="fill:var(--surface);stroke:var(--wall)" stroke-width="4"/>`;
  for (const l of room.landmarks || []) {
    const w = l.w * W / 100, h = l.h * H / 100, x = l.x * W / 100, y = l.y * H / 100, tall = h > w;
    out += `<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="8" style="fill:var(--chair)"/>` +
      `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle" font-size="14" style="fill:var(--faint)" ${tall ? `transform="rotate(90 ${x} ${y})"` : ""}>${esc(l.label)}</text>`;
  }
  for (const l of room.labels || []) out += `<text x="${l.x * W / 100}" y="${l.y * H / 100}" text-anchor="middle" font-size="13" style="fill:var(--faint)">${esc(l.text)}</text>`;
  if (room.host) {
    const x = room.host.x * W / 100, y = room.host.y * H / 100;
    out += `<circle cx="${x}" cy="${y}" r="9" style="fill:var(--text)"/><text x="${x + 16}" y="${y + 5}" font-size="14" font-weight="700" style="fill:var(--text)">You</text>`;
  }
  return out;
}
function renderMap() {
  let out = roomEl();
  for (const id in tables) {
    const { info, t } = tables[id];
    if (!t) continue;
    const g = geo(info), s = status(t);
    const solid = s.alert === "clear" ? "var(--clear)" : s.alert === "wait" ? "var(--wait)" : null;
    const free = s.key === "FREE", left = s.key === "LEFT";
    const fill = solid || (free ? "var(--free-soft)" : "var(--surface)");
    const stroke = solid || (free ? "var(--free)" : left ? "var(--left)" : "var(--track)");
    const ink = solid ? "var(--on-alert)" : "var(--text)";
    const small = g.shape === "round";
    const timeText = free && s.time ? (small ? s.time : `empty ${s.time}`) : s.time;
    out += `<g ${s.alert ? `class="tap" data-act="${esc(id)}"` : ""} aria-label="Table ${esc(info.name)}: ${s.label} ${s.time}">` +
      chairs(g) + (solid || free ? "" : mealRing(g, s)) +
      shapeEl(g, `fill:${fill};stroke:${stroke}`, `stroke-width="${solid ? 0 : 2.5}" ${left ? 'stroke-dasharray="6 5"' : ""}`) +
      `<text x="${g.x}" y="${g.y + (timeText ? -3 : 10)}" text-anchor="middle" font-size="${small ? 28 : 32}" font-weight="800" style="fill:${ink}">${esc(info.name)}</text>` +
      (timeText ? `<text x="${g.x}" y="${g.y + 19}" text-anchor="middle" font-size="${small ? 12.5 : 14}" font-weight="600" style="fill:${solid ? "var(--on-alert)" : "var(--muted)"}">${timeText}</text>` : "") +
      s.hints.map((h, i) => `<g transform="translate(${g.x - 37} ${g.y + g.h / 2 + (g.shape === "booth" ? 14 : 28) + i * 24})"><rect width="74" height="21" rx="10.5" style="fill:var(--hint-bg);stroke:var(--hint-line)"/><text x="37" y="15" text-anchor="middle" font-size="12" font-weight="700" style="fill:var(--hint)">${HINT_TEXT[h] || h}</text></g>`).join("") +
      `</g>`;
  }
  document.getElementById("map").innerHTML = out;
}

// ---------- List view ----------
const LANES = [
  { name: "Clear now", sub: "tap when cleared", c: "var(--clear)", keys: ["CLEAR"] },
  { name: "Needs service", sub: "nothing on the table yet", c: "var(--wait)", keys: ["WAIT", "SEATED"] },
  { name: "Eating", sub: "", c: "var(--seat)", keys: ["EATING"] },
  { name: "Wrapping up", sub: "plates gone or just left", c: "var(--left)", keys: ["FINISHING", "LEFT"] },
  { name: "Open", sub: "ready to seat", c: "var(--free)", keys: ["FREE"] },
];
const TICKET_COLOR = { CLEAR: "var(--clear)", WAIT: "var(--wait)", SEATED: "var(--track)", EATING: "var(--seat)", FINISHING: "var(--seat)", LEFT: "var(--left)", FREE: "var(--free)" };
function renderList() {
  const all = Object.entries(tables).filter(([, x]) => x.t).map(([id, x]) => ({ id, info: x.info, s: status(x.t) }));
  document.getElementById("list-view").innerHTML = LANES.map((l) => {
    const items = all.filter((x) => l.keys.includes(x.s.key)).sort((a, b) => (l.keys.indexOf(a.s.key) - l.keys.indexOf(b.s.key)) || (b.s.age - a.s.age));
    return `<section class="lane" style="--c:${l.c}"><h2>${l.name} <span>${items.length}</span></h2>${l.sub ? `<div class="sub">${l.sub}</div>` : ""}
      <div class="tickets">${items.length ? items.map(({ id, info, s }) => {
        const tag = s.alert ? "button" : "div";
        return `<${tag} class="ticket ${s.alert ? "act" : ""}" ${s.alert ? `data-act="${esc(id)}"` : ""} style="--c:${TICKET_COLOR[s.key]}">
          <div class="num">${esc(info.name)}</div>
          <div class="what">${icon(ICON[s.key])}<span>${s.label}</span></div>
          <div class="time">${s.time || (s.key === "FREE" ? "ready" : "just now")}</div>
          <div class="meta"><span>${info.seats || "?"} seats${info.section ? " · " + esc(info.section) : ""}</span>${s.hints.map((h) => `<span class="h">${HINT_TEXT[h] || h}</span>`).join("")}</div>
          ${s.alert ? `<div class="do">${s.alert === "clear" ? "Tap when cleared" : "Tap once someone has been over"}</div>` : ""}
        </${tag}>`;
      }).join("") : `<div class="empty">none</div>`}</div></section>`;
  }).join("");
}

// ---------- Header, alerts, footer ----------
function renderHeader() {
  document.getElementById("clock").textContent = new Date(nowServer() * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (summary) {
    const s = summary;
    const dots = document.getElementById("dots");
    dots.classList.toggle("bar", s.tables_total > 16); // a dot per table, or a bar for big rooms
    dots.innerHTML = s.tables_total > 16
      ? `<i style="width:${(100 * s.tables_in_use) / Math.max(1, s.tables_total)}%"></i>`
      : Array.from({ length: s.tables_total }, (_, i) => `<i class="${i < s.tables_in_use ? "on" : ""}"></i>`).join("");
    document.getElementById("fill-text").innerHTML = `<b>${s.tables_in_use} of ${s.tables_total}</b> tables<br><b>${s.seats_in_use} of ${s.seats_total}</b> seats`;
  }
  for (const v of ["map", "list", "reports"]) document.getElementById("v-" + v).setAttribute("aria-pressed", view === v);
  document.getElementById("theme").innerHTML = theme === "light" ? `${icon("moon")}Dark` : `${icon("sun")}Light`;
  const snd = document.getElementById("sound");
  snd.innerHTML = `${icon("bell")}${audio ? "Sound on" : "Sound off"}`;
  snd.classList.toggle("on", !!audio);
}
function urgent() {
  return Object.entries(tables).filter(([, x]) => x.t).map(([id, x]) => ({ id, info: x.info, s: status(x.t) }))
    .filter((x) => x.s.alert)
    .sort((a, b) => (a.s.alert === b.s.alert ? b.s.age - a.s.age : a.s.alert === "clear" ? -1 : 1));
}
function renderAlerts() {
  const el = document.getElementById("alerts");
  if (view === "list") { el.innerHTML = ""; return; } // the first two lanes are the alerts
  const u = urgent();
  el.innerHTML = u.length ? u.map(({ id, info, s }) => `<button class="alert ${s.alert}" data-act="${esc(id)}">${icon(ICON[s.key])}
      <span>Table ${esc(info.name)} <small>${s.alert === "clear" ? `clear it · ${s.time}` : `nothing served · ${s.time}`}</small></span>
      <em>${s.alert === "clear" ? "Cleared" : "Visited"}</em></button>`).join("")
    : `<div class="calm">All good. Nothing needs you right now.</div>`;
}
function renderFooter() {
  const parts = [];
  const approx = (secs) => (secs < 60 ? "under 1 min" : `${Math.round(secs / 60)} min`);
  if (summary && summary.avg_first_service != null) parts.push(`<span>First service tonight <b>${approx(summary.avg_first_service)}</b></span>`);
  if (summary && summary.avg_empty_between != null) parts.push(`<span>Empty between parties <b>${approx(summary.avg_empty_between)}</b></span>`);
  if (!parts.length) parts.push(`<span>Tonight's averages appear once the first parties have left.</span>`);
  const key = view === "map" ? `<div class="key">
      <span><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7" fill="none" style="stroke:var(--track)" stroke-width="3"/><path d="M10 3a7 7 0 0 1 7 7" fill="none" style="stroke:var(--seat)" stroke-width="3" stroke-linecap="round"/></svg>ring fills as the meal goes on</span>
      <span><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" style="fill:var(--free-soft);stroke:var(--free)" stroke-width="2"/></svg>free</span>
      <span><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" style="fill:var(--surface);stroke:var(--left)" stroke-width="2" stroke-dasharray="4 3"/></svg>guests left</span>
    </div>` : "";
  document.getElementById("footer").innerHTML = parts.join("") + key;
}
function render() {
  document.documentElement.dataset.theme = theme;
  document.getElementById("map-view").hidden = view !== "map";
  document.getElementById("list-view").hidden = view !== "list";
  document.getElementById("reports-view").hidden = view !== "reports";
  document.getElementById("footer").hidden = view === "reports";
  renderHeader();
  renderAlerts(); // stays visible on Reports too, so a red table is never missed
  if (view === "map") renderMap(); else if (view === "list") renderList(); // reports draw themselves
  renderFooter();
  renderCamera();
  checkChime();
}

// ---------- Sound: one soft two-note chime per new alert ----------
// iPad Safari only plays sound after a tap, so staff tap "Sound off" once per shift.
let audio = null;
const chimed = new Set();
function chime() {
  if (!audio) return;
  const t0 = audio.currentTime;
  [[880, 0], [660, 0.18]].forEach(([freq, at]) => {
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t0 + at);
    gain.gain.exponentialRampToValueAtTime(0.25, t0 + at + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + at + 0.5);
    osc.connect(gain).connect(audio.destination);
    osc.start(t0 + at);
    osc.stop(t0 + at + 0.55);
  });
}
function checkChime() {
  let fresh = false;
  const live = new Set();
  for (const { id, s } of urgent()) {
    const k = id + ":" + s.alert;
    live.add(k);
    if (!chimed.has(k)) { chimed.add(k); fresh = true; }
  }
  for (const k of [...chimed]) if (!live.has(k)) chimed.delete(k);
  if (fresh) chime(); // one chime even if several alerts appear at once
}
function toggleSound() {
  if (audio) { audio.close(); audio = null; }
  else { try { audio = new (window.AudioContext || window.webkitAudioContext)(); chime(); } catch (e) { audio = null; } }
  render();
}

// ---------- Actions ----------
async function post(id, action) {
  try {
    const r = await fetch(`/api/tables/${encodeURIComponent(id)}/${action}`, { method: "POST" });
    if (r.ok) { tables[id].t = await r.json(); render(); }
  } catch (e) { setOnline(false); }
}
function onAct(id) {
  const x = tables[id];
  if (!x || !x.t) return;
  const s = status(x.t);
  if (s.alert === "clear") post(id, "clear");
  else if (s.alert === "wait") post(id, "served"); // "someone has been over"
}

// ---------- Connection and camera health ----------
async function loadAll() {
  const data = await (await fetch("/api/tables")).json();
  clockOffset = data.now - Date.now() / 1000;
  lastEventAt = data.last_event_at;
  summary = data.summary;
  for (const t of data.tables) if (tables[t.id]) tables[t.id].t = t;
  render();
}
function renderCamera() {
  const el = document.getElementById("nocam");
  const offline = !document.getElementById("offline").hidden;
  const age = lastEventAt == null ? null : nowServer() - lastEventAt;
  const stale = age == null || age > CAMERA_STALE_S;
  el.hidden = !stale || offline;
  el.textContent = age == null
    ? "Waiting for camera data… (table colors are not live yet)"
    : `No camera data for ${Math.floor(age / 60)} min. Check the camera box. Table colors may be out of date.`;
  document.body.classList.toggle("stale", stale || offline);
}
function setOnline(ok) {
  document.getElementById("offline").hidden = ok;
  const c = document.getElementById("conn");
  c.textContent = ok ? "Live" : "Offline";
  c.classList.toggle("ok", ok);
  renderCamera();
}
function connect() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { setOnline(true); loadAll().catch(() => setOnline(false)); };
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    clockOffset = msg.now - Date.now() / 1000;
    lastEventAt = msg.last_event_at;
    summary = msg.summary;
    if (tables[msg.table.id]) tables[msg.table.id].t = msg.table;
    render();
  };
  es.onerror = () => setOnline(false); // EventSource reconnects by itself
}

async function main() {
  const params = new URLSearchParams(location.search);
  view = params.get("view") || load("tw-view", "map");
  theme = params.get("theme") || load("tw-theme", "light");
  floor = await (await fetch("/api/floor")).json();
  for (const info of floor.tables) tables[info.id] = { info, t: null };
  document.getElementById("map").setAttribute("viewBox", `0 0 ${W} ${H}`);
  document.querySelectorAll("header .seg button").forEach((b) => b.addEventListener("click", () => {
    view = b.dataset.view; save("tw-view", view); render();
    if (view === "reports") window.Reports.open();
  }));
  document.getElementById("theme").addEventListener("click", () => { theme = theme === "light" ? "dark" : "light"; save("tw-theme", theme); render(); });
  document.getElementById("sound").addEventListener("click", toggleSound);
  document.body.addEventListener("click", (e) => { const a = e.target.closest("[data-act]"); if (a) onAct(a.dataset.act); });
  if (!["map", "list", "reports"].includes(view)) view = "map";
  render();
  if (view === "reports") window.Reports.open();
  connect();
  setInterval(render, 1000);
  setInterval(() => { if (view === "reports") window.Reports.refresh(); }, 120000);
  // Full refresh every 30 s: picks up the camera's heartbeat and anything missed.
  setInterval(() => loadAll().catch(() => setOnline(false)), 30000);
  // iPad wakes from sleep: refresh everything.
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadAll().catch(() => setOnline(false)); });
}

main().catch(() => { setOnline(false); setTimeout(() => location.reload(), 5000); });
