// Stand-in for the TableWatch server, for the browser-only demo (docs/demo.html).
// It answers the same /api calls the real dashboard makes, using the same rules as
// backend/state.py, and plays a sped-up dinner service. Built into the demo by
// tools/build_demo.py; never used by the real app.
(function () {
  const FLOOR = /*FLOOR_JSON*/ null;
  const CFG = { clearAfter: 20, notServed: 30, platesGone: 5, checkHint: 20, longStay: 100, minVisit: 15 };
  const SERVED_DELTA = 2, SET = 3;
  const now = () => Date.now() / 1000;
  const visits = [];
  const VISIT = () => ({ seated_at: null, served_at: null, baseline: null, peak: null, plates_gone_since: null, empty_before: null });
  const T = {};
  for (const f of FLOOR.tables) T[f.id] = { id: f.id, seats: f.seats || 4, state: "FREE", unattended_since: null, free_since: null, dish_count: SET, ...VISIT() };

  // ---- same rules as backend/state.py ----
  function observe(t, people, dishes, count) {
    const before = { ...t };
    t.dish_count = count;
    if (people) {
      if (t.state !== "OCCUPIED") Object.assign(t, VISIT(), { seated_at: now(), empty_before: t.free_since != null ? now() - t.free_since : null, free_since: null });
      t.state = "OCCUPIED"; t.unattended_since = null;
      if (t.baseline == null) t.baseline = t.peak = count;
      if (t.served_at == null && Math.abs(count - t.baseline) >= SERVED_DELTA) t.served_at = now();
      t.peak = Math.max(t.peak, count);
      const gone = t.served_at != null && count <= t.baseline && t.peak - count >= SERVED_DELTA;
      t.plates_gone_since = gone ? (t.plates_gone_since ?? now()) : null;
    } else if (dishes) {
      if (t.unattended_since == null && t.state === "OCCUPIED") t.unattended_since = now();
    } else toFree(t);
    tick(t); record(before, t);
  }
  function toFree(t) { if (t.state !== "FREE") t.free_since = now(); t.state = "FREE"; t.unattended_since = null; Object.assign(t, VISIT()); }
  function tick(t) { if (t.state !== "NEEDS_CLEARING" && t.unattended_since != null && now() - t.unattended_since >= CFG.clearAfter) t.state = "NEEDS_CLEARING"; }
  function record(old, t) {
    if (old.seated_at == null || t.seated_at === old.seated_at) return;
    const left = old.unattended_since ?? now();
    if (left - old.seated_at >= CFG.minVisit) visits.push({ stay: left - old.seated_at, first: old.served_at != null ? old.served_at - old.seated_at : null, empty: old.empty_before });
  }
  function longStayAfter() {
    if (visits.length < 5) return CFG.longStay;
    const s = visits.map((v) => v.stay).sort((a, b) => a - b);
    return 1.5 * s[Math.floor(s.length / 2)];
  }
  function view(t) {
    const n = now(); let stage = "FREE", alert = null; const hints = [];
    if (t.state === "NEEDS_CLEARING") { stage = "CLEAR"; alert = "clear"; }
    else if (t.state === "OCCUPIED" && t.unattended_since != null) stage = "LEFT";
    else if (t.state === "OCCUPIED") {
      if (t.served_at == null) { stage = "SEATED"; if (n - t.seated_at >= CFG.notServed) alert = "not_served"; }
      else if (t.plates_gone_since != null && n - t.plates_gone_since >= CFG.platesGone) { stage = "FINISHING"; if (n - t.plates_gone_since >= CFG.checkHint) hints.push("check"); }
      else stage = "SERVED";
      if (n - t.seated_at >= longStayAfter()) hints.push("long_stay");
    }
    return { ...t, stage, alert, hints };
  }
  function summary() {
    const seated = Object.values(T).filter((t) => t.state === "OCCUPIED" && t.unattended_since == null);
    const avg = (xs) => { xs = xs.filter((x) => x != null); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
    return { tables_in_use: seated.length, tables_total: FLOOR.tables.length,
      seats_in_use: seated.reduce((a, t) => a + t.seats, 0), seats_total: Object.values(T).reduce((a, t) => a + t.seats, 0),
      avg_first_service: avg(visits.map((v) => v.first)), avg_empty_between: avg(visits.map((v) => v.empty)), visits_tonight: visits.length };
  }

  // ---- a sped-up dinner service, same shape as simulator.py ----
  function meal() {
    const r = (a, b) => a + Math.random() * (b - a);
    const forgotten = Math.random() < 0.15, long = Math.random() < 0.1, neglected = Math.random() < 0.35;
    return [
      [false, true, SET, r(5, 20)],                                   // table set
      [true, true, SET, forgotten ? r(40, 50) : r(5, 15)],            // guests sat down
      [true, true, SET + 2, r(5, 10)],                                // drinks arrived
      [true, true, SET + 5, long ? r(110, 130) : r(25, 50)],          // food served
      [true, true, SET, r(5, 30)],                                    // plates cleared, still sitting
      [false, true, SET, neglected ? r(30, 45) : r(4, 10)],           // guests left, dishes remain
      [false, false, 0, r(4, 12)],                                    // bussed
    ];
  }
  const plan = {};
  for (const id in T) {
    const steps = meal(), start = Math.floor(Math.random() * 4);
    if (start >= 2) Object.assign(T[id], { state: "OCCUPIED", seated_at: now() - 10 - Math.random() * 30, served_at: now() - 5, baseline: SET, peak: SET + 5 });
    plan[id] = { steps: steps.slice(start), until: 0 };
  }
  function step() {
    const n = now();
    for (const id in T) {
      const p = plan[id];
      if (n >= p.until) {
        if (!p.steps.length) p.steps = meal();
        const [people, dishes, count, dur] = p.steps.shift();
        p.until = n + dur;
        observe(T[id], people, dishes, count);
      }
      tick(T[id]);
    }
    push();
  }

  // ---- the /api the dashboard talks to ----
  const listeners = new Set();
  const lastSent = {};
  function push(force) {
    const s = summary();
    for (const id in T) {
      const v = view(T[id]), key = JSON.stringify(v);
      if (!force && lastSent[id] === key) continue;
      lastSent[id] = key;
      const data = JSON.stringify({ now: now(), table: v, summary: s, last_event_at: now() });
      listeners.forEach((es) => es.onmessage && es.onmessage({ data }));
    }
  }
  const reply = (body) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  window.fetch = function (url, opts) {
    const path = String(url);
    if (path === "/api/floor") return reply(FLOOR);
    if (path === "/api/tables") return reply({ now: now(), last_event_at: now(), summary: summary(), tables: Object.values(T).map(view) });
    const m = path.match(/^\/api\/tables\/([^/]+)\/(clear|served)$/);
    if (m && opts && opts.method === "POST") {
      const t = T[decodeURIComponent(m[1])];
      if (m[2] === "clear") { const b = { ...t }; toFree(t); record(b, t); plan[t.id].steps = meal(); plan[t.id].until = now() + 4; }
      else if (t.state === "OCCUPIED" && t.served_at == null) t.served_at = now();
      setTimeout(push, 0);
      return reply(view(t));
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  };
  window.EventSource = class {
    constructor() { listeners.add(this); setTimeout(() => { this.onopen && this.onopen(); push(true); }, 50); }
    close() { listeners.delete(this); }
  };
  setInterval(step, 1000);
})();
