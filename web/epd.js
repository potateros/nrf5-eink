// EPD-nRF5 BLE protocol for the NRF_EPD_5E5D tag, as Web Bluetooth. A port of epd/device.py and
// epd/rle.py, plus the variant's slot commands (docs/DEVICE.md §2.0b-c). No network, no deps.

export const SVC = "62750001-d828-918d-fb46-b6c11c675aec";
const CHAR = "62750002-d828-918d-fb46-b6c11c675aec";
const VER = "62750003-d828-918d-fb46-b6c11c675aec";

export const CMD = {
  INIT: 0x01, CLEAR: 0x02, REFRESH: 0x05, SET_TIME: 0x20, WRITE_IMAGE: 0x30,
  SET_SLOT: 0x31, FREE_SLOT: 0x32, SET_SLIDE: 0x33, SET_CONFIG: 0x90,
};
export const MODE = { PICTURE: 0, CALENDAR: 1, CLOCK: 2 };
export const CFG_MODE = 11;  // config byte: display mode
export const CFG_SLOT = 13;  // config byte: current slot, where the next upload is stored
export const REFRESH_HOLD = 30;  // s to stay connected after anything that refreshes the panel
export const CLEAR_WAIT = 25;    // s after CLEAR before INIT (INIT resets the panel)
export const SCRATCH_SLOT = 14;  // display-only uploads land here, so stored slots survive

// Opcodes the raw console refuses: pin map, sleep with no wake pin, config erase, raw config.
const BLOCKED = new Map([
  [0x00, "SET_PINS overwrites the pin map in flash"],
  [0x90, "raw SET_CONFIG; use the mode buttons instead"],
  [0x92, "SYS_SLEEP: no wake-up pin, it may not wake again"],
  [0x99, "CFG_ERASE: defaults lack model 0x16 and break the display"],
]);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- RLE (matches the firmware and epd/rle.py) ---------------------------------------------

export function rleCompress(data, maxLiteral = 128) {
  const out = [];
  let i = 0;
  const n = data.length;
  while (i < n) {
    let run = 1;
    while (i + run < n && run < 130 && data[i + run] === data[i]) run++;
    if (run >= 3) {
      out.push(0x80 | (run - 3), data[i]);
      i += run;
      continue;
    }
    const start = i;
    while (i < n && i - start < maxLiteral) {
      if (i + 2 < n && data[i] === data[i + 1] && data[i] === data[i + 2]) break;
      i++;
    }
    out.push(i - start - 1);
    for (let k = start; k < i; k++) out.push(data[k]);
  }
  return Uint8Array.from(out);
}

// Compress, then split at code boundaries so each chunk decodes on its own.
export function rleChunks(data, maxChunk) {
  const stream = rleCompress(data, Math.min(maxChunk - 1, 128));
  const result = [];
  let start = 0, i = 0;
  while (i < stream.length) {
    const len = stream[i] & 0x80 ? 2 : stream[i] + 2;
    if (i - start + len > maxChunk && i > start) {
      result.push(stream.slice(start, i));
      start = i;
    }
    i += len;
  }
  if (i > start) result.push(stream.slice(start, i));
  return result;
}

export function rleDecompress(data) {
  const out = [];
  let i = 0;
  while (i < data.length) {
    const c = data[i];
    if (c & 0x80) {
      for (let k = 0; k < (c & 0x7f) + 3; k++) out.push(data[i + 1]);
      i += 2;
    } else {
      for (let k = 0; k <= c; k++) out.push(data[i + 1 + k]);
      i += c + 2;
    }
  }
  return Uint8Array.from(out);
}

// --- battery, same curve as the firmware's calendar glyph (epd/battery.py battery_pct) -----

export function batteryPct(mv) {
  const adc = Math.floor((mv * 2047) / 3600);
  for (const [hi, lo, top, span] of [[1705, 1584, 28, 72], [1584, 1360, 4, 24], [1360, 1136, 0, 4]]) {
    if (adc > hi) return hi === 1705 ? 100 : top + span;
    if (adc > lo) return top + Math.floor(((adc - lo) * span) / (hi - lo));
  }
  return 0;
}

const tzHours = () => -new Date().getTimezoneOffset() / 60;

// --- device ---------------------------------------------------------------------------------

