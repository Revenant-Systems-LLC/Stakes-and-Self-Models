// ClawlingRenderer: draws one critter's tide pool from a frame object.
//
// State in, pixels out. It knows nothing about logs, servers or blinding:
// give it frames (format in viewer/README.md) and it animates between them.
// A future game client can drive it with frames of its own.
//
//   const r = new ClawlingRenderer(canvas, overlayDiv);
//   r.setFrame(frame);          // animate from the last frame to this one
//   r.setFog(true);             // show only what the critter can see
//   r.setSpeed(2);              // animation speed multiplier

import { TILE, PAL, rect, px, drawSand, drawSea, drawFood, drawThorn, drawHaze, drawCritter, drawEmote, ants } from "./sprites.js";

const N = 11;           // world is N x N
const B = 1;            // border tiles of sea around it
const SIZE = (N + 2 * B) * TILE;
const MOVE_MS = 340;
const EMOTE_MS = 1500;

const EVENT_EMOTE = { eat: "heart", ouch: "alert", swap: "swap", checkin: "question", edit: "pencil", faint: "zzz" };

export class ClawlingRenderer {
  constructor(canvas, overlay = null) {
    this.canvas = canvas;
    canvas.width = SIZE;
    canvas.height = SIZE;
    this.ctx = canvas.getContext("2d");
    this.ctx.imageSmoothingEnabled = false;
    this.overlay = overlay;
    this.bubbleEl = null;
    if (overlay) {
      this.bubbleEl = document.createElement("div");
      this.bubbleEl.className = "pixel-bubble hidden";
      overlay.appendChild(this.bubbleEl);
    }
    this.frame = null;
    this.prev = null;
    this.changedAt = 0;
    this.fog = false;
    this.speed = 1;
    this.particles = [];
    this.shakeUntil = 0;
    this._loop = this._loop.bind(this);
    requestAnimationFrame(this._loop);
  }

  static get size() { return SIZE; }

  setFog(on) { this.fog = !!on; }
  setSpeed(s) { this.speed = Math.max(0.25, s || 1); }
  clear() { this.frame = null; this.prev = null; this.particles = []; this._setBubble(null); }

  setFrame(frame) {
    const now = performance.now();
    this.prev = this.frame;
    this.frame = frame;
    this.changedAt = now;
    const [cx, cy] = this._cell(frame.critter.pos);
    for (const ev of frame.events || []) {
      if (ev === "eat") this._burst(cx + 7, cy + 4, [PAL.berry, PAL.berry2, PAL.note], 10);
      if (ev === "ouch") { this._burst(cx + 7, cy + 7, [PAL.heart, PAL.white], 12); this.shakeUntil = now + 260; }
      if (ev === "swap") this._burst(cx + 7, cy, [PAL.shown, PAL.chosen], 8);
    }
    this._setBubble(frame.bubble);
  }

  // ---- internals ----------------------------------------------------------
  _cell([r, c]) { return [(c + B) * TILE, (r + B) * TILE]; }

