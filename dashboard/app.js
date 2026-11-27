// TableWatch dashboard: floor map + live updates over Server-Sent Events.
//
// Quiet by design: only two things raise the banner and chime (a table to clear,
// a table nobody has served). Stages, hints and timers are plain text on the tiles.
const LABELS = {
  FREE: "FREE", SEATED: "SEATED", SERVED: "SERVED", FINISHING: "PLATES GONE",
  LEFT: "GUESTS LEFT", CLEAR: "CLEAR",
};
const HINTS = { check: "check?", long_stay: "long stay" };
const floorEl = document.getElementById("floor");
const tiles = {};   // table id -> {el, table, info}
let clockOffset = 0; // server time - local time, in seconds
let lastEventAt = null; // server time of the camera's last report
let summary = null;
const CAMERA_STALE_S = 120;
const alerted = new Set(); // "T3:clear" keys already chimed for

function nowServer() { return Date.now() / 1000 + clockOffset; }

function mins(secs) { return Math.max(0, Math.floor(secs / 60)); }
function clock(secs) {
  secs = Math.max(0, Math.floor(secs));
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

function sizeFor(t) {
  // Size in vmin, from seat count and shape. Big enough to tap easily.
  const base = t.seats <= 2 ? 15 : 17;
  const wide = t.shape === "rect" ? Math.max(1.4, t.seats / 4) : 1;
  return { w: base * wide, h: base };
}

function buildFloor(floor) {
  floorEl.innerHTML = "";
  for (const t of floor.tables) {
    const el = document.createElement("div");
    const s = sizeFor(t);
    el.className = `table ${t.shape}`;
    el.style.left = t.x + "%";
    el.style.top = t.y + "%";
    el.style.width = s.w + "vmin";
    el.style.height = s.h + "vmin";
    el.innerHTML = `<div class="name"></div><div class="label"></div><div class="timer"></div><div class="hints"></div>`;
    el.querySelector(".name").textContent = t.name;
    el.addEventListener("click", () => onTap(t.id));
    floorEl.appendChild(el);
    tiles[t.id] = { el, table: null, info: t };
  }
}

function render(table) {
  const tile = tiles[table.id];
  if (!tile) return;
  tile.table = table;
  const el = tile.el;
  el.classList.remove(...Object.keys(LABELS), "not_served");
  el.classList.add(table.stage);
  if (table.alert === "not_served") el.classList.add("not_served");
  el.querySelector(".label").textContent = table.alert === "not_served" ? "WAITING" : LABELS[table.stage];
  const hints = el.querySelector(".hints");
  hints.innerHTML = "";
  for (const h of table.hints || []) {
    const span = document.createElement("span");
    span.className = "hint";
    span.textContent = HINTS[h] || h;
    hints.appendChild(span);
  }
  renderTimer(tile);
}

function renderTimer(tile) {
  const t = tile.table, now = nowServer();
  let text = "";
  if (t.stage === "CLEAR") text = clock(now - t.unattended_since);
  else if (t.stage === "LEFT") text = `left ${clock(now - t.unattended_since)}`;
  else if (t.alert === "not_served") text = `${mins(now - t.seated_at)} min`;
  else if ((t.stage === "SEATED" || t.stage === "SERVED") && now - t.seated_at >= 60) text = `${mins(now - t.seated_at)} min`;
  else if (t.stage === "FINISHING" && now - t.plates_gone_since >= 60) text = `${mins(now - t.plates_gone_since)} min`;
  else if (t.stage === "FREE" && t.free_since != null && now - t.free_since >= 60) text = `empty ${mins(now - t.free_since)} min`;
  tile.el.querySelector(".timer").textContent = text;
}

function renderSummary() {
  if (!summary) return;
  const s = summary;
  document.getElementById("f-tables").textContent = `${s.tables_in_use} / ${s.tables_total}`;
  document.getElementById("f-seats").textContent = `${s.seats_in_use} / ${s.seats_total}`;
  document.getElementById("f-bar").style.width = s.tables_total ? `${(100 * s.tables_in_use) / s.tables_total}%` : "0";
  const parts = [];
  const approx = (secs) => (secs < 60 ? "under 1 min" : `~${Math.round(secs / 60)} min`);
  if (s.avg_first_service != null) parts.push(`First service ${approx(s.avg_first_service)}`);
  if (s.avg_empty_between != null) parts.push(`Empty between parties ${approx(s.avg_empty_between)}`);
  document.getElementById("tonight").textContent = parts.length ? `Tonight: ${parts.join(" · ")}` : "";
}

function renderBanner() {
  const items = [];
  let anyClear = false;
  const now = nowServer();
  const live = new Set();
  let fresh = false;
  for (const id in tiles) {
    const { table, info } = tiles[id];
    if (!table || !table.alert) continue;
    const key = `${id}:${table.alert}`;
    live.add(key);
    if (table.alert === "clear") {
      anyClear = true;
      items.push(`Table ${info.name}: clear it (${clock(now - table.unattended_since)})`);
    } else {
      items.push(`Table ${info.name}: nothing served for ${mins(now - table.seated_at)} min`);
    }
    if (!alerted.has(key)) { alerted.add(key); fresh = true; }
  }
  if (fresh) chime(); // one chime even if several alerts appear at once
  for (const key of [...alerted]) if (!live.has(key)) alerted.delete(key);
  const b = document.getElementById("banner");
  b.hidden = items.length === 0;
  b.classList.toggle("only-attention", !anyClear);
  b.innerHTML = "";
  for (const text of items) {
    const span = document.createElement("span");
    span.textContent = text;
    b.appendChild(span);
  }
}

// --- Sound: one soft two-note chime per new alert. iPad Safari only plays sound
// after a tap, so staff tap "Sound off" once per shift to turn it on.
let audio = null;
function soundOn() { return audio != null; }
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
function toggleSound() {
  const btn = document.getElementById("sound");
  if (soundOn()) { audio.close(); audio = null; }
  else {
    try { audio = new (window.AudioContext || window.webkitAudioContext)(); chime(); } catch (e) { audio = null; }
  }
  btn.textContent = soundOn() ? "Sound on" : "Sound off";
  btn.classList.toggle("on", soundOn());
}

async function post(id, action) {
  try {
    const r = await fetch(`/api/tables/${encodeURIComponent(id)}/${action}`, { method: "POST" });
    if (r.ok) { render(await r.json()); renderBanner(); }
  } catch (e) { setOnline(false); }
}

function onTap(id) {
  const t = tiles[id].table;
  if (!t) return;
  if (t.stage === "CLEAR") post(id, "clear");
  else if (t.alert === "not_served") post(id, "served"); // "we've been there"
}

async function loadAll() {
  const data = await (await fetch("/api/tables")).json();
  clockOffset = data.now - Date.now() / 1000;
  lastEventAt = data.last_event_at;
  summary = data.summary;
  data.tables.forEach(render);
  renderSummary();
  renderBanner();
  renderCamera();
}

function renderCamera() {
  const el = document.getElementById("nocam");
  const age = lastEventAt == null ? null : nowServer() - lastEventAt;
  const stale = age == null || age > CAMERA_STALE_S;
  el.hidden = !stale || !document.getElementById("offline").hidden;
  el.textContent = age == null
    ? "Waiting for camera data… (table colors are not live yet)"
    : `No camera data for ${Math.floor(age / 60)} min. Check the camera box. Table colors may be out of date.`;
  document.body.classList.toggle("stale", stale || !document.getElementById("offline").hidden);
}

function setOnline(ok) {
  document.body.classList.toggle("stale", !ok);
  document.getElementById("offline").hidden = ok;
  const c = document.getElementById("conn");
  c.textContent = ok ? "Live" : "Offline";
  c.classList.toggle("ok", ok);
}

function connect() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { setOnline(true); loadAll().catch(() => setOnline(false)); };
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    clockOffset = msg.now - Date.now() / 1000;
    lastEventAt = msg.last_event_at;
    summary = msg.summary;
    render(msg.table);
    renderSummary();
    renderBanner();
    renderCamera();
  };
  es.onerror = () => setOnline(false); // EventSource reconnects by itself
}

async function main() {
  buildFloor(await (await fetch("/api/floor")).json());
  document.getElementById("sound").addEventListener("click", toggleSound);
  connect();
  setInterval(() => {
    Object.values(tiles).forEach((t) => t.table && renderTimer(t));
    renderBanner();
    renderCamera();
  }, 1000);
  // Full refresh every 30 s: picks up the camera's heartbeat and anything missed.
  setInterval(() => loadAll().catch(() => setOnline(false)), 30000);
  // iPad wakes from sleep: refresh everything.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadAll().catch(() => setOnline(false));
  });
}

main().catch(() => { setOnline(false); setTimeout(() => location.reload(), 5000); });
