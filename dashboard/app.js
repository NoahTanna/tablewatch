// TableWatch dashboard: floor map + live updates over Server-Sent Events.
const LABELS = { FREE: "FREE", OCCUPIED: "SEATED", NEEDS_CLEARING: "CLEAR" };
const floorEl = document.getElementById("floor");
const tiles = {};   // table id -> {el, table}
let clockOffset = 0; // server time - local time, in seconds
let lastEventAt = null; // server time of the camera's last report
const CAMERA_STALE_S = 120;

function nowServer() { return Date.now() / 1000 + clockOffset; }

function sizeFor(t) {
  // Size in vmin, from seat count and shape. Big enough to tap easily.
  const base = t.seats <= 2 ? 15 : t.seats <= 4 ? 17 : 17;
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
    el.innerHTML = `<div class="name"></div><div class="label"></div><div class="timer"></div>`;
    el.querySelector(".name").textContent = t.name;
    el.addEventListener("click", () => onTap(t.id));
    floorEl.appendChild(el);
    tiles[t.id] = { el, table: null };
  }
}

function render(table) {
  const tile = tiles[table.id];
  if (!tile) return;
  tile.table = table;
  tile.el.classList.remove("FREE", "OCCUPIED", "NEEDS_CLEARING");
  tile.el.classList.add(table.state);
  tile.el.querySelector(".label").textContent = LABELS[table.state];
  renderTimer(tile);
  renderCounts();
}

function renderTimer(tile) {
  const t = tile.table;
  const el = tile.el.querySelector(".timer");
  if (t.state !== "NEEDS_CLEARING" || t.unattended_since == null) { el.textContent = ""; return; }
  const secs = Math.max(0, Math.floor(nowServer() - t.unattended_since));
  el.textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

function renderCounts() {
  const n = { FREE: 0, OCCUPIED: 0, NEEDS_CLEARING: 0 };
  for (const id in tiles) if (tiles[id].table) n[tiles[id].table.state]++;
  document.getElementById("n-red").textContent = n.NEEDS_CLEARING;
  document.getElementById("n-gray").textContent = n.OCCUPIED;
  document.getElementById("n-green").textContent = n.FREE;
}

async function onTap(id) {
  const tile = tiles[id];
  if (!tile.table || tile.table.state !== "NEEDS_CLEARING") return;
  try {
    const r = await fetch(`/api/tables/${encodeURIComponent(id)}/clear`, { method: "POST" });
    if (r.ok) render(await r.json());
  } catch (e) { setOnline(false); }
}

async function loadAll() {
  const data = await (await fetch("/api/tables")).json();
  clockOffset = data.now - Date.now() / 1000;
  lastEventAt = data.last_event_at;
  data.tables.forEach(render);
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
    lastEventAt = msg.now;
    render(msg.table);
    renderCamera();
  };
  es.onerror = () => setOnline(false); // EventSource reconnects by itself
}

async function main() {
  buildFloor(await (await fetch("/api/floor")).json());
  connect();
  setInterval(() => { Object.values(tiles).forEach((t) => t.table && renderTimer(t)); renderCamera(); }, 1000);
  // Full refresh every 30 s: picks up the camera's heartbeat and anything missed.
  setInterval(() => loadAll().catch(() => setOnline(false)), 30000);
  // iPad wakes from sleep: refresh everything.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadAll().catch(() => setOnline(false));
  });
}

main().catch(() => { setOnline(false); setTimeout(() => location.reload(), 5000); });