  _burst(x, y, colors, n) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, s = 0.4 + Math.random() * 0.9;
      this.particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 0.6, life: 30 + Math.random() * 20,
                            c: colors[i % colors.length] });
    }
  }

  _setBubble(text) {
    if (!this.bubbleEl) return;
    if (!text) { this.bubbleEl.classList.add("hidden"); return; }
    this.bubbleEl.textContent = text;
    this.bubbleEl.classList.remove("hidden");
  }

  _critterXY(now) {
    const f = this.frame;
    const [tx, ty] = this._cell(f.critter.pos);
    const from = f.critter.from;
    if (!from) return [tx, ty, 0];
    const k = Math.min(1, (now - this.changedAt) * this.speed / MOVE_MS);
    const [fx, fy] = this._cell(from);
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    const hop = (fx !== tx || fy !== ty) ? Math.round(Math.sin(k * Math.PI) * 4) : 0;
    return [Math.round(fx + (tx - fx) * e), Math.round(fy + (ty - fy) * e) - hop, k];
  }

  _loop(now) {
    requestAnimationFrame(this._loop);
    const ctx = this.ctx;
    const f = this.frame;
    ctx.save();
    if (now < this.shakeUntil) ctx.translate(Math.random() < 0.5 ? -1 : 1, Math.random() < 0.5 ? -1 : 0);
    // sea border and sand
    for (let r = -B; r < N + B; r++)
      for (let c = -B; c < N + B; c++) {
        const x = (c + B) * TILE, y = (r + B) * TILE;
        if (r < 0 || c < 0 || r >= N || c >= N) drawSea(ctx, x, y, r, c, now);
        else drawSand(ctx, x, y, r, c, now);
      }
    if (!f) { ctx.restore(); return; }

    const [pr, pc] = f.critter.pos;
    const inWin = (r, c) => Math.abs(r - pr) <= 4 && Math.abs(c - pc) <= 4;
    const regionOf = (r, c) => Math.floor((r - pr + 4) / 3) * 3 + Math.floor((c - pc + 4) / 3);
    const shown = f.view ? f.view.shown : null;

    // food and urchins
    for (let r = 0; r < N; r++) {
      const row = f.map[r] || "";
      for (let c = 0; c < N; c++) {
        const ch = row[c];
        if (ch !== "F" && ch !== "T") continue;
        const x = (c + B) * TILE, y = (r + B) * TILE;
        if (this.fog && f.view) {
          if (!inWin(r, c)) continue;
          if (regionOf(r, c) !== shown) { drawHaze(ctx, x, y, now); continue; }
        }
        if (ch === "F") drawFood(ctx, x, y, now); else drawThorn(ctx, x, y, now);
      }
    }

    // fog outside the critter's 9x9 window
    if (this.fog && f.view) {
      ctx.fillStyle = PAL.fog;
      for (let r = 0; r < N; r++) for (let c = 0; c < N; c++)
        if (!inWin(r, c)) ctx.fillRect((c + B) * TILE, (r + B) * TILE, TILE, TILE);
    }

    // the region it chose to look at, and the one the game showed instead
    if (f.view) {
      const box = (k) => {
        const r0 = pr - 4 + Math.floor(k / 3) * 3, c0 = pc - 4 + (k % 3) * 3;
        const ra = Math.max(0, r0), rb = Math.min(N, r0 + 3), ca = Math.max(0, c0), cb = Math.min(N, c0 + 3);
        if (ra >= rb || ca >= cb) return null;
        return [(ca + B) * TILE, (ra + B) * TILE, (cb - ca) * TILE, (rb - ra) * TILE];
      };
      const ch = box(f.view.chosen);
      if (f.view.shown !== f.view.chosen) {
        const sh = box(f.view.shown);
        if (sh) {
          const pulse = 0.18 + 0.12 * Math.sin(now / 160);
          ctx.fillStyle = `rgba(255,180,58,${pulse.toFixed(3)})`;
          ctx.fillRect(sh[0], sh[1], sh[2], sh[3]);
          ants(ctx, sh[0], sh[1], sh[2], sh[3], PAL.shown, now, true);
          ants(ctx, sh[0] + 1, sh[1] + 1, sh[2] - 2, sh[3] - 2, PAL.shown, now, true);
        }
      }
      if (ch) {
        ctx.fillStyle = "rgba(94,240,255,0.13)";
        ctx.fillRect(ch[0], ch[1], ch[2], ch[3]);
        ants(ctx, ch[0], ch[1], ch[2], ch[3], PAL.chosen, now);
      }
    }

    // the critter
    const [x, y, k] = this._critterXY(now);
    const since = (now - this.changedAt) * this.speed;
    const evs = f.events || [];
    let pose = f.critter.pose || "idle";
    if (k < 1 && f.critter.from && (f.critter.from[0] !== pr || f.critter.from[1] !== pc)) pose = "walk";
    else if (evs.includes("ouch") && since < 700) pose = "ouch";
    else if (evs.includes("eat") && since < 900) pose = "eat";
    rect(ctx, x + 1, y + TILE + 1, 13, 1, "rgba(36,18,46,0.22)"); rect(ctx, x + 3, y + TILE + 2, 9, 1, "rgba(36,18,46,0.14)"); // shadow
    drawCritter(ctx, x, y, { mood: f.critter.mood, pose, t: now, flash: pose === "ouch" && Math.floor(since / 90) % 2 === 0 });

    // emote over its head
    let emote = null;
    if (since < EMOTE_MS) for (const ev of evs) if (EVENT_EMOTE[ev]) { emote = EVENT_EMOTE[ev]; break; }
    if (!emote && f.emote) emote = f.emote;
    if (!emote && f.waiting) emote = "dots";
    if (!emote && f.critter.mood === "worried" && Math.floor(now / 2400) % 2 === 0) emote = "sweat";
    if (!emote && f.critter.mood === "asleep") emote = "zzz";
    if (emote) drawEmote(ctx, x + 3, y - 15, emote, now);

    // ambient bubbles rising out of the sea
    if (Math.random() < 0.04) {
      const side = Math.floor(Math.random() * 4), p = Math.random() * SIZE;
      const [bx, bY] = side === 0 ? [p, SIZE - 2] : side === 1 ? [p, TILE - 2] : side === 2 ? [3 + Math.random() * 8, p] : [SIZE - 4 - Math.random() * 8, p];
      this.particles.push({ x: bx, y: bY, vx: 0, vy: -0.25, life: 24, c: PAL.foam, bubble: true });
    }
    // particles
    this.particles = this.particles.filter((p) => p.life > 0);
    for (const p of this.particles) {
      p.x += p.vx + (p.bubble ? Math.sin(p.life / 3) * 0.2 : 0); p.y += p.vy; if (!p.bubble) p.vy += 0.04; p.life -= 1;
      px(ctx, p.x, p.y, p.c);
    }
    ctx.restore();

    // keep the speech bubble over the critter
    if (this.bubbleEl && !this.bubbleEl.classList.contains("hidden")) {
      const left = ((x + TILE / 2) / SIZE) * 100, top = (y / SIZE) * 100;
      this.bubbleEl.style.left = `${left}%`;
      this.bubbleEl.style.top = `${top}%`;
      this.bubbleEl.classList.toggle("below", y < 3 * TILE);
      this.bubbleEl.classList.toggle("left", x > (N - 2) * TILE);
      this.bubbleEl.classList.toggle("right", x < 3 * TILE);
    }
  }
}