export class EPD extends EventTarget {
  constructor() {
    super();
    this.device = null;
    this.char = null;
    this.queue = Promise.resolve();  // Chrome rejects overlapping GATT operations: serialise
    this.reset();
  }

  reset() {
    this.state = { config: null, slots: null, mtu: 20, rle: false, t: null, bat: null, version: null, clockEnable: null };
    this.messages = [];
  }

  get connected() { return !!(this.device && this.device.gatt.connected); }

  emit(type, detail) { this.dispatchEvent(new CustomEvent(type, { detail })); }
  log(text, kind = "info") { this.emit("log", { text, kind }); }

  async connect() {
    if (!navigator.bluetooth) throw new Error("Web Bluetooth isn't available. Use Chrome or Edge on the Mac.");
    this.device = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: "NRF_EPD" }], optionalServices: [SVC],
    });
    this.device.addEventListener("gattserverdisconnected", () => {
      this.log("Disconnected", "warn");
      this.char = null;
      this.emit("state", this.state);
      this.emit("disconnected");
    });
    this.reset();
    this.log(`Connecting to ${this.device.name}…`);
    const server = await this.device.gatt.connect();
    const svc = await server.getPrimaryService(SVC);
    this.char = await svc.getCharacteristic(CHAR);
    try {
      const raw = new Uint8Array((await (await svc.getCharacteristic(VER)).readValue()).buffer);
      this.state.version = raw.length > 1
        ? new TextDecoder().decode(raw).replace(/\0+$/, "")
        : "0x" + raw[0].toString(16);
    } catch { this.state.version = "?"; }
    this.char.addEventListener("characteristicvaluechanged", (e) => {
      const v = e.target.value;
      this.onNotify(new Uint8Array(v.buffer, v.byteOffset, v.byteLength).slice());
    });
    await this.char.startNotifications();  // the firmware answers with its config bytes
    await this.waitReady(15000);
    this.log(`Connected: ${this.state.version}`, "ok");
  }

  disconnect() {
    if (this.connected) this.device.gatt.disconnect();
  }

  onNotify(bytes) {
    const text = new TextDecoder().decode(bytes);
    this.messages.push(bytes);
    if (!/^[a-z_]+=/.test(text)) {
      this.state.config = bytes;  // raw config block (14 bytes on this unit)
    } else {
      for (const tok of text.split(/\s+/)) {
        const [k, v] = tok.split("=");
        if (k === "mtu") this.state.mtu = parseInt(v, 10);
        else if (k === "rle") this.state.rle = v === "1";
        else if (k === "t") this.state.t = parseInt(v, 10);
        else if (k === "bat") this.state.bat = parseInt(v, 10);
        else if (k === "clock_enable") this.state.clockEnable = v === "1";
      }
      if (text.startsWith("slots=")) {
        const [count, mask, current] = text.slice(6).trim().split(/\s+/).map((x) => parseInt(x, 10));
        this.state.slots = { count, mask, current: Number.isNaN(current) ? 255 : current };
      }
      // sid= is a licence id the vendor's tool sends to a paid server; we don't keep or show it.
    }
    this.emit("state", this.state);
  }

  // Seconds the device clock is ahead of this computer (the device reports local time).
  clockDrift() {
    if (this.state.t == null) return null;
    return this.state.t - (Date.now() / 1000 + tzHours() * 3600);
  }

  write(bytes, response = true) {
    const data = Uint8Array.from(bytes);
    const op = this.queue.then(async () => {
      if (!this.char) throw new Error("Not connected");
      if (response) await this.char.writeValueWithResponse(data);
      else await this.char.writeValueWithoutResponse(data);
    });
    this.queue = op.catch(() => {});
    return op;
  }

  async waitFor(pred, timeout) {
    const start = this.messages.length;
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (this.messages.slice(start).some(pred)) return true;
      await sleep(100);
    }
    return false;
  }

  // INIT until the firmware answers with `mtu=` (proves it is idle and initialised).
  async waitReady(timeout = 90000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const seen = this.messages.length;
      await this.write([CMD.INIT]);
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        if (this.messages.slice(seen).some((m) => m[0] === 0x6d && new TextDecoder().decode(m).startsWith("mtu="))) return;
        await sleep(100);
      }
    }
    throw new Error("The firmware didn't answer INIT");
  }

  // Fresh config + slots: the firmware sends its config only when notifications are re-enabled.
  // Clears the old copy first, so callers can tell whether a fresh one arrived.
  async refreshState() {
    await this.queue;
    this.state.config = null;
    await this.char.stopNotifications();
    await this.char.startNotifications();
    const end = Date.now() + 3000;
    while (!this.state.config && Date.now() < end) await sleep(100);
    await this.waitReady(15000);
    if (!this.state.config) this.log("The device didn't resend its config; Mode and Current slot are unknown", "warn");
    return this.state;
  }

  // Point the next upload (the scheduled push included) at `slot` without uploading, so a kept
  // or shown slot isn't overwritten. Returns whether config byte 13 now reads `slot`.
  async retarget(slot = SCRATCH_SLOT) {
    await this.write([CMD.SET_SLOT, 0, slot]);
    await sleep(300);
    await this.refreshState();
    const cfg = this.state.config;
    return !!cfg && cfg.length > CFG_SLOT && cfg[CFG_SLOT] === slot;
  }

  async writePlane(data, red, onChunk) {
    const size = this.state.mtu - 2;
    let parts = this.state.rle ? rleChunks(data, size) : null;
    const useRle = parts && parts.reduce((a, p) => a + p.length, 0) < data.length;
    if (!useRle) {
      parts = [];
      for (let i = 0; i < data.length; i += size) parts.push(data.slice(i, i + size));
    }
    for (let i = 0; i < parts.length; i++) {
      const flags = (red ? 0x01 : 0) | (i === 0 ? 0x02 : 0) | (useRle ? 0x04 : 0);
      const last = i === parts.length - 1;
      await this.write([CMD.WRITE_IMAGE, flags, ...parts[i]], last || i % 8 === 7);
      onChunk?.(i + 1, parts.length);
    }
  }

  // Upload both planes and refresh. With slot set, the frame is stored there; otherwise it goes
  // to the scratch slot so the slots you stored keep their pictures. Always sends a red plane:
  // stale red RAM would show through.
  async upload(black, red, { slot = SCRATCH_SLOT, onProgress } = {}) {
    await this.write([CMD.SET_SLOT, 0, slot]);
    await this.waitReady();
    const total = 2;
    await this.writePlane(black, false, (i, n) => onProgress?.((i / n) / total, "black"));
    await this.writePlane(red ?? new Uint8Array(black.length).fill(0xff), true,
      (i, n) => onProgress?.(0.5 + (i / n) / total, "red"));
    await this.write([CMD.REFRESH]);
  }

  async setTime(mode) {
    const ts = Math.floor(Date.now() / 1000);
    await this.write([CMD.SET_TIME, (ts >>> 24) & 255, (ts >>> 16) & 255, (ts >>> 8) & 255, ts & 255, tzHours() & 255, mode]);
  }

  async showSlot(n) {
    await this.write([CMD.SET_SLOT, 1, n]);
    await sleep(500);
    await this.setTime(MODE.PICTURE);
  }

  freeSlot(n) { return this.write([CMD.FREE_SLOT, n]); }
  startCarousel(minutes) { return this.write([CMD.SET_SLIDE, (minutes >> 8) & 255, minutes & 255]); }
  clear() { return this.write([CMD.CLEAR]); }

  // Set the display-mode byte from a freshly read config, and pin the current slot to `slot`
  // (a stale byte 13 would aim the next push at a kept picture). Calendar = the firmware draws
  // its own calendar at local midnight.
  async armFallback(mode = MODE.CALENDAR, slot = SCRATCH_SLOT) {
    await this.refreshState();
    const cfg = this.state.config;
    if (!cfg || cfg.length <= CFG_MODE) throw new Error("No fresh config from the device; fallback not armed");
    const next = cfg.slice();
    next[CFG_MODE] = mode;
    if (next.length > CFG_SLOT) next[CFG_SLOT] = slot;
    await this.write([CMD.SET_CONFIG, ...next]);
  }

  async raw(bytes) {
    if (!bytes.length) throw new Error("Empty command");
    if (BLOCKED.has(bytes[0])) throw new Error(`Blocked: ${BLOCKED.get(bytes[0])}`);
    if (bytes[0] === CMD.INIT && bytes.length > 1) throw new Error("Blocked: INIT with a model id is persisted");
    if (bytes[0] >= 0xa0) throw new Error("Blocked: unknown range, could be DFU");
    await this.write(bytes);
  }
}
