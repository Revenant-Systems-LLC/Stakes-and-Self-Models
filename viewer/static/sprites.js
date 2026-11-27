// Clawlings pixel art. Everything is drawn pixel by pixel on a small canvas
// that the page scales up with crisp edges. Original art for this project.
// Nothing here knows about logs, episodes or blinding.

export const TILE = 14;

export const PAL = {
  ink: "#24122e",
  sea: "#163f55", sea2: "#1f5670", foam: "#8fd3e0",
  rock: "#3b2f4f", rock2: "#54456c",
  sand: "#f3dcc0", sand2: "#e8c9a6", sand3: "#f9ead6", pebble: "#d3ad8b",
  body: "#ff7a59", body2: "#ffab8a", body3: "#d9493c", belly: "#ffd2b8",
  eye: "#1a0f24", white: "#ffffff", blush: "#ff8fb8",
  leaf: "#4fbf6a", leaf2: "#2f8f4e", berry: "#ff4f9a", berry2: "#ffd1e6",
  urchin: "#5b2c7a", urchin2: "#8a4fb0", spine: "#2c1240", tip: "#ff9ad5",
  chosen: "#5ef0ff", shown: "#ffb43a", fog: "rgba(28,14,48,0.62)", haze: "#b7c2d9",
  heart: "#ff4f7b", sweat: "#7fd6ff", alert: "#ffde3b", zzz: "#c9b8ff", note: "#ffe27a",
};

// --- primitives ------------------------------------------------------------
export function px(ctx, x, y, c) { ctx.fillStyle = c; ctx.fillRect(x | 0, y | 0, 1, 1); }
export function rect(ctx, x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(x | 0, y | 0, w | 0, h | 0); }

// Pixel-perfect filled ellipse centred on a half-pixel grid.
export function blob(ctx, cx, cy, rx, ry, c) {
  ctx.fillStyle = c;
  for (let y = -ry; y <= ry; y++) {
    const w = Math.floor(rx * Math.sqrt(Math.max(0, 1 - (y * y) / ((ry + 0.35) * (ry + 0.35)))));
    ctx.fillRect(Math.round(cx - w), Math.round(cy + y), w * 2 + 1, 1);
  }
}

// Tiny bitmaps: rows of characters, each char a palette key (or '.' for empty).
export function bitmap(ctx, x, y, rows, colors) {
  for (let r = 0; r < rows.length; r++)
    for (let c = 0; c < rows[r].length; c++) {
      const k = rows[r][c];
      if (k !== "." && colors[k]) px(ctx, x + c, y + r, colors[k]);
    }
}

