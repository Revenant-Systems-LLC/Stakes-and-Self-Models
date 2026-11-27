// Reads an episode JSON (as /api/episode sends it), builds frames with the real
// frames.js, plans them with anim.js, and prints what came out as JSON.
// viewer/tests/test_anim_js.py uses this to run demo logs end to end.
//   node viewer/tests/js/plan_episode.mjs episode.json [turnMs]
import { readFileSync } from "node:fs";
import { buildFrames } from "../../static/frames.js";
import { planEpisode, fitPlan, sample } from "../../static/anim.js";

const ep = JSON.parse(readFileSync(process.argv[2], "utf8"));
const turnMs = Number(process.argv[3] || 950);
const manifest = JSON.parse(readFileSync(new URL("../../static/art/manifest.json", import.meta.url), "utf8"));
const frames = buildFrames(ep);
const plans = planEpisode(frames, { manifest });
const out = plans.map((p, i) => {
  const f = fitPlan(p, turnMs);
  const end = sample(f, turnMs - 1, manifest);
  return {
    turn: frames[i].turn,
    pos: frames[i].critter.pos,
    from: frames[i].critter.from,
    events: frames[i].events,
    facing: p.facing,
    clips: p.segments.map((s) => s.clip),
    total: p.total,
    fitted: f.total,
    rest: p.rest,
    end: { clip: end.clip, pos: end.pos, hop: end.hop },
  };
});
process.stdout.write(JSON.stringify(out));
