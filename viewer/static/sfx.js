// Tiny square-wave chirps, made on the fly. Off until the page turns them on.
let ac = null;
let on = false;

export function setSound(enabled) {
  on = !!enabled;
  if (on && !ac) ac = new (window.AudioContext || window.webkitAudioContext)();
  if (on && ac.state === "suspended") ac.resume();
}

function tone(freq, start, dur, vol = 0.05, type = "square", slide = 0) {
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, ac.currentTime + start);
  if (slide) o.frequency.linearRampToValueAtTime(freq + slide, ac.currentTime + start + dur);
  g.gain.setValueAtTime(vol, ac.currentTime + start);
  g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + start + dur);
  o.connect(g).connect(ac.destination);
  o.start(ac.currentTime + start);
  o.stop(ac.currentTime + start + dur + 0.02);
}

const SOUNDS = {
  step: () => tone(520 + Math.random() * 120, 0, 0.05, 0.02),
  eat: () => { tone(660, 0, 0.07); tone(880, 0.07, 0.07); tone(1175, 0.14, 0.1); },
  ouch: () => tone(420, 0, 0.22, 0.06, "sawtooth", -260),
  swap: () => { tone(500, 0, 0.09, 0.04, "triangle", 300); tone(800, 0.1, 0.09, 0.04, "triangle", -300); },
  checkin: () => { tone(740, 0, 0.08, 0.04, "triangle"); tone(988, 0.1, 0.12, 0.04, "triangle"); },
  edit: () => { tone(300, 0, 0.05, 0.03); tone(300, 0.08, 0.05, 0.03); },
  faint: () => tone(440, 0, 0.6, 0.05, "triangle", -300),
  chirp: () => { tone(1200, 0, 0.04, 0.025, "triangle", 400); tone(1500, 0.06, 0.04, 0.02, "triangle", 300); },
};

export function play(name) {
  if (!on || !ac || !SOUNDS[name]) return;
  try { SOUNDS[name](); } catch (_) { /* audio is decoration only */ }
}
