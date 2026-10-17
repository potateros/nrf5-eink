// Image -> panel bit planes (400x300, 1 bit/px, MSB first). Mirrors epd/image.py: black plane
// 1 = not black, red plane 1 = not red, palette white / black / red (220, 0, 0).

export const W = 400, H = 300;
export const INK_THRESHOLD = 170;  // luminance below this is black when not dithering (as epd.image)
const PALETTE = [[255, 255, 255], [0, 0, 0], [220, 0, 0]];  // index 0 white, 1 black, 2 red

// Draw source (ImageBitmap / HTMLImageElement) onto a 400x300 canvas.
// fit: "cover" crops to fill, "contain" letterboxes on white. rotate: 0/90/180/270.
export function compose(source, { fit = "cover", rotate = 0 } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, W, H);
  const sw = source.width, sh = source.height;
  const turned = rotate % 180 !== 0;
  const bw = turned ? sh : sw, bh = turned ? sw : sh;  // bounding box after rotation
  const scale = fit === "cover" ? Math.max(W / bw, H / bh) : Math.min(W / bw, H / bh);
  ctx.save();
  ctx.translate(W / 2, H / 2);
  ctx.rotate((rotate * Math.PI) / 180);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(source, (-sw * scale) / 2, (-sh * scale) / 2, sw * scale, sh * scale);
  ctx.restore();
  return ctx.getImageData(0, 0, W, H);
}

const nearest = (r, g, b, colours) => {
  let best = 0, bestD = Infinity;
  for (const i of colours) {
    const [pr, pg, pb] = PALETTE[i];
    const d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
};

// Diffusion kernels: [dx, dy, weight]
const KERNELS = {
  floyd: { div: 16, taps: [[1, 0, 7], [-1, 1, 3], [0, 1, 5], [1, 1, 1]] },
  atkinson: { div: 8, taps: [[1, 0, 1], [2, 0, 1], [-1, 1, 1], [0, 1, 1], [1, 1, 1], [0, 2, 1]] },
};

// Returns palette indices (Uint8Array W*H). dither: "none" | "floyd" | "atkinson".
export function quantize(img, { red = true, dither = "none", threshold = INK_THRESHOLD } = {}) {
  const n = W * H;
  const out = new Uint8Array(n);
  const src = img.data;
  if (!red && dither === "none") {  // same rule as to_planes(red=False, dither=False)
    for (let i = 0; i < n; i++) {
      const lum = 0.299 * src[i * 4] + 0.587 * src[i * 4 + 1] + 0.114 * src[i * 4 + 2];
      out[i] = lum >= threshold ? 0 : 1;
    }
    return out;
  }
  const colours = red ? [0, 1, 2] : [0, 1];
  if (dither === "none") {
    for (let i = 0; i < n; i++) out[i] = nearest(src[i * 4], src[i * 4 + 1], src[i * 4 + 2], colours);
    return out;
  }
  const buf = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) buf[i * 3 + c] = src[i * 4 + c];
  const { div, taps } = KERNELS[dither];
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = y * W + x;
      const r = buf[i * 3], g = buf[i * 3 + 1], b = buf[i * 3 + 2];
      const p = nearest(r, g, b, colours);
      out[i] = p;
      const er = r - PALETTE[p][0], eg = g - PALETTE[p][1], eb = b - PALETTE[p][2];
      for (const [dx, dy, w] of taps) {
        const xx = x + dx, yy = y + dy;
        if (xx < 0 || xx >= W || yy >= H) continue;
        const j = (yy * W + xx) * 3;
        buf[j] += (er * w) / div;
        buf[j + 1] += (eg * w) / div;
        buf[j + 2] += (eb * w) / div;
      }
    }
  }
  return out;
}

// Palette indices -> (black plane, red plane).
export function toPlanes(idx) {
  const bpr = W / 8;
  const black = new Uint8Array(bpr * H), red = new Uint8Array(bpr * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const p = idx[y * W + x], bit = 0x80 >> (x % 8), k = y * bpr + (x >> 3);
      if (p !== 1) black[k] |= bit;  // 1 = not black
      if (p !== 2) red[k] |= bit;    // 1 = not red
    }
  }
  return { black, red };
}

// Palette indices -> ImageData, exactly what the panel will show.
export function previewData(idx) {
  const img = new ImageData(W, H);
  for (let i = 0; i < idx.length; i++) {
    const [r, g, b] = PALETTE[idx[i]];
    img.data[i * 4] = r;
    img.data[i * 4 + 1] = g;
    img.data[i * 4 + 2] = b;
    img.data[i * 4 + 3] = 255;
  }
  return img;
}
