import { EPD, MODE, CFG_MODE, CFG_SLOT, REFRESH_HOLD, CLEAR_WAIT, SCRATCH_SLOT, batteryPct } from "./epd.js";
import { compose, quantize, toPlanes, previewData, W, H } from "./image.js";

const $ = (id) => document.getElementById(id);
const epd = new EPD();
let busy = false;
let source = null;     // ImageBitmap of the picked file or rendered layout
let planes = null;     // { black, red } for the current preview
let selected = null;   // selected slot index

// --- log & status ---------------------------------------------------------------------------

function log(text, kind = "info") {
  const li = document.createElement("li");
  li.className = kind;
  const t = document.createElement("time");
  t.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  li.append(t, text);
  $("log").append(li);
  $("log").scrollTop = $("log").scrollHeight;
}
epd.addEventListener("log", (e) => log(e.detail.text, e.detail.kind));
epd.addEventListener("state", () => render());
epd.addEventListener("disconnected", () => render());

function setStatus() {
  const s = $("status");
  if (busy) { s.className = "pill busy"; s.textContent = "Busy"; }
  else if (epd.connected) { s.className = "pill on"; s.textContent = `Connected · ${epd.device.name}`; }
  else { s.className = "pill off"; s.textContent = "Not connected"; }
  $("connect").textContent = epd.connected ? "Disconnect" : "Connect";
  $("connect").classList.toggle("primary", !epd.connected);
  $("connect").disabled = busy;
}

function updateButtons() {
  const conn = epd.connected && !busy;
  for (const el of document.querySelectorAll("[data-needs]")) {
    const need = el.dataset.needs;
    el.disabled = !conn || (need === "slot" && selected === null);
  }
  $("send").disabled = !conn || !planes;
}

const preventUnload = (e) => { e.preventDefault(); e.returnValue = ""; };

// Run a device action with the UI locked; optional hold keeps the link up while the panel refreshes.
async function run(label, fn) {
  if (busy) return;
  busy = true;
  window.addEventListener("beforeunload", preventUnload);
  render();
  try {
    await fn();
  } catch (err) {
    log(`${label}: ${err.message || err}`, "err");
  } finally {
    busy = false;
    window.removeEventListener("beforeunload", preventUnload);
    $("hold").hidden = true;
    $("image-card").querySelector(".progress").hidden = true;
    render();
  }
}

async function hold(seconds, text) {
  $("hold").hidden = false;
  const start = Date.now();
  while (Date.now() - start < seconds * 1000) {
    const left = Math.ceil(seconds - (Date.now() - start) / 1000);
    $("hold-text").textContent = `${text} Keep this tab open: ${left} s`;
    $("hold-fill").style.width = `${((Date.now() - start) / (seconds * 1000)) * 100}%`;
    await new Promise((r) => setTimeout(r, 250));
    if (!epd.connected) throw new Error("Link dropped during the refresh; the panel may be half-drawn. Send again.");
  }
  $("hold").hidden = true;
}

// --- device facts & slots ---------------------------------------------------------------------

const MODES = ["Picture", "Calendar", "Clock"];

function render() {
  const s = epd.state;
  const cfg = s.config;
  $("f-version").textContent = s.version || "–";
  if (s.bat) {
    const pct = batteryPct(s.bat);
    $("f-bat").innerHTML = "";
    const span = document.createElement("span");
    span.textContent = `~${pct}%${pct < 30 ? " LOW" : ""}`;
    if (pct < 30) span.className = "low";
    $("f-bat").append(span, ` · ${(s.bat / 1000).toFixed(2)} V rail`);
  } else $("f-bat").textContent = "–";
  const drift = epd.clockDrift();
  $("f-clock").textContent = drift == null ? "–"
    : Math.abs(drift) < 90 ? `in sync (${drift >= 0 ? "+" : ""}${Math.round(drift)} s)`
    : `off by ${Math.round(drift / 60)} min · Calendar syncs it`;
  $("f-mode").textContent = cfg ? (MODES[cfg[CFG_MODE]] ?? `0x${cfg[CFG_MODE].toString(16)}`) : "–";
  const cur = cfg && cfg.length > CFG_SLOT ? cfg[CFG_SLOT] : null;
  $("f-slot").textContent = cur == null ? "–" : cur === 255 ? "none" : `${cur}${cur === SCRATCH_SLOT ? " (scratch)" : ""}`;
  $("f-link").textContent = epd.connected ? `MTU ${s.mtu}, RLE ${s.rle ? "on" : "off"}` : "–";
  renderSlots(cur);
  setStatus();
  updateButtons();
}

