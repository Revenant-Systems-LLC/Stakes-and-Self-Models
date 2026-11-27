// Animation plan for one critter: which clip plays when, and where the critter is.
//
// Pure functions, no canvas, no clock, no randomness. Give it renderer frames
// (format in viewer/README.md) and it says, for any moment inside a turn, which
// clip is on, which frame of that clip, where the critter stands and which emote
// floats over it. The renderer will ask it what to draw; drawing stays in
// renderer.js and the art stays in the sprite manifest (viewer/docs/animation.md).
//
// Nothing imports this yet. Wiring it into renderer.js is part of the visual pass.
//
//   import { planEpisode, fitPlan, sample } from "./anim.js";
//   const plans = planEpisode(frames, { manifest });
//   const p = fitPlan(plans[i], turnMs);        // squeeze into the time one turn gets
//   const s = sample(p, msSinceTurnStarted, manifest);
//   // s.clip, s.frame, s.facing, s.pos ([row, col], fractional while walking), s.hop (px up), s.emote

export const FACINGS = ["north", "south", "east", "west"];

// Every clip the art has to provide. viewer/manifest.py checks a manifest against this list.
export const CLIPS = [
  "idle", "idle_happy", "idle_worried", "idle_hurt",
  "walk_north", "walk_south", "walk_east", "walk_west",
  "eat", "ouch", "think", "faint", "sleep",
];
// Clips that play once and hand over; the rest loop.
export const ONE_SHOT = ["eat", "ouch", "think", "faint"];
export const EMOTES = ["heart", "alert", "swap", "question", "pencil", "zzz", "dots", "sweat"];

// Times in ms at 1x. These match what renderer.js does today, so the first
// wired-in version looks the same before any art changes.
export const DEFAULT_TIMING = {
  walk: 340,      // one tile of movement (renderer MOVE_MS)
  hop: 4,         // px the critter lifts mid-step
  eat: 560,       // renderer shows the eat pose until 900 ms after the turn starts; 900 - 340
  ouch: 360,      // ouch pose until 700 ms; 700 - 340
  think: 600,     // check-in: a beat of thinking before it settles
  faint: 700,     // tips over, then sleeps
  emote: 1500,    // renderer EMOTE_MS
  frameMs: 260,   // procedural art flips between two frames every 260 ms
};

const EVENT_EMOTE = { eat: "heart", ouch: "alert", swap: "swap", checkin: "question", edit: "pencil", faint: "zzz" };
// Order clips play in when one turn has several events.
const EVENT_CLIP = [["ouch", "ouch"], ["eat", "eat"], ["faint", "faint"], ["checkin", "think"]];

export function facingOf(from, to, prev = "south") {
  if (!from || !to) return prev;
  const dr = to[0] - from[0], dc = to[1] - from[1];
  if (dr === 0 && dc === 0) return prev;
  if (Math.abs(dr) >= Math.abs(dc)) return dr < 0 ? "north" : "south";
  return dc > 0 ? "east" : "west";
}

export function restClip(frame) {
  const pose = frame.critter.pose, mood = frame.critter.mood;
  if (pose === "faint" || mood === "asleep") return "sleep";
  if (mood === "happy") return "idle_happy";
  if (mood === "worried") return "idle_worried";
  if (mood === "hurt") return "idle_hurt";
  return "idle";
}

// Total length of a one-shot clip: from the manifest if the art has it, else the default.
export function clipLength(name, manifest, timing = DEFAULT_TIMING) {
  const c = resolveClip(name, manifest);
  if (c && c.frames && ONE_SHOT.includes(name)) {
    const n = frameCount(c);
    const ms = c.ms;
    if (Array.isArray(ms)) return ms.reduce((a, b) => a + b, 0);
    if (typeof ms === "number" && n > 0) return ms * n;
  }
  return timing[name] ?? timing.frameMs;
}

function frameCount(c) {
  return Array.isArray(c.frames) ? c.frames.length : (typeof c.frames === "number" ? c.frames : 0);
}

// A clip entry, following one level of "mirror" so walk_west can reuse walk_east flipped.
export function resolveClip(name, manifest) {
  const clips = manifest && manifest.clips;
  if (!clips || !clips[name]) return null;
  const c = clips[name];
  if (c.mirror) {
    const base = clips[c.mirror];
    return base && !base.mirror ? { ...base, flip: true } : null;
  }
  return c;
}

// The plan for one frame. prevFacing carries the facing over from the turn before.
export function planFrame(frame, prevFacing = "south", { manifest = null, timing = DEFAULT_TIMING } = {}) {
  const pos = frame.critter.pos;
  const from = frame.critter.from || pos;
  const moved = from[0] !== pos[0] || from[1] !== pos[1];
  const facing = facingOf(from, pos, prevFacing);
  const evs = frame.events || [];
  const segments = [];
  let t = 0;
  if (moved) {
    segments.push({ clip: `walk_${facing}`, start: t, dur: timing.walk, loop: true, move: { from, to: pos, hop: timing.hop } });
    t += timing.walk;
  }
  const clipStart = {};
  for (const [ev, clip] of EVENT_CLIP) {
    if (!evs.includes(ev)) continue;
    const dur = clipLength(clip, manifest, timing);
    clipStart[ev] = t;
    segments.push({ clip, start: t, dur, loop: false });
    t += dur;
  }
  // the emote goes up when the thing it's about happens; events with no clip (swap, edit) show at once
  let emote = null;
  for (const ev of evs) {
    if (!EVENT_EMOTE[ev]) continue;
    emote = { kind: EVENT_EMOTE[ev], start: clipStart[ev] ?? 0, dur: timing.emote };
    break;
  }
  const rest = restClip(frame);
  let idleEmote = null;
  if (frame.waiting) idleEmote = "dots";
  else if (rest === "sleep") idleEmote = "zzz";
  else if (frame.critter.mood === "worried") idleEmote = "sweat";
  return { turn: frame.turn, pos: pos.slice(), facing, segments, rest, total: t, emote, idleEmote, terminal: !!frame.terminal };
}

