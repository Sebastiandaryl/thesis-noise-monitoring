/* Manila Noise Atlas: shared code for the public page (index.html) and the staff dashboard (admin.html). */
"use strict";

/* =====================================================================
   CONFIGURATION
   Everything the team is expected to edit lives in this block.
   ===================================================================== */
const CONFIG = {
  // "auto"      = live readings when server.py has recent data, otherwise simulated.
  // "simulated" = placeholder data generated in the browser.
  // "api"       = always poll the Raspberry Pi (see software/dashboard/server.py).
  DATA_MODE: "auto",
  API_URL: "/api/readings/latest",
  POLL_SECONDS: 5,
  FORECAST_HORIZON_MIN: 15,      // how far ahead predicted_db looks
  WHO_DAY_DB: 55,                // WHO guideline, daytime
  WHO_NIGHT_DB: 40,              // WHO guideline, night
  DAY_START_HOUR: 6,             // 06:00 to 22:00 counts as daytime
  NIGHT_START_HOUR: 22,
  ALERT_DB: 70,                  // warning alert when a site reaches this
  CRITICAL_DB: 85,               // critical alert
  OFFLINE_AFTER_SEC: 120,        // node shows offline after this long without data
  GPS_STALE_SEC: 300,            // without a GPS fix for this long, a node goes back to its saved location
  TIMEZONE: "Asia/Manila",
};

// PLACEHOLDER sensor sites around DLSU Manila. Replace lat/lng with the
// real deployment points once the nodes are installed. The id must match
// the site_id the Raspberry Pi sends.
const DEFAULT_SITES = [
  { id: "S01", name: "Taft Ave · DLSU Gate",        short: "Taft/DLSU",    setting: "Roadside",    profile: "roadside",    lat: 14.5647, lng: 120.9932, base: 72, mix: { vehicular: .62, commercial: .12, human: .14, ambient: .09, industrial: .03 } },
  { id: "S02", name: "Vito Cruz LRT Station",       short: "Vito Cruz",    setting: "Transit hub", profile: "roadside",    lat: 14.5633, lng: 120.9951, base: 74, mix: { vehicular: .58, commercial: .16, human: .16, ambient: .06, industrial: .04 } },
  { id: "S03", name: "San Andres Market",           short: "San Andres",   setting: "Market",      profile: "market",      lat: 14.5741, lng: 120.9967, base: 69, mix: { commercial: .48, human: .26, vehicular: .18, ambient: .06, industrial: .02 } },
  { id: "S04", name: "Rizal Memorial Complex",      short: "Rizal Mem.",   setting: "Public space",profile: "park",        lat: 14.5617, lng: 120.9914, base: 58, mix: { human: .46, ambient: .26, vehicular: .18, commercial: .08, industrial: .02 } },
  { id: "S05", name: "Manila Baywalk · Roxas Blvd", short: "Baywalk",      setting: "Public space",profile: "park",        lat: 14.5690, lng: 120.9826, base: 60, mix: { ambient: .38, vehicular: .30, human: .22, commercial: .08, industrial: .02 } },
  { id: "S06", name: "Pandacan Industrial Area",    short: "Pandacan",     setting: "Industrial",  profile: "industrial",  lat: 14.5893, lng: 121.0002, base: 71, mix: { industrial: .56, vehicular: .22, ambient: .12, human: .06, commercial: .04 } },
  { id: "S07", name: "Leveriza Residential, Malate",short: "Leveriza",     setting: "Residential", profile: "residential", lat: 14.5563, lng: 120.9968, base: 50, mix: { ambient: .44, human: .30, vehicular: .18, commercial: .06, industrial: .02 } },
  { id: "S08", name: "St. Scholastica's College",   short: "St. Scho",     setting: "School",      profile: "school",      lat: 14.5594, lng: 120.9978, base: 54, mix: { human: .50, vehicular: .24, ambient: .18, commercial: .06, industrial: .02 } },
  { id: "S09", name: "EDSA–Taft · Pasay Rotonda",   short: "EDSA–Taft",    setting: "Roadside",    profile: "roadside",    lat: 14.5376, lng: 121.0010, base: 77, mix: { vehicular: .70, commercial: .14, human: .10, industrial: .04, ambient: .02 } },
];

// Working copy of the sites. Admin edits (from server.py or demo mode) are
// merged in by applySiteOverrides(). status: active | maintenance | offline.
// location: "gps" follows the node's GPS when it has a fix, "fixed" always uses
// the saved coordinates. homeLat/homeLng keep the saved coordinates as the fallback.
let SITES = DEFAULT_SITES.map(s => ({ status: "active", note: "", location: "gps", ...s, homeLat: s.lat, homeLng: s.lng, mix: { ...s.mix } }));

// Presentation demo: open either page with ?demo to force sample data, ?demo=off to leave it.
// Scenarios (GPS lost, node offline, noise event) are stored per browser so a
// public tab and a staff tab stay in step during a defense.
const Demo = {
  get on() { return !!store("nma.demo"); },
  init() {
    const q = new URLSearchParams(location.search);
    if (q.has("demo")) store("nma.demo", q.get("demo") !== "off");
  },
  scenarios() { return store("nma.demo.scn") || {}; },
  set(siteId, patch) { const all = this.scenarios(); all[siteId] = { ...(all[siteId] || {}), ...patch }; store("nma.demo.scn", all); },
  reset() { store("nma.demo.scn", {}); },
};
const Hooks = { siteAdded() {}, siteMoved() {}, sitesChanged() {} };

// PLACEHOLDER classifier results. Replace with your evaluation numbers.
const MODEL_RESULTS = [
  { name: "Random Forest (current prototype)", accuracy: .842, precision: .836, recall: .829, f1: .832 },
  { name: "Baseline CNN",                      accuracy: .868, precision: .861, recall: .857, f1: .859 },
  { name: "Chaos-enhanced CNN",                accuracy: .912, precision: .907, recall: .903, f1: .905 },
];

/* =====================================================================
   CONSTANTS
   ===================================================================== */
const CATEGORIES = [
  { id: "vehicular",  label: "Vehicular",      color: "--cat-vehicular" },
  { id: "industrial", label: "Industrial",     color: "--cat-industrial" },
  { id: "human",      label: "Human activity", color: "--cat-human" },
  { id: "commercial", label: "Commercial",     color: "--cat-commercial" },
  { id: "ambient",    label: "Ambient",        color: "--cat-ambient" },
];
const CAT_BY_ID = Object.fromEntries(CATEGORIES.map(c => [c.id, c]));
const BANDS = [
  { max: 45,  label: "Quiet",     range: "< 45",  color: "#3a9d5d", text: "#0d2416" },
  { max: 55,  label: "Moderate",  range: "45–55", color: "#9cbf3b", text: "#1d2508" },
  { max: 65,  label: "Elevated",  range: "55–65", color: "#f0c02f", text: "#2b2003" },
  { max: 75,  label: "Loud",      range: "65–75", color: "#ee8a2a", text: "#2b1402" },
  { max: 85,  label: "Very loud", range: "75–85", color: "#d8412f", text: "#ffffff" },
  { max: 999, label: "Hazardous", range: "≥ 85",  color: "#8e1f5c", text: "#ffffff" },
];
const bandOf = db => BANDS.find(b => db < b.max) || BANDS[BANDS.length - 1];
const MIN = 60000;
const HISTORY_MIN = 1440;

