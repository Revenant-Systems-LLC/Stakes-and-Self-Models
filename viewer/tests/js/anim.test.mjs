// Unit tests for static/anim.js. Run with: node --test viewer/tests/js
// (viewer/tests/test_anim_js.py runs this from pytest when node is installed.)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  CLIPS, ONE_SHOT, EMOTES, DEFAULT_TIMING as T, facingOf, restClip, planFrame, planEpisode, planWorld,
  fitPlan, sample, clipLength, resolveClip, agentsOf,
} from "../../static/anim.js";

const manifest = JSON.parse(readFileSync(new URL("../../static/art/manifest.json", import.meta.url), "utf8"));

const fr = (pos, from, events = [], { critter = {}, ...extra } = {}) => ({
  turn: 1, map: [], view: null, ...extra, critter: { pos, from, mood: "ok", ...critter }, events,
});

test("facing follows the step and holds when it stays", () => {
  assert.equal(facingOf([5, 5], [4, 5]), "north");
  assert.equal(facingOf([5, 5], [6, 5]), "south");
  assert.equal(facingOf([5, 5], [5, 6]), "east");
  assert.equal(facingOf([5, 5], [5, 4]), "west");
  assert.equal(facingOf([5, 5], [5, 5], "east"), "east");
  assert.equal(facingOf(null, [5, 5], "west"), "west");
});

test("rest clip comes from mood and pose", () => {
  assert.equal(restClip(fr([1, 1], null)), "idle");
  assert.equal(restClip(fr([1, 1], null, [], { critter: { mood: "happy" } })), "idle_happy");
  assert.equal(restClip(fr([1, 1], null, [], { critter: { mood: "worried" } })), "idle_worried");
  assert.equal(restClip(fr([1, 1], null, [], { critter: { mood: "hurt" } })), "idle_hurt");
  assert.equal(restClip(fr([1, 1], null, [], { critter: { mood: "ok", pose: "faint" } })), "sleep");
  assert.equal(restClip(fr([1, 1], null, [], { critter: { mood: "asleep" } })), "sleep");
});

test("a step then a snack: walk, then eat, heart goes up when eating starts", () => {
  const p = planFrame(fr([4, 5], [5, 5], ["eat"]), "south", { manifest });
  assert.deepEqual(p.segments.map((s) => s.clip), ["walk_north", "eat"]);
  assert.equal(p.segments[0].start, 0);
  assert.equal(p.segments[1].start, T.walk);
  assert.equal(p.total, T.walk + clipLength("eat", manifest));
  assert.deepEqual(p.emote, { kind: "heart", start: T.walk, dur: T.emote });
  assert.equal(p.facing, "north");
});

test("standing still makes no walk segment and keeps facing", () => {
  const p = planFrame(fr([5, 5], [5, 5], ["swap"]), "west");
  assert.equal(p.segments.length, 0);
  assert.equal(p.facing, "west");
  assert.equal(p.total, 0);
  assert.deepEqual(p.emote, { kind: "swap", start: 0, dur: T.emote });
});

test("several events play in a fixed order", () => {
  const p = planFrame(fr([5, 5], [5, 4], ["checkin", "faint", "ouch"]), "south");
  assert.deepEqual(p.segments.map((s) => s.clip), ["walk_east", "ouch", "faint", "think"]);
  for (let i = 1; i < p.segments.length; i++)
    assert.equal(p.segments[i].start, p.segments[i - 1].start + p.segments[i - 1].dur);
  assert.ok(p.segments.slice(1).every((s) => s.loop === false));
});

test("one-shot clip length follows the manifest, and falls back to defaults", () => {
  assert.equal(clipLength("eat", manifest), 2 * 280);
  assert.equal(clipLength("eat", null), T.eat);
  const m = { clips: { eat: { frames: [[0, 0], [1, 0], [2, 0]], ms: [100, 50, 25], loop: false } } };
  assert.equal(clipLength("eat", m), 175);
});

test("mirrored clips resolve to their base, flipped", () => {
  const c = resolveClip("walk_west", manifest);
  assert.equal(c.flip, true);
  assert.equal(c.ms, manifest.clips.walk_east.ms);
  assert.equal(resolveClip("walk_west", { clips: { walk_west: { mirror: "nope" } } }), null);
});

test("plans for an episode carry facing across turns", () => {
  const frames = [fr([5, 5], null), fr([5, 6], [5, 5]), fr([5, 6], [5, 6]), fr([4, 6], [5, 6])];
  const plans = planEpisode(frames);
  assert.deepEqual(plans.map((p) => p.facing), ["south", "east", "east", "north"]);
});