// Cheap stable noise for ground speckles.
export function hash(a, b, s = 0) {
  let h = (a * 374761393 + b * 668265263 + s * 2147483647) | 0;
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

// --- tiles -----------------------------------------------------------------
export function drawSand(ctx, x, y, r, c, t) {
  rect(ctx, x, y, TILE, TILE, (r + c) % 2 ? PAL.sand : PAL.sand3);
  for (let i = 0; i < 5; i++) {
    const h = hash(r * 31 + i, c * 17 + i);
    if (h < 0.55) px(ctx, x + Math.floor(hash(r, c, i) * TILE), y + Math.floor(hash(c, r, i + 9) * TILE), h < 0.2 ? PAL.pebble : PAL.sand2);
  }
  const d = hash(r * 7 + 3, c * 13 + 5, 42);
  if (d < 0.07) bitmap(ctx, x + 4, y + 8, [".pp.", "pwwp", ".pp."], { p: PAL.blush, w: PAL.white });          // little shell
  else if (d < 0.13) bitmap(ctx, x + 5, y + 6, ["g..g", "g.g.", ".gg.", ".g.."], { g: PAL.leaf2 });           // seaweed tuft
  // slow caustic shimmer
  const ph = Math.sin(t / 900 + r * 0.9 + c * 0.6);
  if (ph > 0.93) rect(ctx, x + 3 + ((r * 5 + c) % 7), y + 4 + ((r + c * 3) % 6), 2, 1, PAL.white);
}

export function drawSea(ctx, x, y, r, c, t) {
  rect(ctx, x, y, TILE, TILE, (r + c) % 2 ? PAL.sea : PAL.sea2);
  const k = Math.floor(t / 260 + r * 3 + c * 5) % 14;
  rect(ctx, x + k % TILE, y + 3 + ((r * 7 + c) % 8), 3, 1, PAL.foam);
}

export function drawFood(ctx, x, y, t, bob = 0) {
  // a sea-sprout with a glowing berry
  const s = Math.sin(t / 420 + x) > 0 ? 0 : 1;
  rect(ctx, x + 6, y + 7, 2, 5, PAL.leaf2);
  bitmap(ctx, x + 2, y + 5 + s, ["gg....gg", ".gG..Gg.", "..gGGg.."], { g: PAL.leaf2, G: PAL.leaf });
  blob(ctx, x + 7, y + 4 - bob, 2, 2, PAL.berry);
  px(ctx, x + 6, y + 3 - bob, PAL.berry2);
  rect(ctx, x + 4, y + 12, 6, 1, PAL.sand2);
}

export function drawThorn(ctx, x, y, t) {
  // a grumpy sea urchin
  const w = Math.sin(t / 300 + y) > 0.6 ? 1 : 0;
  const sp = [[7, 0], [2, 2], [12, 2], [0, 7], [14 - 1, 7], [2, 12], [12, 12], [4, 1], [10, 1], [1, 4], [12, 4]];
  for (const [sx, sy] of sp) {
    const dx = Math.sign(sx - 7), dy = Math.sign(sy - 7);
    px(ctx, x + sx, y + sy, PAL.tip);
    px(ctx, x + sx - dx, y + sy - dy, PAL.spine);
  }
  blob(ctx, x + 7, y + 7, 4, 4, PAL.spine);
  blob(ctx, x + 7, y + 7, 3, 3, PAL.urchin);
  rect(ctx, x + 5, y + 5, 2, 1, PAL.urchin2);
  // tiny cross eyes
  px(ctx, x + 5, y + 7 + w, PAL.tip); px(ctx, x + 9, y + 7 + w, PAL.tip);
}

export function drawHaze(ctx, x, y, t) {
  // something is there, but the critter isn't looking: a soft blur puff
  const o = Math.sin(t / 500 + x * 0.3) > 0 ? 1 : 0;
  blob(ctx, x + 7, y + 7 + o, 3, 2, PAL.haze);
  px(ctx, x + 6, y + 6 + o, PAL.white);
}

// --- the Clawling ----------------------------------------------------------
// Front-facing little lobster, a bit bigger than its tile so it reads as the
// star: round body, big eyes, mitten claws, antennae, tail fan.
// mood: happy | ok | worried | hurt | asleep.  pose: idle | walk | eat | ouch | faint
export function drawCritter(ctx, x, y, { mood = "ok", pose = "idle", t = 0, flash = false } = {}) {
  const frame = Math.floor(t / 260) % 2;
  const asleep = pose === "faint" || mood === "asleep";
  const ox = x - 3, oy = y - 5;                    // sprite box is 20 x 20
  const body = flash ? PAL.white : PAL.body;
  const shade = flash ? PAL.belly : PAL.body3;
  const hi = flash ? PAL.white : PAL.body2;

  if (asleep) {
    blob(ctx, ox + 10, oy + 15, 8, 4, PAL.ink);
    blob(ctx, ox + 10, oy + 15, 7, 3, body);
    rect(ctx, ox + 6, oy + 13, 5, 1, hi);
    rect(ctx, ox + 6, oy + 15, 3, 1, PAL.eye); rect(ctx, ox + 11, oy + 15, 3, 1, PAL.eye);
    px(ctx, ox + 5, oy + 16, PAL.blush); px(ctx, ox + 14, oy + 16, PAL.blush);
    blob(ctx, ox + 1, oy + 14, 2, 2, PAL.ink); blob(ctx, ox + 1, oy + 14, 1, 1, shade);
    blob(ctx, ox + 18, oy + 14, 2, 2, PAL.ink); blob(ctx, ox + 18, oy + 14, 1, 1, shade);
    return;
  }

  const bob = pose === "walk" ? frame : (Math.sin(t / 380) > 0.2 ? 1 : 0);
  const by = oy + bob;
  const squash = pose === "eat" && frame ? 1 : 0;

  // antennae, swaying
  const aw = pose !== "ouch" ? frame : 0;
  for (const [sx, dir] of [[7, -1], [12, 1]]) {
    px(ctx, ox + sx, by + 3, PAL.ink);
    px(ctx, ox + sx + dir, by + 2, PAL.ink);
    px(ctx, ox + sx + dir * (2 + aw), by + 1, PAL.ink);
    px(ctx, ox + sx + dir * (3 + aw), by, PAL.berry);
  }
  // tail fan and little legs
  bitmap(ctx, ox + 6, by + 16, ["kk.kkkk.kk", ".kddkkddk.", "..kkddkk..", "....kk...."], { k: PAL.ink, d: shade });
  const lg = pose === "walk" && frame ? 1 : 0;
  for (const lx of [4, 6]) { px(ctx, ox + lx, by + 15 - lg, PAL.ink); px(ctx, ox + 19 - lx, by + 15 - (1 - lg), PAL.ink); }

  // body
  blob(ctx, ox + 10, by + 10 + squash, 7, 6 - squash, PAL.ink);
  blob(ctx, ox + 10, by + 10 + squash, 6, 5 - squash, body);
  rect(ctx, ox + 6, by + 5 + squash, 4, 1, hi); rect(ctx, ox + 5, by + 6 + squash, 2, 1, hi);
  rect(ctx, ox + 7, by + 14, 7, 1, flash ? PAL.white : PAL.belly);
  rect(ctx, ox + 6, by + 15, 9, 1, shade);

  // mitten claws: raised and open, snapping while it eats, flung up when hurt
  const up = pose === "ouch" ? 3 : (mood === "happy" ? 1 + frame : (mood === "worried" ? -1 : 0));
  const snap = pose === "eat" ? frame : 0;
  const claw = (cx, side) => {
    const cy = by + 6 - up;
    px(ctx, cx - side * 2, cy + 3, PAL.ink); px(ctx, cx - side * 3, cy + 4, PAL.ink); // arm
    blob(ctx, cx, cy, 3, 3, PAL.ink);
    blob(ctx, cx, cy, 2, 2, body);
    px(ctx, cx - 1, cy - 1, hi);
    if (!snap) { px(ctx, cx + side, cy - 2, PAL.ink); px(ctx, cx + side, cy - 3, PAL.sand3); px(ctx, cx + side * 2, cy - 2, PAL.sand3); }
  };
  claw(ox + 1, -1); claw(ox + 18, 1);

  // face
  const ey = by + 8 + squash;
  const eyes = (fn) => { fn(ox + 6); fn(ox + 11); };
  if (mood === "hurt" || pose === "ouch") {
    eyes((ex) => { px(ctx, ex, ey, PAL.eye); px(ctx, ex + 2, ey, PAL.eye); px(ctx, ex + 1, ey + 1, PAL.eye); px(ctx, ex, ey + 2, PAL.eye); px(ctx, ex + 2, ey + 2, PAL.eye); });
    rect(ctx, ox + 9, ey + 4, 2, 2, PAL.eye);
  } else if (mood === "happy") {
    eyes((ex) => { px(ctx, ex, ey + 2, PAL.eye); px(ctx, ex + 1, ey + 1, PAL.eye); px(ctx, ex + 2, ey + 2, PAL.eye); });
    rect(ctx, ox + 8, ey + 4, 4, 1, PAL.eye); rect(ctx, ox + 9, ey + 5, 2, 1, PAL.heart);
  } else {
    const blink = Math.floor(t / 130) % 29 === 0;
    const worried = mood === "worried";
    eyes((ex) => {
      if (blink) { rect(ctx, ex, ey + 2, 3, 1, PAL.eye); return; }
      rect(ctx, ex, ey + (worried ? 1 : 0), 3, worried ? 3 : 4, PAL.eye);
      px(ctx, ex, ey + (worried ? 1 : 0), PAL.white);
      px(ctx, ex + 2, ey + 3, worried ? PAL.eye : PAL.sea2);
    });
    if (worried) { px(ctx, ox + 6, ey - 1, PAL.eye); px(ctx, ox + 7, ey - 2, PAL.eye); px(ctx, ox + 13, ey - 1, PAL.eye); px(ctx, ox + 12, ey - 2, PAL.eye); }
    if (pose === "eat") rect(ctx, ox + 9, ey + 4, 2, 1 + frame, PAL.eye);
    else if (worried) { px(ctx, ox + 8, ey + 5, PAL.eye); px(ctx, ox + 9, ey + 4, PAL.eye); px(ctx, ox + 10, ey + 5, PAL.eye); px(ctx, ox + 11, ey + 4, PAL.eye); }
    else { px(ctx, ox + 8, ey + 4, PAL.eye); px(ctx, ox + 9, ey + 5, PAL.eye); px(ctx, ox + 10, ey + 5, PAL.eye); px(ctx, ox + 11, ey + 4, PAL.eye); }
  }
  if (mood !== "worried") { rect(ctx, ox + 4, ey + 4, 2, 1, PAL.blush); rect(ctx, ox + 14, ey + 4, 2, 1, PAL.blush); }
}

// --- emotes: little bubbles over the critter's head --------------------------
const ICONS = {
  heart: [".h.h.", "hhhhh", "hhhhh", ".hhh.", "..h.."],
  sweat: ["..s..", ".sss.", "sssss", "sssss", ".sss."],
  alert: ["..a..", "..a..", "..a..", ".....", "..a.."],
  question: [".qqq.", "q...q", "...q.", "..q..", "..q.."],
  swap: ["a...q", "aa.qq", ".....", "qq.aa", "q...a"],
  zzz: ["zzzz.", "..z..", ".z...", "zzzz.", "....."],
  note: ["..nnn", "..n.n", "..n..", "nnn..", "nn..."],
  pencil: ["....p", "...pp", "..pp.", ".pp..", "kk..."],
  dots: [".....", ".....", "d.d.d", ".....", "....."],
};
const ICON_COLORS = { h: PAL.heart, s: PAL.sweat, a: PAL.alert, q: PAL.chosen, z: PAL.zzz, n: PAL.note, p: PAL.shown, k: PAL.ink, d: PAL.ink };

export function drawEmote(ctx, x, y, kind, t) {
  if (!ICONS[kind]) return;
  const bob = Math.sin(t / 220) > 0 ? 0 : 1;
  const yy = y - bob;
  rect(ctx, x, yy, 9, 8, PAL.ink);
  rect(ctx, x + 1, yy + 1, 7, 6, PAL.white);
  px(ctx, x + 3, yy + 8, PAL.ink); px(ctx, x + 4, yy + 8, PAL.ink); px(ctx, x + 3, yy + 9, PAL.ink);
  if (kind === "dots") {
    const n = Math.floor(t / 300) % 4;
    for (let i = 0; i < 3; i++) if (i < n) px(ctx, x + 2 + i * 2, yy + 4, PAL.ink);
    return;
  }
  bitmap(ctx, x + 2, yy + 1, ICONS[kind], ICON_COLORS);
}

// Dashed outline around a box, animated (marching ants).
export function ants(ctx, x, y, w, h, color, t, solid = false) {
  const off = Math.floor(t / 120) % 4;
  const on = (i) => solid || ((i + off) % 4) < 2;
  ctx.fillStyle = color;
  for (let i = 0; i < w; i++) { if (on(i)) { ctx.fillRect(x + i, y, 1, 1); ctx.fillRect(x + w - 1 - i, y + h - 1, 1, 1); } }
  for (let i = 0; i < h; i++) { if (on(i)) { ctx.fillRect(x + w - 1, y + i, 1, 1); ctx.fillRect(x, y + h - 1 - i, 1, 1); } }
}