/* =====================================================================
   HELPERS
   ===================================================================== */
const $ = id => document.getElementById(id);
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const round1 = v => (v == null || isNaN(v)) ? "--" : v.toFixed(1);
const minuteOf = ms => Math.floor(ms / MIN);
const fmtHM = new Intl.DateTimeFormat("en-GB", { timeZone: CONFIG.TIMEZONE, hour: "2-digit", minute: "2-digit", hour12: false });
const fmtHMS = new Intl.DateTimeFormat("en-GB", { timeZone: CONFIG.TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const fmtHour = new Intl.DateTimeFormat("en-GB", { timeZone: CONFIG.TIMEZONE, hour: "2-digit", hour12: false });
const manilaHour = ms => { const h = parseInt(fmtHour.format(ms), 10); return h === 24 ? 0 : h; };
const manilaFracHour = ms => { const d = new Date(ms); const [h, m] = fmtHM.format(d).split(":").map(Number); return (h % 24) + m / 60; };
const isDay = ms => { const h = manilaHour(ms); return h >= CONFIG.DAY_START_HOUR && h < CONFIG.NIGHT_START_HOUR; };
const limitAt = ms => isDay(ms) ? CONFIG.WHO_DAY_DB : CONFIG.WHO_NIGHT_DB;
// Energetic (logarithmic) average — the correct way to average decibels.
const leq = arr => { const v = arr.filter(x => x != null); if (!v.length) return null; return 10 * Math.log10(v.reduce((s, x) => s + Math.pow(10, x / 10), 0) / v.length); };
const pct = (arr, p) => { const v = arr.filter(x => x != null).sort((a, b) => a - b); if (!v.length) return null; return v[Math.min(v.length - 1, Math.floor((1 - p / 100) * v.length))]; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function store(key, val) { try { if (val === undefined) return JSON.parse(localStorage.getItem(key)); localStorage.setItem(key, JSON.stringify(val)); } catch (e) { return null; } }
function toast(text) { const t = $("toast"); t.textContent = text; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, 2200); }

function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const rand = mulberry32(20260928);
const gauss = () => { let u = 0, v = 0; while (!u) u = rand(); while (!v) v = rand(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };

/* =====================================================================
   DATA STORE
   history[siteId][minute] = { db, n, e, pred, cat }
   ===================================================================== */
const state = {
  history: {},           // per-site minute buckets
  latest: {},            // per-site latest normalized reading
  lastSeen: {},          // per-site ms of last reading
  gps: {},               // per-site { fix, ts, lat, lng } from the latest reading
  alerts: [],            // alert log
  selected: SITES[0].id,
  view: "measured",
  offset: 0,             // replay offset in minutes (0 = live)
  range: 60,
  filters: { cats: new Set(CATEGORIES.map(c => c.id)), minDb: 40, onlyOver: false },
  sort: { key: "now", dir: -1 },
  mode: CONFIG.DATA_MODE,
  sourceError: null,
};
SITES.forEach(s => { state.history[s.id] = {}; });

function bucket(siteId, minute) {
  const h = state.history[siteId] || (state.history[siteId] = {});
  return h[minute] || (h[minute] = { db: null, n: 0, e: 0, pred: null, cat: null });
}
function prune(nowMin) {
  const cutoff = nowMin - HISTORY_MIN - 5;
  for (const id in state.history) for (const k in state.history[id]) if (+k < cutoff) delete state.history[id][k];
}

// Normalize one raw reading from any source into the dashboard's shape.
function normalizeReading(raw) {
  const probs = raw.probabilities || raw.probs || {};
  let category = raw.category || raw.label || null;
  if (!category && Object.keys(probs).length) category = Object.entries(probs).sort((a, b) => b[1] - a[1])[0][0];
  const ts = raw.timestamp ? Date.parse(raw.timestamp) : Date.now();
  return {
    siteId: String(raw.site_id ?? raw.siteId ?? raw.id),
    ts: isNaN(ts) ? Date.now() : ts,
    db: raw.laeq_db != null ? +raw.laeq_db : (raw.db != null ? +raw.db : null),
    pred: raw.predicted_db != null ? +raw.predicted_db : null,
    category: category ? String(category).toLowerCase() : null,
    probs,
    lle: raw.lle != null ? +raw.lle : null,
    d2: raw.corr_dim != null ? +raw.corr_dim : null,
    df: raw.fractal_dim != null ? +raw.fractal_dim : null,
    lat: raw.lat != null && raw.lat !== "" && !isNaN(+raw.lat) ? +raw.lat : null,
    lng: raw.lng != null && raw.lng !== "" && !isNaN(+raw.lng) ? +raw.lng : null,
    gpsFix: raw.gps_fix != null ? !!raw.gps_fix : null,
    name: raw.name,
  };
}

function ingest(r) {
  if (!r.siteId) return;
  let site = SITES.find(s => s.id === r.siteId);
  const hasFix = r.lat != null && r.lng != null && r.gpsFix !== false;
  if (!site && hasFix) {
    site = { id: r.siteId, name: r.name || r.siteId, short: r.name || r.siteId, setting: "Sensor", profile: "roadside", lat: r.lat, lng: r.lng, homeLat: r.lat, homeLng: r.lng, location: "gps", base: 65, mix: {}, status: "active", note: "" };
    SITES.push(site); state.history[site.id] = {}; Hooks.siteAdded(site);
  }
  if (!site) return;
  if (hasFix) state.gps[site.id] = { fix: true, ts: r.ts, lat: r.lat, lng: r.lng };
  else if (r.gpsFix === false || state.gps[site.id]) state.gps[site.id] = { ...(state.gps[site.id] || {}), fix: false };
  placeSite(site);
  const m = minuteOf(r.ts);
  if (r.db != null) {
    const b = bucket(r.siteId, m);
    b.n += 1; b.e += Math.pow(10, r.db / 10); b.db = 10 * Math.log10(b.e / b.n);
    if (r.category) b.cat = r.category;
  }
  if (r.pred != null) bucket(r.siteId, m + CONFIG.FORECAST_HORIZON_MIN).pred = r.pred;
  state.latest[r.siteId] = r;
  state.lastSeen[r.siteId] = Date.now();
}

// Where a node is drawn: its GPS position while the fix is fresh, otherwise the saved location.
function gpsState(site) {
  if (site.location === "fixed") return { kind: "fixed", label: "Saved location (GPS not used)" };
  const g = state.gps[site.id];
  if (!g) return { kind: "none", label: "Saved location (no GPS data)" };
  const age = (Date.now() - (g.ts || 0)) / 1000;
  if (g.fix && age < CONFIG.GPS_STALE_SEC) return { kind: "gps", label: "GPS fix", lat: g.lat, lng: g.lng };
  return { kind: "lost", label: "Saved location (no GPS fix)" };
}
function placeSite(site) {
  const g = gpsState(site);
  const lat = g.kind === "gps" ? g.lat : site.homeLat ?? site.lat, lng = g.kind === "gps" ? g.lng : site.homeLng ?? site.lng;
  if (lat !== site.lat || lng !== site.lng) { site.lat = lat; site.lng = lng; Hooks.siteMoved(site); }
}

/* =====================================================================
   PLACEHOLDER SIMULATOR
   Diurnal traffic profile + a logistic-map chaotic term + random events.
   Only used while DATA_MODE is "simulated".
   ===================================================================== */
const PROFILES = {
  roadside:    [-12,-13,-14,-14,-11,-6,-1,3,4,2,0,0,1,0,0,1,3,4,3,1,-1,-4,-7,-10],
  market:      [-14,-14,-12,-8,-2,3,4,3,2,1,0,0,0,-1,-1,0,1,1,-1,-3,-6,-9,-12,-14],
  industrial:  [-10,-10,-10,-10,-10,-8,-3,1,2,2,2,1,0,2,2,2,1,-2,-6,-8,-9,-10,-10,-10],
  school:      [-14,-15,-15,-15,-13,-9,-2,4,1,0,0,2,3,1,0,3,4,1,-3,-6,-8,-10,-12,-13],
  residential: [-10,-11,-12,-12,-10,-6,-2,1,1,0,-1,-1,0,-1,-1,0,1,2,3,3,2,0,-4,-7],
  park:        [-12,-13,-14,-14,-12,-6,-2,0,-1,-2,-3,-3,-3,-3,-2,-1,1,4,5,5,3,0,-4,-8],
};
const Sim = {
  chaos: {}, smooth: {}, spike: {},
  profileAt(site, ms) { const p = PROFILES[site.profile] || PROFILES.roadside; const h = manilaFracHour(ms); const i = Math.floor(h) % 24, f = h - Math.floor(h); return p[i] * (1 - f) + p[(i + 1) % 24] * f; },
  step(site) {
    // Logistic map at r = 3.91 is deterministic chaos.
    let x = this.chaos[site.id] ?? (0.2 + rand() * 0.6);
    x = 3.91 * x * (1 - x); this.chaos[site.id] = x;
    const c = 0.55 * (this.smooth[site.id] || 0) + 0.45 * (x - 0.5) * 8;
    this.smooth[site.id] = c;
    return c;
  },
  sampleCat(site, ms) {
    const mix = { ...site.mix }; const h = manilaHour(ms);
    if (h < 5 || h >= 23) { mix.ambient = (mix.ambient || 0) + .35; }
    let r = rand() * Object.values(mix).reduce((a, b) => a + b, 0);
    for (const [k, v] of Object.entries(mix)) { r -= v; if (r <= 0) return k; }
    return "ambient";
  },
  level(site, ms, jitter = 1) {
    const base = site.base + this.profileAt(site, ms);
    const c = this.step(site);
    let spike = 0;
    if (rand() < 0.035) spike = 6 + rand() * 10; // horn, bus, shouting…
    return { base, c, db: clamp(base + c + spike + gauss() * 0.9 * jitter, 32, 108) };
  },
  probs(site, cat) {
    const p = {}; let sum = 0;
    CATEGORIES.forEach(k => { const v = Math.max(0.005, (site.mix[k.id] || .02) * (0.6 + rand() * 0.8) + (k.id === cat ? 0.35 : 0)); p[k.id] = v; sum += v; });
    CATEGORIES.forEach(k => p[k.id] = +(p[k.id] / sum).toFixed(3));
    return p;
  },
  chaosMetrics(site) {
    const hist = state.history[site.id]; const nowM = minuteOf(Date.now());
    const vals = []; for (let m = nowM - 30; m <= nowM; m++) if (hist[m]?.db != null) vals.push(hist[m].db);
    const sd = vals.length > 2 ? Math.sqrt(vals.reduce((s, v, i, a) => s + (v - a.reduce((x, y) => x + y) / a.length) ** 2, 0) / vals.length) : 2;
    const quiet = site.profile === "residential" ? -0.05 : 0;
    return {
      lle: +(0.012 + sd * 0.018 + quiet + gauss() * 0.006).toFixed(3),
      d2: +(1.9 + sd * 0.22 + rand() * 0.15).toFixed(2),
      df: +(1.28 + sd * 0.06 + rand() * 0.04).toFixed(2),
    };
  },
  seed() {
    const now = Date.now(); const nowM = minuteOf(now);
    SITES.forEach(site => {
      for (let m = nowM - HISTORY_MIN + 1; m <= nowM; m++) {
        const ms = m * MIN; const { base, c, db } = this.level(site, ms);
        const b = bucket(site.id, m); b.db = db; b.n = 1; b.e = Math.pow(10, db / 10); b.cat = this.sampleCat(site, ms);
        // prediction for this minute, made 15 minutes earlier
        b.pred = clamp(base + c * 0.55 + gauss() * 1.4, 32, 108);
      }
      for (let k = 1; k <= CONFIG.FORECAST_HORIZON_MIN; k++) {
        const ms = (nowM + k) * MIN; const base = site.base + this.profileAt(site, ms);
        bucket(site.id, nowM + k).pred = clamp(base + (this.smooth[site.id] || 0) * Math.pow(0.85, k) + gauss() * 0.8, 32, 108);
      }
      state.lastSeen[site.id] = now;
    });
  },
  readings() {
    const now = Date.now(); const scn = Demo.scenarios();
    // A node set offline in the demo stops sending, so it shows offline right away.
    SITES.forEach(site => { if (scn[site.id]?.offline && now - (state.lastSeen[site.id] || 0) < CONFIG.OFFLINE_AFTER_SEC * 1000) state.lastSeen[site.id] = now - CONFIG.OFFLINE_AFTER_SEC * 1000 - 1; });
    return SITES.filter(site => site.status === "active" && !scn[site.id]?.offline).map(site => {
      const sc = scn[site.id] || {};
      let { db } = this.level(site, now, 1.2);
      if (sc.eventUntil > now) db = clamp(86 + gauss() * 2, 80, 100);
      // GPS: a few metres of jitter around the saved point, like a real module.
      const home = [site.homeLat ?? site.lat, site.homeLng ?? site.lng];
      const gps = sc.gpsLost ? { gps_fix: false } : { gps_fix: true, lat: +(home[0] + gauss() * 0.00002).toFixed(6), lng: +(home[1] + gauss() * 0.00002).toFixed(6) };
      const cat = this.sampleCat(site, now);
      const futureMs = now + CONFIG.FORECAST_HORIZON_MIN * MIN;
      const pred = clamp(site.base + this.profileAt(site, futureMs) + (this.smooth[site.id] || 0) * 0.5 + gauss() * 1.2, 32, 108);
      return { site_id: site.id, timestamp: new Date(now).toISOString(), laeq_db: +db.toFixed(1), predicted_db: +pred.toFixed(1), category: cat, ...gps, probabilities: this.probs(site, cat), ...(() => { const c = this.chaosMetrics(site); return { lle: c.lle, corr_dim: c.d2, fractal_dim: c.df }; })() };
    });
  },
};

/* =====================================================================
   DATA SOURCE ADAPTER
   This is the single place where data enters the dashboard. In "api" mode
   it polls CONFIG.API_URL, which must return an array of readings (or
   { readings: [...] }) in the shape shown in the Data source drawer.
   ===================================================================== */
const DataSource = {
  async fetchLatest() {
    if (state.mode === "simulated") return Sim.readings();
    const res = await fetch(CONFIG.API_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`The endpoint answered ${res.status} ${res.statusText}.`);
    const body = await res.json();
    const list = Array.isArray(body) ? body : (body.readings || body.data || []);
    if (!Array.isArray(list)) throw new Error("The response is not a list of readings.");
    return list;
  },
  // Optional: GET <API_URL with "latest" replaced by "history"> returning the
  // last 24 h of readings, so charts are full right after a page load.
  async fetchHistory() {
    if (state.mode === "simulated") return [];
    const url = CONFIG.API_URL.replace(/latest\/?$/, "history");
    if (url === CONFIG.API_URL) return [];
    try { const r = await fetch(url, { cache: "no-store" }); if (!r.ok) return []; const b = await r.json(); return Array.isArray(b) ? b : (b.readings || []); } catch (e) { return []; }
  },
};

/* =====================================================================
   DERIVED VALUES
   ===================================================================== */
const liveMinute = () => minuteOf(Date.now());
const viewMinute = () => liveMinute() + state.offset;

function valueAt(siteId, minute, kind = "db") {
  const h = state.history[siteId]; if (!h) return null;
  for (let m = minute; m > minute - 3; m--) { const b = h[m]; if (b && b[kind] != null) return b[kind]; }
  return null;
}
function nowValue(siteId) {
  if (state.offset === 0 && state.view === "measured" && state.latest[siteId]?.db != null && Date.now() - state.latest[siteId].ts < 90000) return state.latest[siteId].db;
  return state.view === "predicted" ? valueAt(siteId, viewMinute() + CONFIG.FORECAST_HORIZON_MIN, "pred") : valueAt(siteId, viewMinute());
}
function windowVals(siteId, endMin, len, kind = "db") {
  const h = state.history[siteId] || {}; const out = [];
  for (let m = endMin - len + 1; m <= endMin; m++) out.push(h[m] ? h[m][kind] : null);
  return out;
}
function siteStats(site) {
  const end = viewMinute(); const hour = windowVals(site.id, end, 60);
  const cats = {}; const h = state.history[site.id] || {};
  for (let m = end - 59; m <= end; m++) { const c = h[m]?.cat; if (c) cats[c] = (cats[c] || 0) + 1; }
  const latest = state.latest[site.id];
  const topCat = (state.offset === 0 && latest?.category) || Object.entries(cats).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
  const seen = state.lastSeen[site.id];
  const online = seen != null && (Date.now() - seen) / 1000 < CONFIG.OFFLINE_AFTER_SEC;
  return {
    now: nowValue(site.id),
    measuredNow: state.offset === 0 && latest?.db != null ? latest.db : valueAt(site.id, end),
    pred: valueAt(site.id, end + CONFIG.FORECAST_HORIZON_MIN, "pred"),
    leq: leq(hour), max: Math.max(...hour.filter(v => v != null)), l10: pct(hour, 10), l90: pct(hour, 90),
    hour, cats, topCat, online,
    lle: latest?.lle, d2: latest?.d2, df: latest?.df,
    status: site.status || "active",
  };
}
function passesFilter(site, st) {
  const f = state.filters;
  if (st.topCat && !f.cats.has(st.topCat)) return false;
  if (st.now != null && st.now < f.minDb) return false;
  if (f.onlyOver && !(st.now != null && st.now > limitAt(viewMinute() * MIN))) return false;
  return true;
}

/* =====================================================================
   ALERTS
   ===================================================================== */
function evaluateAlerts(minute, silent) {
  const ms = minute * MIN;
  SITES.forEach(site => {
    const db = valueAt(site.id, minute);
    const pred = valueAt(site.id, minute + CONFIG.FORECAST_HORIZON_MIN, "pred");
    const conds = {
      crit: db != null && db >= CONFIG.CRITICAL_DB,
      warn: db != null && db >= CONFIG.ALERT_DB && db < CONFIG.CRITICAL_DB,
      info: db != null && db < CONFIG.ALERT_DB && pred != null && pred >= CONFIG.ALERT_DB,
    };
    conds.offline = site.status === "active" && !siteStats(site).online;
    for (const [type, on] of Object.entries(conds)) {
      const active = state.alerts.find(a => a.site === site.id && a.type === type && !a.end);
      if (on && !active) state.alerts.unshift({ id: `${site.id}-${type}-${minute}`, site: site.id, type, start: ms, end: null, peak: type === "info" ? pred : db, ack: silent && minute < liveMinute() - 30 });
      else if (on && active) active.peak = Math.max(active.peak ?? 0, type === "info" ? pred : db);
      else if (!on && active) active.end = ms;
    }
  });
  state.alerts = state.alerts.slice(0, 120);
}


/* =====================================================================
   BACKEND: login, notices, site management, activity log
   Talks to server.py when the page is served by it. Opened any other way
   (double-clicked file, preview), it falls back to a demo backend that
   keeps everything in this browser only.
   ===================================================================== */
const DEMO_USERS = {
  admin:   { password: "admin123",   role: "admin",   name: "Demo Admin" },
  planner: { password: "planner123", role: "planner", name: "Demo City Planner" },
};
const ROLE_LABEL = { admin: "Administrator", planner: "Government planner" };

const Backend = {
  mode: null, // "server" | "demo"
  async detect() {
    if (this.mode) return this.mode;
    if (location.protocol === "file:") return (this.mode = "demo");
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      const b = r.ok ? await r.json() : null;
      this.mode = b && b.service === "noise-atlas" ? "server" : "demo";
    } catch (e) { this.mode = "demo"; }
    return this.mode;
  },
  async req(method, url, body) {
    const r = await fetch(url, {
      method, credentials: "same-origin", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null; try { data = await r.json(); } catch (e) { /* empty body */ }
    if (!r.ok) throw new Error(data?.error || `The server answered ${r.status}.`);
    return data;
  },
  // ---- demo storage ----
  dGet(k, d) { const v = store("nma.demo." + k); return v == null ? d : v; },
  dSet(k, v) { store("nma.demo." + k, v); },
  dSession() { try { return JSON.parse(sessionStorage.getItem("nma.demo.session")); } catch (e) { return null; } },
  dLog(action, detail) {
    const log = this.dGet("log", []);
    log.unshift({ ts: new Date().toISOString(), user: this.dSession()?.username || "system", action, detail });
    this.dSet("log", log.slice(0, 300));
  },
  dRequire(role) {
    const u = this.dSession();
    if (!u) throw new Error("Please log in again.");
    if (role === "admin" && u.role !== "admin") throw new Error("Only administrators can do this.");
    return u;
  },

  // ---- auth ----
  async me() {
    if (await this.detect() === "server") { try { return await this.req("GET", "/api/me"); } catch (e) { return null; } }
    return this.dSession();
  },
  async login(username, password) {
    if (await this.detect() === "server") return this.req("POST", "/api/login", { username, password });
    const u = DEMO_USERS[String(username).trim().toLowerCase()];
    if (!u || u.password !== password) throw new Error("Wrong username or password.");
    const user = { username: String(username).trim().toLowerCase(), role: u.role, name: u.name };
    try { sessionStorage.setItem("nma.demo.session", JSON.stringify(user)); } catch (e) { /* private mode */ }
    this.dLog("login", `${user.name} logged in`);
    return user;
  },
  async logout() {
    if (await this.detect() === "server") { try { await this.req("POST", "/api/logout"); } catch (e) { /* already out */ } return; }
    this.dLog("logout", "Logged out");
    try { sessionStorage.removeItem("nma.demo.session"); } catch (e) { /* ignore */ }
  },

  // ---- notices ----
  async notices() {
    if (await this.detect() === "server") { try { return await this.req("GET", "/api/notices"); } catch (e) { return []; } }
    const now = Date.now();
    return this.dGet("notices", []).filter(n => !n.expires || Date.parse(n.expires) > now);
  },
  async addNotice(n) {
    if (await this.detect() === "server") return this.req("POST", "/api/notices", n);
    const u = this.dRequire("admin");
    const notice = { ...n, id: `N${Date.now().toString(36)}`, created: new Date().toISOString(), author: u.name };
    this.dSet("notices", [notice, ...this.dGet("notices", [])]);
    this.dLog("notice.add", `Posted notice "${n.title}"`);
    return notice;
  },
  async removeNotice(id) {
    if (await this.detect() === "server") return this.req("DELETE", `/api/notices/${encodeURIComponent(id)}`);
    this.dRequire("admin");
    const all = this.dGet("notices", []); const n = all.find(x => x.id === id);
    this.dSet("notices", all.filter(x => x.id !== id));
    this.dLog("notice.remove", `Removed notice "${n?.title || id}"`);
  },

  // ---- sites ----
  async siteOverrides() {
    if (await this.detect() === "server") { try { return await this.req("GET", "/api/sites"); } catch (e) { return []; } }
    return this.dGet("sites", []);
  },
  async saveSite(site) {
    const clean = { id: site.id, name: site.name, short: site.short, setting: site.setting, lat: +site.lat, lng: +site.lng, status: site.status, note: site.note || "", location: site.location === "fixed" ? "fixed" : "gps" };
    if (await this.detect() === "server") return this.req("PUT", `/api/sites/${encodeURIComponent(site.id)}`, clean);
    this.dRequire("admin");
    const all = this.dGet("sites", []).filter(x => x.id !== site.id);
    this.dSet("sites", [...all, clean]);
    this.dLog("site.save", `Updated ${clean.id} (${clean.name}): ${clean.status}${clean.note ? ` · ${clean.note}` : ""}`);
    return clean;
  },
  async removeSite(id) {
    if (await this.detect() === "server") return this.req("DELETE", `/api/sites/${encodeURIComponent(id)}`);
    this.dRequire("admin");
    const all = this.dGet("sites", []).filter(x => x.id !== id);
    this.dSet("sites", [...all, { id, removed: true }]);
    this.dLog("site.remove", `Removed site ${id}`);
  },

  // ---- activity log ----
  async log() {
    if (await this.detect() === "server") { try { return await this.req("GET", "/api/log"); } catch (e) { return []; } }
    return this.dGet("log", []);
  },
};

const SETTING_PROFILE = { "Roadside": "roadside", "Transit hub": "roadside", "Market": "market", "Industrial": "industrial", "School": "school", "Residential": "residential", "Public space": "park" };
const PROFILE_BASE = { roadside: 72, market: 68, industrial: 70, school: 60, residential: 55, park: 62 };

function applySiteOverrides(list) {
  (list || []).forEach(o => {
    if (!o || !o.id) return;
    const i = SITES.findIndex(s => s.id === o.id);
    if (o.removed) { if (i >= 0) SITES.splice(i, 1); return; }
    const fields = {};
    ["name", "short", "setting", "status", "note", "location"].forEach(k => { if (o[k] != null && o[k] !== "") fields[k] = o[k]; });
    if (o.note === "") fields.note = "";
    if (o.lat != null && !isNaN(+o.lat)) fields.lat = +o.lat;
    if (o.lng != null && !isNaN(+o.lng)) fields.lng = +o.lng;
    if (fields.lat != null) fields.homeLat = fields.lat;
    if (fields.lng != null) fields.homeLng = fields.lng;
    if (i >= 0) { Object.assign(SITES[i], fields); placeSite(SITES[i]); }
    else if (fields.lat != null && fields.lng != null) {
      const profile = SETTING_PROFILE[fields.setting] || "roadside";
      SITES.push({ id: o.id, name: fields.name || o.id, short: fields.short || fields.name || o.id, setting: fields.setting || "Roadside", profile, base: PROFILE_BASE[profile], mix: { vehicular: .4, human: .2, commercial: .15, ambient: .2, industrial: .05 }, status: "active", note: "", location: "gps", ...fields });
      state.history[o.id] = state.history[o.id] || {};
    }
  });
  if (!SITES.some(s => s.id === state.selected) && SITES[0]) state.selected = SITES[0].id;
  Hooks.sitesChanged();
}

// Decide simulated vs live. "auto" goes live only when server.py has fresh readings.
async function resolveMode() {
  if (Demo.on) return "simulated";
  const saved = store("nma.cfg");
  if (saved) { CONFIG.API_URL = saved.url || CONFIG.API_URL; CONFIG.POLL_SECONDS = saved.poll || CONFIG.POLL_SECONDS; }
  const mode = saved?.mode || CONFIG.DATA_MODE;
  if (mode !== "auto") return mode;
  if (await Backend.detect() !== "server") return "simulated";
  try {
    const r = await fetch(CONFIG.API_URL, { cache: "no-store" });
    const list = r.ok ? await r.json() : [];
    const fresh = (Array.isArray(list) ? list : []).some(x => Date.now() - Date.parse(x.timestamp) < 10 * MIN);
    return fresh ? "api" : "simulated";
  } catch (e) { return "simulated"; }
}

/* =====================================================================
   PLAIN-LANGUAGE AND PLANNING METRICS
   ===================================================================== */
const SOURCE_WORDS = { vehicular: "Traffic", industrial: "Industry and machinery", human: "People and crowds", commercial: "Shops and business", ambient: "Background city hum" };

// Everyday comparisons for a dB value.
function dbComparison(db) {
  if (db == null) return "";
  if (db < 40) return "as quiet as a library";
  if (db < 50) return "like a quiet residential street";
  if (db < 60) return "like normal conversation";
  if (db < 70) return "like a busy office or restaurant";
  if (db < 80) return "like heavy city traffic";
  if (db < 90) return "like a passing truck or bus";
  return "like a motorcycle up close";
}

// Hour-of-day LAeq (Manila time) over the last 24 hours: array of 24.
function hourOfDayLevels(siteId) {
  const h = state.history[siteId] || {}; const nowM = liveMinute(); const buckets = Array.from({ length: 24 }, () => []);
  for (let m = nowM - HISTORY_MIN + 1; m <= nowM; m++) { const b = h[m]; if (b?.db != null) buckets[manilaHour(m * MIN)].push(b.db); }
  return buckets.map(leq);
}

// Day 07-19, evening 19-23, night 23-07 (EU END definition) and Lden.
function periodLevels(siteId) {
  const h = state.history[siteId] || {}; const nowM = liveMinute();
  const day = [], eve = [], night = [], whoDay = [], whoNight = [];
  let overDay = 0, overNight = 0;
  for (let m = nowM - HISTORY_MIN + 1; m <= nowM; m++) {
    const v = h[m]?.db; if (v == null) continue;
    const hr = manilaHour(m * MIN);
    (hr >= 7 && hr < 19 ? day : hr >= 19 && hr < 23 ? eve : night).push(v);
    if (isDay(m * MIN)) { whoDay.push(v); if (v > CONFIG.WHO_DAY_DB) overDay++; }
    else { whoNight.push(v); if (v > CONFIG.WHO_NIGHT_DB) overNight++; }
  }
  const Ld = leq(day), Le = leq(eve), Ln = leq(night);
  let Lden = null;
  if (Ld != null && Le != null && Ln != null) Lden = 10 * Math.log10((12 * Math.pow(10, Ld / 10) + 4 * Math.pow(10, (Le + 5) / 10) + 8 * Math.pow(10, (Ln + 10) / 10)) / 24);
  return {
    Ld, Le, Ln, Lden,
    whoDay: leq(whoDay), whoNight: leq(whoNight),
    overDayPct: whoDay.length ? 100 * overDay / whoDay.length : null,
    overNightPct: whoNight.length ? 100 * overNight / whoNight.length : null,
    coverage: (day.length + eve.length + night.length) / HISTORY_MIN,
  };
}

// Livability grade from Lden, in bands a resident can read at a glance.
const GRADES = [
  { max: 55,  letter: "A", label: "Quiet",        advice: "Comfortable for living, sleeping and studying.", color: "#3a9d5d", text: "#0d2416" },
  { max: 60,  letter: "B", label: "Fairly quiet", advice: "Generally fine for living. Some traffic noise at peak hours.", color: "#9cbf3b", text: "#1d2508" },
  { max: 65,  letter: "C", label: "Moderate",     advice: "Noticeable noise. Choose rooms facing away from the road.", color: "#f0c02f", text: "#2b2003" },
  { max: 70,  letter: "D", label: "Noisy",        advice: "Frequent loud periods. Sound insulation is recommended for homes.", color: "#ee8a2a", text: "#2b1402" },
  { max: 999, letter: "E", label: "Very noisy",   advice: "Long-term exposure may affect sleep and health. Not ideal for homes.", color: "#d8412f", text: "#ffffff" },
];
const gradeOf = lden => lden == null ? null : GRADES.find(g => lden < g.max);

// Continuous runs of hours, e.g. [1,2,3] -> "01:00–04:00".
function hourRanges(hours) {
  const sorted = [...hours].sort((a, b) => a - b); const out = []; let start = null, prev = null;
  sorted.forEach(h => { if (start == null) { start = prev = h; } else if (h === prev + 1) prev = h; else { out.push([start, prev]); start = prev = h; } });
  if (start != null) out.push([start, prev]);
  const f = h => `${String(h % 24).padStart(2, "0")}:00`;
  return out.map(([a, b]) => `${f(a)}–${f(b + 1)}`);
}

/* =====================================================================
   SHARED MAP
   ===================================================================== */
// "streets" (CARTO Voyager) looks closest to Google Maps; "hybrid" is satellite with street names on top.
const TILE_SETS = {
  streets: { url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", attr: "© OpenStreetMap contributors © CARTO", max: 20 },
  hybrid: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr: "Imagery © Esri · © OpenStreetMap contributors © CARTO", max: 19,
            labels: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png" },
  osm:   { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attr: "© OpenStreetMap contributors", max: 19 },
  light: { url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", attr: "© OpenStreetMap contributors © CARTO", max: 20 },
  dark:  { url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attr: "© OpenStreetMap contributors © CARTO", max: 20 },
  sat:   { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr: "Imagery © Esri", max: 19 },
};
const prefersDark = () => document.documentElement.dataset.theme === "dark" || (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);

function createNoiseMap(elId, opts = {}) {
  const map = L.map(elId, { zoomControl: true, minZoom: 4, worldCopyJump: true }).setView([14.566, 120.994], 14);
  L.control.scale({ metric: true, imperial: false, position: "bottomright" }).addTo(map);
  map.createPane("schematic"); map.getPane("schematic").style.zIndex = 250;
  const schematic = L.layerGroup();
  const markers = {};
  const markerLayer = L.layerGroup().addTo(map);
  const zoneLayer = L.layerGroup().addTo(map);
  const heatLayer = L.heatLayer([], {
    radius: 42, blur: 30, maxZoom: 17, max: 1, minOpacity: 0.3,
    gradient: { 0.0: "#3a9d5d", 0.35: "#9cbf3b", 0.5: "#f0c02f", 0.65: "#ee8a2a", 0.8: "#d8412f", 1.0: "#8e1f5c" },
  }).addTo(map);
  let tileLayer = null, failed = false, current = "auto";

  // Offline basemap: the whole Philippines from assets/ph-basemap.js (land and city
  // names), plus a street sketch of the DLSU study area when zoomed in close.
  const sketchCanvas = L.canvas({ padding: 0.5, pane: "schematic" });
  let detailLayer = null, cityTiers = [];
  function showSketchDetail() {
    if (!map.hasLayer(schematic)) return;
    const z = map.getZoom();
    cityTiers.forEach(t => { if (z >= t.minZoom) schematic.addLayer(t.layer); else schematic.removeLayer(t.layer); });
    if (detailLayer) { if (z >= 12) schematic.addLayer(detailLayer); else schematic.removeLayer(detailLayer); }
  }
  map.on("zoomend", showSketchDetail);
  function buildSchematic() {
    schematic.clearLayers();
    const river = cssVar("--map-river"), road = cssVar("--map-road"), major = cssVar("--map-road-major");
    const casing = cssVar("--map-casing"), majorCasing = cssVar("--map-road-major-casing"), park = cssVar("--map-park");
    const o = { pane: "schematic", interactive: false };
    const label = (layer, ll, text, style) => L.marker(ll, { pane: "schematic", interactive: false, keyboard: false, icon: L.divIcon({ className: "", html: `<span style="${style};white-space:nowrap">${text}</span>`, iconSize: [0, 0] }) }).addTo(layer);
    if (typeof PH_BASEMAP !== "undefined") {
      const ph = cssVar("--map-land"), other = cssVar("--map-land-other"), coast = cssVar("--map-coast");
      PH_BASEMAP.land.forEach(p => L.polygon(p.r, { ...o, renderer: sketchCanvas, fillColor: p.c ? ph : other, fillOpacity: 1, color: coast, weight: 0.8, smoothFactor: 1.5 }).addTo(schematic));
      // Bigger cities appear first as you zoom in.
      // The capital and regional centers show from zoom 5, other big cities from 8, the rest from 10.
      const tierOf = c => c[4] ? 0 : c[3] >= 2e5 ? 1 : 2;
      cityTiers = [5, 8, 10].map((minZoom, i) => {
        const layer = L.layerGroup();
        PH_BASEMAP.cities.filter(c => tierOf(c) === i).forEach(c => {
          label(layer, [c[1], c[2]], `<i style="display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--map-city);margin-right:4px;vertical-align:1px"></i>${esc(c[0])}`,
            `font:${c[4] === 1 ? 700 : 600} ${c[4] ? 12 : 11}px var(--font-body);color:var(--map-city);text-shadow:0 0 3px var(--map-land),0 0 3px var(--map-land);transform:translate(-3px,-8px);display:inline-block`);
        });
        return { minZoom, layer };
      });
      label(schematic, [13.2, 118.6], "West Philippine Sea", "font:italic 600 12px var(--font-body);color:var(--map-water-ink);letter-spacing:.06em");
      label(schematic, [12.5, 127.6], "Philippine Sea", "font:italic 600 12px var(--font-body);color:var(--map-water-ink);letter-spacing:.06em");
      label(schematic, [14.53, 120.80], "Manila Bay", "font:italic 600 11px var(--font-body);color:var(--map-water-ink)");
    }
    // Approximate streets around the study area, shown from zoom 12.
    detailLayer = L.layerGroup();
    L.polyline([[14.5962, 120.958], [14.5955, 120.974], [14.596, 120.980], [14.595, 120.988], [14.5975, 120.996], [14.593, 121.005], [14.585, 121.012], [14.578, 121.020], [14.570, 121.033], [14.566, 121.045]], { ...o, color: river, weight: 9, opacity: 1 }).addTo(detailLayer);
    // Parks and open spaces (approximate): Rizal Park, Manila Zoo, Rizal Memorial, Paco Park.
    [
      [[14.5850, 120.9745], [14.5850, 120.9830], [14.5800, 120.9835], [14.5795, 120.9760]],
      [[14.5675, 120.9870], [14.5672, 120.9905], [14.5635, 120.9907], [14.5638, 120.9872]],
      [[14.5640, 120.9900], [14.5640, 120.9945], [14.5595, 120.9948], [14.5592, 120.9905]],
      [[14.5825, 120.9888], [14.5825, 120.9908], [14.5808, 120.9908], [14.5808, 120.9888]],
    ].forEach(poly => L.polygon(poly, { ...o, stroke: false, fillColor: park, fillOpacity: 1 }).addTo(detailLayer));
    const roads = [
      { n: "Taft Ave", w: 5, c: major, p: [[14.5935, 120.9815], [14.5830, 120.9858], [14.5760, 120.9895], [14.5647, 120.9937], [14.5560, 120.9975], [14.5460, 121.0002], [14.5376, 121.0012], [14.5280, 121.0000]] },
      { n: "Roxas Blvd", w: 5, c: major, p: [[14.5840, 120.9770], [14.5760, 120.9790], [14.5680, 120.9820], [14.5560, 120.9855], [14.5450, 120.9885], [14.5330, 120.9895], [14.5200, 120.9905]] },
      { n: "EDSA", w: 5, c: major, p: [[14.5370, 120.9910], [14.5376, 121.0012], [14.5395, 121.0105], [14.5410, 121.0190], [14.5500, 121.0300], [14.5600, 121.0400]] },
      { n: "Quirino Ave", w: 3, c: road, p: [[14.5700, 120.9840], [14.5720, 120.9920], [14.5760, 121.0000], [14.5820, 121.0080]] },
      { n: "Vito Cruz", w: 3, c: road, p: [[14.5660, 120.9825], [14.5640, 120.9935], [14.5620, 121.0040], [14.5600, 121.0150]] },
      { n: "Osmeña Hwy", w: 4, c: road, p: [[14.5820, 121.0000], [14.5700, 121.0030], [14.5560, 121.0080], [14.5400, 121.0150]] },
      { n: "Pres. Quirino", w: 3, c: road, p: [[14.5530, 120.9860], [14.5540, 120.9960], [14.5520, 121.0060]] },
    ];
    roads.forEach(r => {
      L.polyline(r.p, { ...o, color: r.c === road ? casing : majorCasing, weight: r.w + 2, opacity: 1 }).addTo(detailLayer);
      L.polyline(r.p, { ...o, color: r.c, weight: r.w, opacity: 1 }).addTo(detailLayer);
      label(detailLayer, r.p[Math.floor(r.p.length / 2)], r.n, "font:600 10px var(--font-body);color:var(--muted);text-shadow:0 0 3px var(--map-land)");
    });
    label(detailLayer, [14.5828, 120.9765], "Rizal Park", "font:600 10px var(--font-body);color:var(--map-park-ink)");
    label(detailLayer, [14.5660, 120.9874], "Manila Zoo", "font:600 10px var(--font-body);color:var(--map-park-ink)");
  }

  let labelLayer = null;
  function setBasemap(key = current) {
    current = key;
    let k = failed ? "schematic" : key;
    if (k === "auto") k = prefersDark() ? "dark" : "streets";
    if (tileLayer) { map.removeLayer(tileLayer); tileLayer = null; }
    if (labelLayer) { map.removeLayer(labelLayer); labelLayer = null; }
    typeControl && typeControl.sync(k);
    buildSchematic();
    map.getContainer().classList.toggle("sketch", k === "schematic");
    if (k === "schematic") { schematic.addTo(map); showSketchDetail(); return; }
    map.removeLayer(schematic);
    const t = TILE_SETS[k]; let loaded = 0, errors = 0;
    tileLayer = L.tileLayer(t.url, { attribution: t.attr, maxZoom: t.max, subdomains: "abcd", crossOrigin: true });
    tileLayer.on("tileload", () => loaded++);
    tileLayer.on("tileerror", () => {
      errors++;
      if (errors >= 4 && loaded === 0 && !failed) {
        failed = true;
        if (opts.noticeEl) { opts.noticeEl.hidden = false; opts.noticeEl.textContent = "No internet map here, so this is the built-in offline map of the Philippines. Street maps and satellite load on a normal internet connection."; }
        setBasemap();
      }
    });
    tileLayer.addTo(map);
    if (t.labels) labelLayer = L.tileLayer(t.labels, { maxZoom: t.max, subdomains: "abcd", crossOrigin: true }).addTo(map);
  }

  // Google-style "Map | Satellite" switch in the corner of the map.
  let typeControl = null;
  if (opts.typeControl !== false) {
    const Ctl = L.Control.extend({
      onAdd() {
        const box = L.DomUtil.create("div", "map-type");
        box.innerHTML = `<button type="button" data-k="auto">Map</button><button type="button" data-k="hybrid">Satellite</button>`;
        L.DomEvent.disableClickPropagation(box);
        box.addEventListener("click", e => {
          const b = e.target.closest("[data-k]"); if (!b) return;
          resetFailure(); setBasemap(b.dataset.k); opts.onBasemap && opts.onBasemap(b.dataset.k);
        });
        return box;
      },
    });
    typeControl = new Ctl({ position: "bottomleft" }); typeControl.addTo(map);
    typeControl.sync = k => typeControl.getContainer().querySelectorAll("[data-k]").forEach(b => b.setAttribute("aria-pressed", b.dataset.k === "hybrid" ? k === "hybrid" || k === "sat" : !(k === "hybrid" || k === "sat")));
  }

  // Staff tools: drag pins to move nodes, or click the map to pick a point.
  let dragHandler = null;
  function setDraggable(on, onMove) {
    dragHandler = on ? onMove : null;
    Object.values(markers).forEach(mk => { if (mk.dragging) on ? mk.dragging.enable() : mk.dragging.disable(); });
    map.getContainer().classList.toggle("moving", on);
  }
  function pickPoint(cb) {
    map.getContainer().classList.add("picking");
    const done = e => { map.getContainer().classList.remove("picking"); cb(e ? e.latlng : null); document.removeEventListener("keydown", esc); };
    const esc = e => { if (e.key === "Escape") { map.off("click", done); done(null); } };
    document.addEventListener("keydown", esc);
    map.once("click", done);
  }
  function resetFailure() { failed = false; if (opts.noticeEl) opts.noticeEl.hidden = true; }

  function ensureMarker(site) {
    if (markers[site.id]) { markers[site.id].setLatLng([site.lat, site.lng]); return markers[site.id]; }
    const icon = L.divIcon({ className: "site-pin", html: `<div class="pin"><span>--</span></div>`, iconSize: [40, 40], iconAnchor: [20, 20] });
    const mk = L.marker([site.lat, site.lng], { icon, keyboard: true, title: site.name, riseOnHover: true });
    mk.bindTooltip("", { className: "site-tip", direction: "top", offset: [0, -16] });
    mk.on("click", () => opts.onSelect && opts.onSelect(site.id));
    markers[site.id] = mk;
    mk.on("add", () => { if (dragHandler && mk.dragging) mk.dragging.enable(); });
    mk.on("dragend", () => dragHandler && dragHandler(site.id, mk.getLatLng()));
    return mk;
  }
  function syncMarkers() {
    Object.keys(markers).forEach(id => { if (!SITES.some(s => s.id === id)) { markerLayer.removeLayer(markers[id]); delete markers[id]; } });
    SITES.forEach(ensureMarker);
  }
  // Paint one pin. v = dB value or null.
  function paintPin(site, v, { selected = false, alarm = false, pred = false, muted = false } = {}) {
    const el = markers[site.id]?.getElement(); if (!el) return;
    const pin = el.querySelector(".pin"); const b = v != null && !muted ? bandOf(v) : null;
    pin.style.background = b ? b.color : "var(--muted)";
    pin.style.color = b ? b.text : "var(--surface)";
    pin.style.setProperty("--s", `${Math.round(clamp(26 + ((v ?? 50) - 45) * 0.45, 26, 40))}px`);
    pin.classList.toggle("sel", selected);
    pin.classList.toggle("alarm", alarm && !muted);
    pin.classList.toggle("pred", pred);
    pin.classList.toggle("muted", muted);
    pin.querySelector("span").textContent = muted ? "—" : v != null ? Math.round(v) : "--";
  }
  function fit() { if (SITES.length) map.fitBounds(L.latLngBounds(SITES.map(s => [s.lat, s.lng])).pad(0.12), { maxZoom: 15 }); }
  const PH_BOUNDS = L.latLngBounds([4.4, 116.8], [21.2, 126.8]);
  function fitCountry() { map.fitBounds(PH_BOUNDS); }

  // "Whole Philippines" and "All nodes" buttons under the zoom control.
  const ViewCtl = L.Control.extend({
    onAdd() {
      const box = L.DomUtil.create("div", "leaflet-bar map-views");
      box.innerHTML = `<a href="#" role="button" data-v="ph" title="Show the whole Philippines" aria-label="Show the whole Philippines"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="10" r="7.5"/><path d="M2.5 10h15M10 2.5c2.2 2.2 2.2 12.8 0 15M10 2.5c-2.2 2.2-2.2 12.8 0 15"/></svg></a><a href="#" role="button" data-v="nodes" title="Zoom to all nodes" aria-label="Zoom to all nodes"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4"/><circle cx="10" cy="10" r="2.2" fill="currentColor"/></svg></a>`;
        L.DomEvent.disableClickPropagation(box);
        box.addEventListener("click", e => { const a = e.target.closest("[data-v]"); if (!a) return; e.preventDefault(); a.dataset.v === "ph" ? fitCountry() : fit(); });
        return box;
      },
    });
  new ViewCtl({ position: "topleft" }).addTo(map);
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById(elId));
  return { map, markers, markerLayer, zoneLayer, heatLayer, setBasemap, resetFailure, ensureMarker, syncMarkers, paintPin, fit, setDraggable, pickPoint, fitCountry };
}

function onThemeChange(fn) {
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);
  new MutationObserver(fn).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

/* =====================================================================
   POLLING LOOP
   Pages set Loop.render to redraw after each new batch of readings.
   ===================================================================== */
const Loop = { render() {}, timer: null };
async function tick() {
  try {
    const raw = await DataSource.fetchLatest();
    raw.map(normalizeReading).forEach(ingest);
    state.sourceError = null;
  } catch (e) {
    state.sourceError = `Could not reach the prototype at ${CONFIG.API_URL}: ${e.message || e}`;
  }
  if (state.mode === "simulated") {
    const nowM = liveMinute();
    SITES.forEach(site => { const b = bucket(site.id, nowM + CONFIG.FORECAST_HORIZON_MIN); if (b.pred == null) b.pred = state.latest[site.id]?.pred ?? null; });
  }
  evaluateAlerts(liveMinute(), false);
  prune(liveMinute());
  Loop.render();
}
async function switchMode(mode) {
  clearInterval(Loop.timer);
  state.mode = mode; state.alerts = []; state.latest = {}; state.lastSeen = {}; state.gps = {};
  SITES.forEach(s => state.history[s.id] = {});
  if (mode === "simulated") { Sim.seed(); for (let m = liveMinute() - 180; m < liveMinute(); m++) evaluateAlerts(m, true); }
  else { (await DataSource.fetchHistory()).map(normalizeReading).forEach(ingest); }
  await tick();
  Loop.timer = setInterval(tick, CONFIG.POLL_SECONDS * 1000);
}

Demo.init();
