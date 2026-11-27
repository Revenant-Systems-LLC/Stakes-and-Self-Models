// Turns an episode (as /api/episode sends it) into renderer frames.
// This is the only place that knows the log format. The renderer only sees frames.

const STEP = { north: [-1, 0], south: [1, 0], east: [0, 1], west: [0, -1] };
const N = 11;

function mood(rec, prev, blinded) {
  if (prev && prev.thorn) return "hurt";
  if (blinded) return prev && prev.ate ? "happy" : "ok";
  if (rec.energy != null) {
    if (rec.energy <= 5 || rec.health <= 3) return "worried";
    if (rec.energy >= 14 && rec.health >= 7) return "happy";
    return "ok";
  }
  return prev && prev.ate ? "happy" : "ok";
}

function clip(s, n = 110) { return s && s.length > n ? s.slice(0, n - 1) + "…" : s; }

export function answerOf(rec) {
  if (rec.checkin_answer != null && rec.checkin_answer !== "") return rec.checkin_answer;
  return rec.answer_field || null;
}

export function buildFrames(ep) {
  const turns = ep.turns || [];
  const blinded = !!ep.blinded;
  const frames = [];
  for (let i = 0; i < turns.length; i++) {
    const rec = turns[i], prev = turns[i - 1];
    const events = [];
    if (prev && prev.ate) events.push("eat");
    if (prev && prev.thorn) events.push("ouch");
    if (rec.tamper_type === "attention_swap") events.push("swap");
    if (rec.tamper_type === "diary_edit") events.push("edit");
    if (rec.checkin) events.push("checkin");
    let bubble = null, bubbleKind = "say";
    if (rec.checkin) {
      bubbleKind = "checkin";
      bubble = blinded ? "(check-in answer hidden while blinded)" : (answerOf(rec) ? `“${clip(answerOf(rec))}”` : "(no answer)");
    } else if (!blinded && rec.wrote) bubble = clip(rec.wrote);
    frames.push({
      turn: rec.turn,
      map: rec.map || ep.start_map,
      critter: { pos: rec.position, from: prev ? prev.position : null, mood: mood(rec, prev, blinded) },
      view: { chosen: rec.chosen_region, shown: rec.shown_region },
      events, bubble, bubbleKind,
      rec,
    });
  }
  // after the last move: where it ended up and how it ended
  if (ep.end && turns.length) {
    const last = turns[turns.length - 1];
    const d = STEP[last.move] || [0, 0];
    const r = Math.min(N - 1, Math.max(0, last.position[0] + d[0]));
    const c = Math.min(N - 1, Math.max(0, last.position[1] + d[1]));
    let map = (last.map || ep.start_map).slice();
    if (last.ate) map = map.map((row, ri) => ri === r ? row.slice(0, c) + "." + row.slice(c + 1) : row);
    const fainted = !blinded && (last.fainted || ep.end.fainted);
    const events = [];
    if (last.ate) events.push("eat");
    if (last.thorn) events.push("ouch");
    if (fainted) events.push("faint");
    frames.push({
      turn: last.turn + 1, terminal: true, map,
      critter: { pos: [r, c], from: last.position, mood: fainted ? "asleep" : (last.thorn ? "hurt" : "happy"), pose: fainted ? "faint" : "idle" },
      view: null, events, bubble: null, rec: null,
    });
  }
  return frames;
}

// One line per thing that happened on a turn, for the feed. Newest first is up to the page.
export function describe(frame, ep) {
  const out = [];
  const rec = frame.rec;
  const blinded = !!ep.blinded;
  for (const ev of frame.events) {
    if (ev === "eat") out.push({ k: "eat", t: "ate a sea-sprout" });
    if (ev === "ouch") out.push({ k: "ouch", t: blinded ? "stepped on an urchin" : (frame.terminal ? "stepped on an urchin" : (rec && rec.energy != null ? "stepped on an urchin, ouch (-5 health)" : "stepped on an urchin (-5 points)")) });
    if (ev === "swap") out.push({ k: "swap", t: `the game swapped its view: it looked at region ${rec.chosen_region}, saw region ${rec.shown_region}` });
    if (ev === "edit") {
      const e = (ep.diary_edits || []).find((x) => x.at_turn === rec.turn);
      out.push({ k: "edit", t: e ? `the game rewrote its diary line from turn ${e.entry_turn} (${(e.kind || "").replace("_", " ")})` : "the game rewrote a diary line" });
    }
    if (ev === "checkin") out.push({ k: "check", t: blinded ? "check-in asked, answer hidden while blinded" : `check-in: “${answerOf(rec) || "no answer"}”` });
    if (ev === "faint") out.push({ k: "end", t: "fainted" });
  }
  if (frame.terminal) out.push({ k: "end", t: blinded ? "episode over" : (ep.end && ep.end.fainted ? "episode over: it fainted" : "episode over: made it to the end") });
  if (rec && rec.reply_valid === false) out.push({ k: "ouch", t: "bad reply, counted as stay" });
  else if (rec && rec.move) out.push({ k: "move", t: STEP[rec.move] ? `walked ${rec.move}` : rec.move === "eat" ? "tried to eat" : "stayed put" });
  return out;
}
