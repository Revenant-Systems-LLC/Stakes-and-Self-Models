# Animation pass: design

This is the non-visual half of the viewer's animation pass. It covers the code that decides what the critter is doing at every moment, the contract between the study's logs and the viewer, and the slot the original art drops into. Nothing here changes what the viewer looks like today. `static/anim.js` is not imported by the page yet. Wiring it in is part of the visual pass, which waits on David.

## Where this is heading

The end goal is a world that AI agents live in, with the feel of a small pet sim: creatures you watch, who get hungry, get hurt, sleep and react. The study's tide pool is the first and smallest version, one critter in an 11x11 pool. Later worlds will hold many agents with lasting needs and histories, and get more complex over time, so the same viewer can be used for further research. The code is shaped for that:

- Plans are per critter. `planWorld()` takes frames that list many critters by id and keeps each one's facing and events apart. A one-critter frame is a world with one critter, id `"main"`.
- The renderer only ever sees frames, and the art only ever comes from the manifest. A new world type needs a new frame builder, not a new renderer.
- The contract checks logs field by field, so research logs stay trustworthy as the world grows.

## Clean-room rules

The genre and feel follow pet sims in the vein David named. The rules for how close we get:

1. Mechanics may be similar. They are rebuilt only from observed gameplay behavior (watching it played, David's own clips) and public descriptions. Never from the game's code, decompiled or otherwise, and never from its files or data.
2. Creatures, names, art, sounds and look are all David's own. None of it is copied, traced or adapted from any other game. Until his art exists the code uses neutral placeholders (`idle`, `walk_east`, `eat`), and the current pixel art in `static/sprites.js` stays as is.
3. Every sprite sheet carries a provenance line in the manifest saying who drew it and from what. `python -m viewer.manifest` fails a sheet without one, so art of unknown origin can't slip in.
4. Tools for observing behavior (such as David's fork of Reverse-Engineer-Anything) produce notes about behavior: timings, states, what triggers what. Those notes can shape this code. Their output is never pasted in as code or assets.
5. The timings in `anim.js` today were taken from this project's own renderer, not from any other game.

## The pieces

| Piece | File | Job |
| --- | --- | --- |
| Data contract | `viewer/contract.py` | States and checks what an episode from `/api/episode` must look like, including the blinding rules |
| Animation model | `viewer/static/anim.js` | Turns frames into timed clip plans and answers "what is on screen at t ms" |
| Sprite manifest | `viewer/static/art/manifest.json` | Names every clip and emote, their frames and timing, and where the art came from |
| Manifest checker | `viewer/manifest.py` | Checks a manifest before new art is committed |

The flow, left to right: log on disk, `logread.episode_view()`, contract check, `frames.js` builds frames, `anim.js` plans them, `renderer.js` draws using the manifest.

## Data contract

`contract.check_episode(view)` returns a list of plain-sentence problems, empty when the episode is good. It checks:

- the top-level keys and the header fields the server shows,
- every map is 11 rows of 11 characters from `.`, `F`, `T`,
- positions are inside the pool, regions are 0 to 8, moves are known,
- turns count up by one and each position follows from the last move (a move into the edge leaves the critter in place),
- a running episode has no end line,
- for a blinded episode, every turn carries only the keys on `logread.BLIND_TURN_KEEP` plus the map, the end line only `BLIND_END_KEEP`, and there is no diary edit text.

The blinded rule is an allow list on purpose. If the runner grows a new turn field, it is stripped from blinded logs until someone adds it to the keep list knowingly, and the contract test fails if it ever slips through.

## Animation model

`planFrame(frame, prevFacing, { manifest })` gives one turn's plan:

- `segments`: clips in the order they play, each with `start` and `dur` in ms at 1x. A move comes first (`walk_<facing>`, with the tween from tile to tile and a small hop), then event clips in a fixed order: `ouch`, `eat`, `faint`, `think` (check-in).
- `rest`: the looping clip once the segments are done, from mood and pose: `idle`, `idle_happy`, `idle_worried`, `idle_hurt` or `sleep`.
- `emote`: the bubble over its head, shown when the event it belongs to starts (the heart when eating starts, not when the walk starts). Swaps and diary edits have no clip, so their emote shows at once.
- `idleEmote`: shown during the rest clip: dots while waiting on a live reply, zzz asleep, sweat when worried.
- `facing`: from the step taken, or carried over from the turn before when it stays put.

`planEpisode(frames)` plans a whole episode, carrying facing along, so scrubbing to any turn gives the same result as playing up to it.

`fitPlan(plan, budgetMs)` squeezes a plan into the time one turn gets at the current speed (950 ms at 1x in `app.js`). Everything scales by the same factor, so order and proportions hold at 8x.

`sample(plan, t, manifest)` answers what to draw `t` ms into the turn: the clip, which frame of it, facing, position (fractional while walking), hop height, emote, and whether to flip the sprite. It's pure: no clock, no randomness, same input, same output.

Default timings, all in ms at 1x, match what `renderer.js` does now, so the first wired-in version looks the same before any art changes:

| What | ms | Where it comes from |
| --- | --- | --- |
| one tile of walking | 340 | renderer `MOVE_MS` |
| eat | 560 | renderer holds the eat pose to 900 ms after the turn starts |
| ouch | 360 | renderer holds the ouch pose to 700 ms |
| think (check-in) | 600 | new |
| faint | 700 | new |
| emote | 1500 | renderer `EMOTE_MS` |

When the manifest gives frame timings for a one-shot clip, those win over the defaults.

## Sprite manifest

```json
{
  "format": "clawlings-sprites",
  "version": 1,
  "source": "sheets",
  "cell": [20, 20],
  "anchor": [3, 5],
  "sheets": {
    "critter": { "image": "critter.png", "provenance": "drawn by David Fisher from his clip 03" }
  },
  "clips": {
    "idle":      { "sheet": "critter", "frames": [[0, 0], [1, 0]], "ms": 260, "loop": true },
    "eat":       { "sheet": "critter", "frames": [[0, 2], [1, 2], [2, 2]], "ms": [120, 120, 200], "loop": false },
    "walk_east": { "sheet": "critter", "frames": [[0, 1], [1, 1]], "ms": 170, "loop": true },
    "walk_west": { "mirror": "walk_east" }
  },
  "emotes": {
    "heart": { "sheet": "critter", "frames": [[0, 5]], "ms": 220, "loop": true }
  }
}
```

- `cell` is the size of one frame on a sheet. `anchor` is where the tile's top-left corner sits inside a cell (the current art draws a 20x20 box 3 px left and 5 px up of the tile).
- `frames` lists `[column, row]` cells. `ms` is one time for every frame or one per frame.
- `mirror` reuses another clip flipped left to right, so side-on walks can be drawn once.
- Clips that play once (`eat`, `ouch`, `think`, `faint`) must have `loop: false`. All others loop.
- Images are PNGs inside the art folder. The checker refuses paths that leave it.
- `"source": "procedural"` means there are no sheets yet and `frames` is just a count. That's the shipped placeholder, which records the current art's timing.

Check it with `python -m viewer.manifest` (or pass a path). The full list of clips and emotes lives in `anim.js` and `manifest.py`, and a test keeps the two in step.

## Waiting on David

1. The art: sprite sheets for every clip and emote, each with a provenance line. Drop them in `viewer/static/art/`, set `"source": "sheets"` and run the checker.
2. His clips: they live on his machine. They are the reference for how the creatures move and how long each action takes. Timings taken from them go into the manifest.
3. The visual pass: wiring `anim.js` into `renderer.js` so the drawing follows the plans, and then the look and feel. Everything there needs his eyes.
4. Creature design and names, which are his alone.
5. Two choices the art will settle: whether walks get four drawn directions or a mirrored side view, and the cell size (20x20 today).
6. The split into its own repo (default name Clawlings-Viewer) when he wants it.

## Tests

```
python -m pytest viewer/tests
node --test viewer/tests/js/anim.test.mjs
```

The pytest suite runs the node tests too when node is installed, and also takes scripted demo episodes end to end through `logread`, the real `frames.js` and `anim.js`, checking every plan against the log: a walk exactly when the critter moved and in the right direction, a clip for every event, the critter standing on its tile at the end of each turn, and every turn fitting its time even at high speed. Without node those tests are skipped and the rest still run. No test makes an API call.