// Plans for a whole episode. Facing depends on earlier turns, so scrubbing to turn i
// uses plans[i] and gets the same facing as playing up to it.
export function planEpisode(frames, opts = {}) {
  const out = [];
  let facing = opts.startFacing || "south";
  for (const f of frames) {
    const p = planFrame(f, facing, opts);
    out.push(p);
    facing = p.facing;
  }
  return out;
}

// ---- many critters ----------------------------------------------------------
// The study runs one critter per pool. Later worlds will hold many, each with its
// own needs and history. A world frame lists them under "critters", each with an
// id, its own events and the same fields as frame.critter:
//
//   { turn, map, critters: [{ id: "c1", pos, from, mood, pose, events: ["eat"] }, ...] }
//
// A one-critter frame counts as a world with one critter whose id is "main".
export function agentsOf(frame) {
  if (Array.isArray(frame.critters)) return frame.critters;
  return [{ id: "main", ...frame.critter, events: frame.events || [], waiting: frame.waiting }];
}

// One plan per critter per frame: out[i] maps critter id to its plan. Facing is
// tracked per id, so a critter that leaves and comes back keeps the way it faced.
export function planWorld(frames, opts = {}) {
  const facing = new Map();
  const out = [];
  for (const f of frames) {
    const plans = {};
    for (const a of agentsOf(f)) {
      if (a.id == null || plans[a.id]) throw new Error(`turn ${f.turn}: every critter needs a distinct id`);
      const single = { turn: f.turn, terminal: f.terminal, waiting: a.waiting, events: a.events || [],
                       critter: { pos: a.pos, from: a.from, mood: a.mood, pose: a.pose } };
      const p = planFrame(single, facing.get(a.id) || opts.startFacing || "south", opts);
      facing.set(a.id, p.facing);
      plans[a.id] = p;
    }
    out.push(plans);
  }
  return out;
}

// Squeeze a plan into budget ms (one turn at the current speed). Scales every
// segment and the emote start by the same factor, so the order and proportions hold.
export function fitPlan(plan, budget) {
  if (!(budget > 0) || plan.total <= budget) return plan;
  const k = budget / plan.total;
  const segments = plan.segments.map((s) => ({ ...s, start: s.start * k, dur: s.dur * k }));
  const emote = plan.emote ? { ...plan.emote, start: plan.emote.start * k, dur: Math.min(plan.emote.dur, budget) } : null;
  return { ...plan, segments, emote, total: budget, scale: k };
}

const ease = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);

function frameIndex(clip, local, loop, manifest, timing) {
  const c = resolveClip(clip, manifest);
  if (!c) return Math.floor(Math.max(0, local) / timing.frameMs) % 2;
  const n = Math.max(1, frameCount(c));
  const ms = Array.isArray(c.ms) ? c.ms : Array(n).fill(c.ms || timing.frameMs);
  const total = ms.reduce((a, b) => a + b, 0);
  let x = Math.max(0, local);
  if (loop) x %= total;
  else if (x >= total) return n - 1;
  for (let i = 0; i < n; i++) {
    if (x < ms[i]) return i;
    x -= ms[i];
  }
  return n - 1;
}

// What to draw t ms into the turn.
export function sample(plan, t, manifest = null, timing = DEFAULT_TIMING) {
  const seg = plan.segments.find((s) => t >= s.start && t < s.start + s.dur);
  const last = plan.segments[plan.segments.length - 1];
  let pos = plan.pos.slice(), hop = 0;
  if (seg && seg.move) {
    const k = Math.min(1, Math.max(0, (t - seg.start) / seg.dur));
    const e = ease(k);
    pos = [seg.move.from[0] + (seg.move.to[0] - seg.move.from[0]) * e, seg.move.from[1] + (seg.move.to[1] - seg.move.from[1]) * e];
    hop = Math.round(Math.sin(k * Math.PI) * seg.move.hop);
  }
  let clip, local, loop;
  if (seg) { clip = seg.clip; local = t - seg.start; loop = seg.loop; }
  else { clip = plan.rest; local = t - (last ? last.start + last.dur : 0); loop = true; }
  let emote = null;
  if (plan.emote && t >= plan.emote.start && t < plan.emote.start + plan.emote.dur) emote = plan.emote.kind;
  else if (!seg && plan.idleEmote) emote = plan.idleEmote;
  const flip = !!(resolveClip(clip, manifest) || {}).flip;
  return { clip, frame: frameIndex(clip, local, loop, manifest, timing), local, facing: plan.facing, pos, hop, emote, flip };
}