test("fitPlan squeezes a long turn into the budget and keeps the order", () => {
  const p = planFrame(fr([5, 5], [5, 4], ["ouch", "eat", "checkin"]), "south");
  const f = fitPlan(p, 475);
  assert.ok(Math.abs(f.total - 475) < 1e-9);
  const last = f.segments[f.segments.length - 1];
  assert.ok(Math.abs(last.start + last.dur - 475) < 1e-9);
  assert.deepEqual(f.segments.map((s) => s.clip), p.segments.map((s) => s.clip));
  assert.equal(fitPlan(p, 10_000), p);  // fits already: unchanged
});

test("sample walks the critter from tile to tile with a hop", () => {
  const p = planFrame(fr([5, 6], [5, 5]), "south");
  const a = sample(p, 0), mid = sample(p, T.walk / 2), b = sample(p, T.walk + 1);
  assert.deepEqual(a.pos, [5, 5]);
  assert.equal(a.hop, 0);
  assert.equal(mid.clip, "walk_east");
  assert.ok(Math.abs(mid.pos[1] - 5.5) < 1e-9);
  assert.equal(mid.hop, T.hop);
  assert.deepEqual(b.pos, [5, 6]);
  assert.equal(b.clip, "idle");
});

test("sample picks frames by the manifest timing", () => {
  const p = planFrame(fr([5, 5], [5, 5], ["eat"]), "south", { manifest });
  assert.equal(sample(p, 0, manifest).frame, 0);
  assert.equal(sample(p, 279, manifest).frame, 0);
  assert.equal(sample(p, 281, manifest).frame, 1);
  // after the one-shot, the rest clip loops: idle is 2 x 260
  const after = p.total;
  assert.equal(sample(p, after + 10, manifest).clip, "idle");
  assert.equal(sample(p, after + 270, manifest).frame, 1);
  assert.equal(sample(p, after + 530, manifest).frame, 0);
});

test("idle emotes show once the turn's action is over", () => {
  const p = planFrame(fr([5, 5], [5, 5], [], { critter: { mood: "worried" } }), "south");
  assert.equal(sample(p, 50).emote, "sweat");
  const w = planFrame(fr([5, 5], [5, 5], [], { waiting: true }), "south");
  assert.equal(sample(w, 50).emote, "dots");
  const s = planFrame(fr([5, 5], [5, 5], [], { critter: { mood: "asleep" } }), "south");
  assert.equal(sample(s, 50).emote, "zzz");
});

test("sample is pure: same input, same output", () => {
  const p = planFrame(fr([5, 6], [5, 5], ["eat"]), "south", { manifest });
  for (const t of [0, 100, 340, 500, 2000]) assert.deepEqual(sample(p, t, manifest), sample(p, t, manifest));
});

test("many critters: each keeps its own facing and events", () => {
  const frames = [
    { turn: 0, critters: [{ id: "a", pos: [1, 1], from: null, mood: "ok" }, { id: "b", pos: [3, 3], from: null, mood: "ok" }] },
    { turn: 1, critters: [{ id: "a", pos: [1, 2], from: [1, 1], mood: "ok", events: ["eat"] },
                          { id: "b", pos: [2, 3], from: [3, 3], mood: "ok" }] },
    { turn: 2, critters: [{ id: "a", pos: [1, 2], from: [1, 2], mood: "happy" }] },
    { turn: 3, critters: [{ id: "a", pos: [1, 2], from: [1, 2], mood: "ok" }, { id: "b", pos: [2, 3], from: [2, 3], mood: "ok" }] },
  ];
  const w = planWorld(frames);
  assert.deepEqual(w[1].a.segments.map((s) => s.clip), ["walk_east", "eat"]);
  assert.deepEqual(w[1].b.segments.map((s) => s.clip), ["walk_north"]);
  assert.equal(w[2].b, undefined);
  assert.equal(w[3].b.facing, "north");  // b was away for a turn and kept its facing
  assert.throws(() => planWorld([{ turn: 0, critters: [{ id: "a", pos: [0, 0] }, { id: "a", pos: [1, 1] }] }]));
});

test("a one-critter frame is a world with one critter", () => {
  const f = fr([4, 5], [5, 5], ["eat"]);
  const [a] = agentsOf(f);
  assert.equal(a.id, "main");
  const w = planWorld([f]);
  assert.deepEqual(w[0].main.segments, planFrame(f, "south").segments);
});

test("clip lists are what the manifest names", () => {
  assert.deepEqual(Object.keys(manifest.clips).sort(), [...CLIPS].sort());
  assert.deepEqual(Object.keys(manifest.emotes).sort(), [...EMOTES].sort());
  for (const c of ONE_SHOT) assert.equal(manifest.clips[c].loop, false);
});
