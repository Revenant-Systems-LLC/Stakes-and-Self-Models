# Clawlings viewer

A small local web page for watching Clawlings episodes. It replays finished episode logs turn by turn, follows an episode live while the runner writes it, and follows the preregistration's blinding rules for confirmatory runs.

It needs nothing beyond the study's own Python environment. The server is Python's standard library, and the page is plain HTML and JavaScript with no build step.

## Start it

On Yggdrasil, from the repo folder:

```
M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m viewer.server
```

Then open http://127.0.0.1:8765 in a browser. The server reads logs from `runs_dir` in `runner/config.json` and prints a status line every 30 seconds so you can tell it's alive. Ctrl+C stops it. It only listens on 127.0.0.1, so nothing outside the machine can reach it.

Options:

- `--runs PATH` reads logs from another folder.
- `--port N` uses another port.
- `--show-blinded` shows confirmatory logs in full. Use it only after the primary test has run.

## What you see

- The tide pool: the 11x11 world, the critter, sea sprouts (food) and urchins (thorns). The map for each turn is rebuilt by replaying the logged moves with the episode's seed, and checked against the logged position every turn. If the two ever disagree, the page says so and shows the starting map only.
- The cyan dashed box is the region the critter chose to look at next. When the game swaps its attention, an amber box shows the region it was actually shown.
- "What it sees" dims everything outside the critter's 9x9 view and hazes the parts it didn't get a clear look at.
- Side panels: meters, the diary (with tampered entries marked), and a feed of what happened.
- The timeline: play, pause, step, speed and scrubbing, with ticks for attention swaps (amber), diary edits (pink) and check-ins (green). Space plays and pauses, and the arrow keys step.
- Follow live jumps to the newest running episode and keeps up with it. The page re-reads a running log about once a second.
- Sound is off by default.

## Live mode

The runner flushes the log after every line (world/log.py), so a log can be read while it's being written. The server decodes whatever is on disk and drops the last half-written line. Nothing extra has to run besides the server. Start it, start the runner as usual, and tick Follow live.

## Blinding

A log counts as blinded if its condition label isn't `stakes` or `no_stakes`, or if its header's phase is listed in `blinded_phases` in `runner/config.json`. For a blinded log the server strips everything that would name the condition before anything reaches the browser: check-in answers, energy, health, points, faints, diary text, raw replies, edit text, and per-turn tokens and cost. Cost goes too because the two system prompts differ in length, so cost tracks the condition. What stays is the map, the path the critter walked, what it ate or stepped on, which region it chose and which it was shown, and when tampers and check-ins happened. Tamper timing comes from the seed and is the same for both twins, so it says nothing about the condition. Spend is shown as phase totals against the cap, never per episode.

Pilot runs and the Fable and Mythos tiers are shown in full.

## Demo logs

To try it without the study's runs (no API calls, no credit):

```
python -m viewer.make_demo
python -m viewer.server --demo
```

`make_demo` plays a scripted greedy critter through the real world code and writes two pilot pairs and one blinded confirmatory pair to `viewer/_demo_runs` (git-ignored). For live mode, run this in a second window and tick Follow live:

```
python -m viewer.make_demo --live
```

## Tests

```
python -m pytest viewer/tests
```

The tests play short scripted episodes and check the map replay, the blinded stripping, reading a log mid-write, and that the server refuses paths outside the runs folder.

## How it's built

The pieces are kept apart so the drawing code never touches logs or blinding.

| File | Job |
| --- | --- |
| `logread.py` | Reads logs (including running ones), rebuilds maps, applies blinding |
| `server.py` | Local HTTP server: `/api/episodes`, `/api/episode?path=`, static files |
| `static/frames.js` | Turns an episode into frames. The only browser code that knows the log format |
| `static/renderer.js` | Draws frames: animation, particles, emotes, speech bubble |
| `static/sprites.js` | Pixel art for the critter, tiles and emotes |
| `static/sfx.js` | Small synthesized sounds |
| `static/app.js` | Page controls, playback and polling |

### Frame format

The renderer is a standalone component. It takes one frame per turn and draws it, animating from the previous frame. It doesn't know where frames come from, so anything that can produce them (a log, a test script, or later a live critter) can drive it.

```js
import { ClawlingRenderer } from "./renderer.js";
const r = new ClawlingRenderer(canvas, overlayDiv);  // overlay is optional, it holds the speech bubble
r.setFrame(frame);   // animate from the last frame to this one
r.setFog(true);      // show only what the critter can see
r.setSpeed(2);       // animation speed multiplier
```

A frame:

```js
{
  turn: 12,                      // number, shown on screen
  map: ["T...F......", ...],     // 11 strings of 11 chars: "." sand, "F" food, "T" thorn
  critter: {
    pos: [row, col],             // where it ends up this turn
    from: [row, col],            // where it was, for the hop animation (same as pos if it stayed)
    mood: "ok",                  // "ok" | "happy" | "worried" | "hurt" | "asleep"
    pose: "idle"                 // optional: "idle" | "faint". Walk, eat and ouch poses come from movement and events
  },
  view: { chosen: 4, shown: 7 }, // 3x3 regions of its 9x9 view, 0-8 row-major, 4 = centre; null to hide
  events: ["eat", "swap"],       // any of "eat" | "ouch" | "swap" | "edit" | "checkin" | "faint"
  bubble: "a sprout! mine.",     // speech bubble text, or null
  bubbleKind: "say",             // "say" | "checkin"
  terminal: false                // true on the closing frame after the last turn
}
```

Events trigger the one-off effects (bursts, screen shake, emotes). Mood drives the face and idle animation. The renderer ignores any other fields, so `frames.js` also hangs the raw turn record on `frame.rec` for the side panels.