function renderSlots(cur) {
  const sl = epd.state.slots;
  const count = sl?.count || 15;
  const box = $("slots");
  box.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const used = sl ? (sl.mask & (1 << i)) !== 0 : false;
    const b = document.createElement("button");
    b.className = "slot" + (used ? " used" : "") + (i === cur ? " cur" : "");
    b.setAttribute("aria-pressed", String(i === selected));
    b.disabled = !epd.connected;
    const small = document.createElement("small");
    small.textContent = i === SCRATCH_SLOT ? "scratch" : used ? "stored" : "empty";
    b.append(String(i), small);
    b.title = `Slot ${i}: ${small.textContent}${i === cur ? " · current" : ""}`;
    b.addEventListener("click", () => {
      selected = selected === i ? null : i;
      $("s-selected").textContent = selected === null ? "No slot selected" : `Slot ${selected} selected`;
      render();
    });
    box.append(b);
  }
  // keep the save-to choices in step with what's stored
  const target = $("target");
  const keep = target.value;
  target.innerHTML = "";
  target.append(new Option(`Scratch slot ${SCRATCH_SLOT} (one-off)`, String(SCRATCH_SLOT)));
  for (let i = 0; i < count; i++) {
    if (i === SCRATCH_SLOT) continue;
    const used = sl ? (sl.mask & (1 << i)) !== 0 : false;
    target.append(new Option(`Keep in slot ${i}${used ? " (replace)" : ""}`, String(i)));
  }
  target.value = keep || String(SCRATCH_SLOT);
}

// --- picture pipeline ---------------------------------------------------------------------------

const prefs = ["fit", "rotate", "colours", "dither", "threshold"];
try {
  const saved = JSON.parse(localStorage.getItem("epd-prefs") || "{}");
  for (const k of prefs) if (saved[k] != null) $(k).value = saved[k];
} catch { /* storage blocked: defaults */ }

function savePrefs() {
  try { localStorage.setItem("epd-prefs", JSON.stringify(Object.fromEntries(prefs.map((k) => [k, $(k).value])))); } catch { /* ignore */ }
}

function recompute() {
  $("threshold-val").textContent = $("threshold").value;
  $("threshold-wrap").hidden = !($("colours").value === "bw" && $("dither").value === "none");
  if (!source) return;
  const img = compose(source, { fit: $("fit").value, rotate: Number($("rotate").value) });
  const idx = quantize(img, { red: $("colours").value === "bwr", dither: $("dither").value, threshold: Number($("threshold").value) });
  planes = toPlanes(idx);
  const ctx = $("preview").getContext("2d");
  ctx.putImageData(previewData(idx), 0, 0);
  $("empty").hidden = true;
  updateButtons();
}

for (const k of prefs) $(k).addEventListener("input", () => { savePrefs(); recompute(); });

// --- picture sources: image file or dashboard ------------------------------------------------------

const caption = (text) => { $("caption").textContent = text; };
const overlay = (text) => { $("overlay").hidden = !text; if (text) $("overlay-text").textContent = text; };

async function loadFile(f) {
  if (!f) return;
  try {
    source = await createImageBitmap(f);
  } catch { log(`Can't read ${f.name} as an image`, "err"); return; }
  renderToken++;  // a dashboard render still in flight must not replace this
  overlay(null);
  fileShown = true;
  wrap.classList.add("has-file");
  for (const b of document.querySelectorAll(".layout")) b.setAttribute("aria-pressed", "false");
  caption(`${f.name} · ${source.width} × ${source.height} → 400 × 300`);
  log(`Loaded ${f.name} (${source.width} × ${source.height})`);
  recompute();
}
// The preview is the picker: click it (in Image file mode) to choose, or drop an image on it
// in either mode (dropping switches to Image file).
const wrap = $("preview-wrap");
$("file").addEventListener("change", () => { loadFile($("file").files[0]); $("file").value = ""; });
wrap.addEventListener("click", () => { if (wrap.classList.contains("pick")) $("file").click(); });
wrap.addEventListener("keydown", (e) => {
  if (wrap.classList.contains("pick") && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); $("file").click(); }
});
wrap.addEventListener("dragover", (e) => { e.preventDefault(); wrap.classList.add("over"); });
wrap.addEventListener("dragleave", () => wrap.classList.remove("over"));
wrap.addEventListener("drop", (e) => {
  e.preventDefault();
  wrap.classList.remove("over");
  const f = e.dataTransfer.files[0];
  if (!f) return;
  setSource("file");
  loadFile(f);
});

let fileShown = false;  // the preview holds a picked file (vs a dashboard or nothing)

