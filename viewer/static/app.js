// The viewer page: picks an episode, plays it, follows live runs.
import { ClawlingRenderer } from "./renderer.js";
import { buildFrames, describe } from "./frames.js";
import { setSound, play as sfx } from "./sfx.js";

const $ = (id) => document.getElementById(id);
const renderer = new ClawlingRenderer($("world"), $("overlay"));

const S = {
  episodes: [], sig: "", path: null, ep: null, frames: [], idx: 0,
  playing: true, speed: 1, follow: false, timer: null, lastTick: 0,
};
const BASE_MS = 950;          // one turn per ~second at 1x
const NAMES = ["Pinch", "Bisque", "Snip", "Krill", "Nibbles", "Scuttle", "Plink", "Tidbit", "Clicky", "Mussel",
  "Pebble", "Coral", "Bubbles", "Snapper", "Paprika", "Wobble", "Pip", "Clementine", "Barnaby", "Sprocket"];

function nameFor(path) {
  let h = 0;
  for (const ch of path || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return NAMES[h % NAMES.length];
}

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- episodes list
function label(e) {
  const bits = [e.phase || "?", e.tier || e.model || "?", `seed ${e.seed}`, e.label, `${e.turns}t`];
  return (e.running ? "● LIVE  " : "") + bits.join(" · ") + (e.blinded ? "  [blinded]" : "");
}

async function refreshList() {
  let data;
  try { data = await getJSON("/api/episodes"); } catch (e) { status(`can't reach the viewer server (${e.message})`); return; }
  S.episodes = data.episodes || [];
  renderSpend(data.spend || []);
  const sig = S.episodes.map((e) => `${e.path}|${e.running}|${e.turns}`).join(",");
  if (sig !== S.sig) {
    S.sig = sig;
    const sel = $("ep");
    sel.innerHTML = "";
    if (!S.episodes.length) sel.add(new Option(`no episode logs yet in ${data.runs_dir}`, ""));
    for (const e of S.episodes) sel.add(new Option(label(e), e.path));
    if (S.path) sel.value = S.path;
  }
  if (S.follow) {
    const live = S.episodes.find((e) => e.running);
    if (live && live.path !== S.path) await load(live.path, { toEnd: true });
  }
  if (!S.path && S.episodes.length) {
    const fromHash = decodeURIComponent((location.hash.match(/path=([^&]+)/) || [])[1] || "");
    const first = S.episodes.find((e) => e.path === fromHash) || S.episodes.find((e) => e.running) || S.episodes[0];
    await load(first.path, { toEnd: first.running });
  }
}

function renderSpend(list) {
  $("spend").innerHTML = list.filter((s) => s.cap).map((s) => {
    const pct = Math.min(100, (100 * s.spend) / s.cap);
    return `<span class="spendbar" title="${s.phase} spend from the runner's ledger">${s.phase} $${s.spend.toFixed(2)}/$${s.cap}` +
           `<span class="bar"><i style="width:${pct.toFixed(1)}%"></i></span></span>`;
  }).join("");
}

// ---------------------------------------------------------------- one episode
async function load(path, { toEnd = false } = {}) {
  if (!path) return;
  let ep;
  try { ep = await getJSON(`/api/episode?path=${encodeURIComponent(path)}`); } catch (e) { status(`couldn't read ${path} (${e.message})`); return; }
  const changed = path !== S.path;
  S.path = path;
  history.replaceState(null, "", `#path=${encodeURIComponent(path)}`);
  $("ep").value = path;
  apply(ep, changed ? (toEnd ? "end" : "start") : "keep");
}

function apply(ep, where) {
  const atEnd = S.idx >= S.frames.length - 1;
  S.ep = ep;
  S.frames = ep.ready ? buildFrames(ep) : [];
  renderTicks();
  $("scrub").max = Math.max(0, S.frames.length - 1);
  $("live").classList.toggle("hidden", !ep.running);
  if (where === "start") show(0, { quiet: true });
  else if (where === "end") show(Math.max(0, S.frames.length - 1), { quiet: true });
  else if (atEnd && !S.playing) show(S.idx, { quiet: true });
  else if (S.idx > S.frames.length - 1) show(S.frames.length - 1, { quiet: true });
  if (!ep.ready) status("waiting for the episode's first line...");
}

function renderTicks() {
  const n = Math.max(1, S.frames.length - 1);
  $("ticks").innerHTML = S.frames.map((f, i) => {
    const k = f.events.includes("swap") ? "swap" : f.events.includes("edit") ? "edit" : f.events.includes("checkin") ? "check" : null;
    return k ? `<i class="${k}" style="left:${(100 * i) / n}%" title="turn ${f.turn}: ${k}"></i>` : "";
  }).join("");
}

function show(i, { quiet = false } = {}) {
  if (!S.frames.length) return;
  i = Math.max(0, Math.min(S.frames.length - 1, i));
  const f = S.frames[i];
  S.idx = i;
  const waiting = S.ep.running && i === S.frames.length - 1;
  renderer.setFrame({ ...f, waiting });
  const bub = $("overlay").querySelector(".pixel-bubble");
  if (bub) bub.classList.toggle("checkin", f.bubbleKind === "checkin");
  $("scrub").value = i;
  $("turnlbl").textContent = f.terminal ? `end · ${S.frames.length - 1} turns` : `turn ${f.turn} of 48`;
  banner(f);
  vitals(f);
  diary(f);
  feed(i);
  if (!quiet) {
    const moved = f.critter.from && (f.critter.from[0] !== f.critter.pos[0] || f.critter.from[1] !== f.critter.pos[1]);
    const evs = f.events;
    if (evs.includes("ouch")) sfx("ouch"); else if (evs.includes("eat")) sfx("eat"); else if (moved) sfx("step");
    if (evs.includes("swap")) setTimeout(() => sfx("swap"), 120);
    if (evs.includes("edit")) setTimeout(() => sfx("edit"), 120);
    if (evs.includes("checkin")) setTimeout(() => sfx("checkin"), 200);
    if (evs.includes("faint")) sfx("faint");
  }
  const e = S.ep;
  status(`${e.path}${e.running ? "  · live, waiting for the next turn" : ""}${e.map_ok ? "" : "  · map replay unavailable: showing the starting map"}`);
}

function banner(f) {
  const b = $("banner");
  const pick = f.events.includes("swap") ? ["swap", "VIEW SWAPPED"] : f.events.includes("edit") ? ["edit", "DIARY EDITED"] :
    f.events.includes("checkin") ? ["check", "CHECK-IN"] : f.terminal ? ["end", "THE END"] : null;
  if (!pick) { b.classList.add("hidden"); return; }
  b.className = `banner ${pick[0]}`;
  b.textContent = pick[1];
}

function vitals(f) {
  const e = S.ep, h = e.header || {};
  const rec = f.rec || (S.frames[S.frames.length - 2] || {}).rec || {};
  const name = nameFor(e.path);
  $("nameplate").textContent = `${name} the Clawling · ${h.model || "?"}`;
  let body = `<div class="kv"><span>name</span><span>${name}</span><span>model</span><span>${h.model || "?"}</span>` +
    `<span>run</span><span>${h.phase || "?"} · ${h.tier || "?"} · seed ${h.world_seed}</span>` +
    `<span>label</span><span>${h.condition_code}</span>` +
    `<span>status</span><span>${e.running ? "running" : (e.end && e.end.status) || "done"}</span></div>`;
  if (e.blinded) {
    body += `<p class="note">Blinded run: vitals, diary and check-in answers stay hidden until the primary test has run.</p>`;
  } else if (rec.energy != null) {
    const en = rec.energy, he = rec.health;
    body += `<div>Energy ${en}/20</div><div class="meter energy ${en <= 5 ? "low" : ""}">${Array.from({ length: 20 }, (_, k) => `<i class="${k < en ? "on" : ""}"></i>`).join("")}</div>`;
    body += `<div>Health ${he}/10</div><div class="meter health">${Array.from({ length: 10 }, (_, k) => `<i class="${k < he ? "on" : ""}"></i>`).join("")}</div>`;
  } else if (rec.points != null) {
    body += `<div>Points</div><div class="points">${rec.points}</div>`;
  }
  $("vitals-body").innerHTML = body;
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function diary(f) {
  const el = $("diary");
  const e = S.ep;
  if (e.blinded) { el.innerHTML = `<li class="note">Hidden in blinded runs.</li>`; return; }
  const rec = f.rec;
  if (!rec) { el.innerHTML = el.innerHTML; return; }
  const edits = (e.diary_edits || []).filter((x) => x.at_turn <= rec.turn);
  let html = (rec.diary || []).map((d) => {
    const ed = edits.find((x) => x.entry_turn === d.turn);
    const title = ed ? ` title="Edited on turn ${ed.at_turn} (${esc(ed.kind)}). It first wrote: ${esc(ed.before)}"` : "";
    return `<li class="${ed ? "edited" : ""}"${title}><b>t${d.turn}</b>${esc(d.text) || "<i class='note'>(blank)</i>"}</li>`;
  }).join("");
  if (!rec.diary || !rec.diary.length) html = `<li class="note">(empty so far)</li>`;
  if (rec.wrote != null && !rec.checkin) html += `<li class="new"><b>t${rec.turn}</b>${esc(rec.wrote)}</li>`;
  el.innerHTML = html;
  el.scrollTop = el.scrollHeight;
}

function feed(i) {
  const lines = [];
  for (let k = i; k >= 0 && lines.length < 60; k--) {
    const f = S.frames[k];
    for (const d of describe(f, S.ep)) lines.push(`<li class="${d.k}"><b>${f.terminal ? "end" : "t" + f.turn}</b><span>${esc(d.t)}</span></li>`);
  }
  $("feed").innerHTML = lines.join("") || `<li class="note">Nothing yet. It's just waking up.</li>`;
}

function status(t) { $("status").textContent = t; }

// ---------------------------------------------------------------- playback
function setPlaying(p) {
  S.playing = p;
  $("b-play").innerHTML = p ? "&#10074;&#10074;" : "&#9654;";
}

function tick(now) {
  requestAnimationFrame(tick);
  if (!S.playing || !S.frames.length) return;
  if (now - S.lastTick < BASE_MS / S.speed) return;
  S.lastTick = now;
  if (S.idx < S.frames.length - 1) show(S.idx + 1);
  else if (!S.ep.running) setPlaying(false);
}
requestAnimationFrame(tick);

// live: re-read the open episode every second while it's running
setInterval(async () => {
  if (!S.path || !S.ep || !S.ep.running) return;
  try {
    const ep = await getJSON(`/api/episode?path=${encodeURIComponent(S.path)}`);
    if ((ep.turns || []).length !== S.ep.turns.length || ep.running !== S.ep.running) apply(ep, "keep");
  } catch (_) { /* the next poll tries again */ }
}, 1000);
setInterval(refreshList, 3000);

// ---------------------------------------------------------------- controls
$("ep").addEventListener("change", (e) => { setPlaying(true); load(e.target.value); });
$("follow").addEventListener("change", (e) => { S.follow = e.target.checked; if (S.follow) { setPlaying(true); refreshList(); } });
$("fog").addEventListener("change", (e) => renderer.setFog(e.target.checked));
$("sound").addEventListener("change", (e) => { setSound(e.target.checked); if (e.target.checked) sfx("chirp"); });
$("speed").addEventListener("change", (e) => { S.speed = parseFloat(e.target.value); renderer.setSpeed(S.speed); });
$("b-play").addEventListener("click", () => {
  if (!S.playing && S.idx >= S.frames.length - 1 && !(S.ep && S.ep.running)) show(0, { quiet: true });
  setPlaying(!S.playing);
});
$("b-back").addEventListener("click", () => { setPlaying(false); show(S.idx - 1); });
$("b-fwd").addEventListener("click", () => { setPlaying(false); show(S.idx + 1); });
$("b-first").addEventListener("click", () => show(0, { quiet: true }));
$("b-last").addEventListener("click", () => show(S.frames.length - 1, { quiet: true }));
$("scrub").addEventListener("input", (e) => { setPlaying(false); show(parseInt(e.target.value, 10), { quiet: true }); });
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT") return;
  if (e.code === "Space") { e.preventDefault(); $("b-play").click(); }
  if (e.code === "ArrowLeft") $("b-back").click();
  if (e.code === "ArrowRight") $("b-fwd").click();
});

setPlaying(true);
refreshList();