function setSource(src) {
  for (const t of document.querySelectorAll(".seg [role=tab]")) t.setAttribute("aria-selected", String(t.dataset.src === src));
  $("src-layout").hidden = src !== "layout";
  $("src-file").hidden = src !== "file";
  const pick = src === "file";
  wrap.classList.toggle("pick", pick);
  wrap.classList.toggle("has-file", pick && fileShown);
  if (pick) { wrap.tabIndex = 0; wrap.setAttribute("role", "button"); wrap.setAttribute("aria-label", "Choose an image"); }
  else { wrap.removeAttribute("tabindex"); wrap.removeAttribute("role"); wrap.removeAttribute("aria-label"); }
  $("empty").textContent = pick && !fileShown
    ? "Drop an image here, or click to choose"
    : "Pick a dashboard or an image. The preview shows exactly what the panel will draw.";
  if (pick && !fileShown) { $("empty").hidden = false; planes = null; caption(""); updateButtons(); }
}

let renderToken = 0;

async function loadLayouts() {
  let rows;
  try { rows = await (await fetch("/api/layouts")).json(); }
  catch { $("layout-hint").textContent = "Dashboards need the local server: uv run eink web"; return; }
  for (const r of rows) {
    const b = document.createElement("button");
    b.className = "layout";
    b.setAttribute("aria-pressed", "false");
    b.title = r.desc;
    let pic;
    if (r.name === "auto") {
      pic = document.createElement("span");
      pic.className = "ph";
      pic.textContent = "rain or proverb, picked by the forecast";
    } else {
      pic = new Image();
      pic.alt = "";
      pic.src = `/api/thumb?name=${encodeURIComponent(r.name)}`;
      pic.onerror = () => { const ph = document.createElement("span"); ph.className = "ph"; ph.textContent = "no screenshot yet"; pic.replaceWith(ph); };
    }
    const name = document.createElement("b");
    name.textContent = r.name;
    const sub = document.createElement("small");
    sub.textContent = r.current ? "scheduled now" : r.desc.split(/[,:;(]/)[0];
    b.append(pic, name, sub);
    b.addEventListener("click", () => selectLayout(r.name, b, pic));
    $("layouts").append(b);
  }
}

// Show the screenshot at once (exact pixels, 2x -> 1x), then swap in a live render.
async function selectLayout(name, button, pic) {
  const token = ++renderToken;
  lastLayout = [name, button, pic];
  fileShown = false;
  for (const b of document.querySelectorAll(".layout")) b.setAttribute("aria-pressed", String(b === button));
  planes = null;  // nothing to send until the live render lands
  updateButtons();
  if (pic instanceof HTMLImageElement && pic.complete && pic.naturalWidth) {
    const ctx = $("preview").getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(pic, 0, 0, W, H);
    $("empty").hidden = true;
  }
  overlay(`Rendering ${name} with live data…`);
  caption("");
  try {
    const res = await fetch(`/api/render?name=${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const bmp = await createImageBitmap(await res.blob());
    if (token !== renderToken) return;  // a newer pick won
    source = bmp;
    // dashboards are already pure white/black/red at 400x300: map them 1:1
    $("fit").value = "cover"; $("rotate").value = "0"; $("colours").value = "bwr"; $("dither").value = "none";
    recompute();
    caption(`${name} · live render ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · exactly what the panel will draw`);
    log(`Rendered ${name}`, "ok");
  } catch (err) {
    if (token !== renderToken) return;
    caption(`${name}: live render failed, showing the last screenshot (not sendable)`);
    log(`Render ${name} failed: ${err.message}`, "err");
  } finally {
    if (token === renderToken) overlay(null);
  }
}

let lastLayout = null;  // [name, button, pic] of the last dashboard picked, to restore on switching back

for (const tab of document.querySelectorAll(".seg [role=tab]")) {
  tab.addEventListener("click", () => {
    if (tab.getAttribute("aria-selected") === "true") return;
    if (tab.dataset.src === "file") {
      fileShown = false;
      renderToken++;  // drop any dashboard render in flight
      overlay(null);
      setSource("file");
    } else {
      fileShown = false;
      setSource("layout");
      if (lastLayout) selectLayout(...lastLayout);
      else { $("empty").hidden = false; planes = null; caption(""); updateButtons(); }
    }
  });
}

// --- actions ---------------------------------------------------------------------------------------

$("connect").addEventListener("click", () => {
  if (epd.connected) { epd.disconnect(); return; }
  run("Connect", async () => {
    try { await epd.connect(); }
    catch (err) {
      if (err.name === "NotFoundError") { log("No device chosen. If it isn't listed: hold the scheduled push, wait for an advert (up to ~45 s).", "warn"); return; }
      throw err;
    }
  });
});

$("send").addEventListener("click", () => run("Send", async () => {
  const slot = Number($("target").value);
  const used = epd.state.slots && (epd.state.slots.mask & (1 << slot)) !== 0;
  if (slot !== SCRATCH_SLOT && used && !confirm(`Slot ${slot} already holds a picture. Replace it?`)) return;
  const bar = $("image-card").querySelector(".progress");
  bar.hidden = false;
  const t0 = Date.now();
  log(`Uploading to slot ${slot}${slot === SCRATCH_SLOT ? " (scratch)" : ""}…`);
  await epd.upload(planes.black, $("colours").value === "bwr" ? planes.red : null, {
    slot, onProgress: (f) => { $("progress-fill").style.width = `${f * 100}%`; },
  });
  log(`Uploaded in ${((Date.now() - t0) / 1000).toFixed(1)} s; panel refreshing`, "ok");
  await hold(REFRESH_HOLD, "Panel refreshing.");
  if ($("arm").checked) {
    await epd.armFallback(MODE.CALENDAR, SCRATCH_SLOT);  // also re-points byte 13 at scratch
    log("Calendar fallback armed for midnight");
  }
  if (slot !== SCRATCH_SLOT) await protectSlot(slot);
  else await epd.refreshState();
  log("Done", "ok");
}));

// Every upload lands in the current slot, the scheduled push included. After keeping or
// showing slot n, point the target back at scratch so n survives the next push.
async function protectSlot(n) {
  if (await epd.retarget(SCRATCH_SLOT)) {
    log(`Slot ${n} protected: the next upload goes to scratch slot ${SCRATCH_SLOT}`, "ok");
  } else {
    const cur = epd.state.config?.[CFG_SLOT];
    log(`Couldn't move the target off slot ${n} (current: ${cur ?? "unknown"}). Keep the scheduled push on hold or it will overwrite slot ${n}`, "err");
  }
}

function modeAction(mode, label) {
  return () => run(label, async () => {
    if (mode === MODE.CLOCK && !confirm("Clock mode redraws every minute. The seller warns a three-colour panel can burn in if left on clock. Continue?")) return;
    await epd.setTime(mode);
    log(`${label}: time synced, panel redrawing`);
    await hold(REFRESH_HOLD, `Drawing ${label.toLowerCase()}.`);
    await epd.refreshState();
  });
}
$("m-calendar").addEventListener("click", modeAction(MODE.CALENDAR, "Calendar"));
$("m-clock").addEventListener("click", modeAction(MODE.CLOCK, "Clock"));
$("m-clear").addEventListener("click", () => run("Clear", async () => {
  if (!confirm("Wipe the panel to white? It takes about 25 s.")) return;
  await epd.clear();
  log("Clearing");
  await hold(CLEAR_WAIT + 5, "Clearing.");
  await epd.refreshState();
}));
$("m-refresh-state").addEventListener("click", () => run("Re-read", async () => { await epd.refreshState(); log("State re-read"); }));

$("s-show").addEventListener("click", () => run("Show slot", async () => {
  const n = selected;
  await epd.showSlot(n);
  log(`Showing slot ${n}`);
  await hold(REFRESH_HOLD, `Drawing slot ${n}.`);
  if (n !== SCRATCH_SLOT) await protectSlot(n);
  else await epd.refreshState();
}));
$("s-delete").addEventListener("click", () => run("Delete slot", async () => {
  const n = selected;
  if (!confirm(`Delete the picture in slot ${n}? This can't be undone.`)) return;
  await epd.freeSlot(n);
  log(`Deleted slot ${n}`);
  await epd.refreshState();
}));
$("s-carousel").addEventListener("click", () => run("Carousel", async () => {
  const min = Math.max(1, Math.min(1440, Math.round(Number($("interval").value) || 60)));
  await epd.startCarousel(min);
  log(`Carousel started: every ${min} min through stored slots. Any send, Calendar, Clock or scheduled push stops it`, "ok");
  await epd.refreshState();
}));

$("raw-send").addEventListener("click", () => run("Raw", async () => {
  const text = $("raw").value.trim();
  if (!/^([0-9a-f]{2}\s*)+$/i.test(text)) throw new Error("Use hex bytes like 31 01 03");
  const bytes = text.split(/\s+/).join("").match(/../g).map((h) => parseInt(h, 16));
  await epd.raw(bytes);
  log(`Sent ${bytes.map((b) => b.toString(16).padStart(2, "0")).join(" ")}`);
}));

// --- tabs ----------------------------------------------------------------------------------------

for (const tab of document.querySelectorAll(".tabs [role=tab]")) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll(".tabs [role=tab]")) t.setAttribute("aria-selected", String(t === tab));
    $("tab-panel").hidden = tab.dataset.tab !== "panel";
    $("tab-help").hidden = tab.dataset.tab !== "help";
  });
}

if (!navigator.bluetooth) log("This browser has no Web Bluetooth. Open the page in Chrome or Edge.", "err");
else log("Ready. Hold the scheduled push first: hq hold eink-dashboard-1");
$("preview").width = W;
$("preview").height = H;
recompute();
loadLayouts();
render();
// Keeps a background server (hq's launcher) alive while this tab is open.
setInterval(() => fetch("/api/ping").catch(() => {}), 60000);
