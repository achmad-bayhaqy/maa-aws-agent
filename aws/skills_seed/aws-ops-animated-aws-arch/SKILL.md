---
name: animated-aws-arch
description: "Draw an animated, light-theme, LEFT-TO-RIGHT AWS architecture diagram as one self-contained SVG — official AWS service icons, marching-ants connectors, and traveling request dots that show data moving through the system. Use this whenever the user asks for an architecture / 架构图 / system / infrastructure / cloud diagram, ESPECIALLY when they want it animated / dynamic / '会动的' / "
---

# animated-aws-arch

Produce a **light-background, left-to-right, animated AWS architecture SVG**: official
AWS service icons (white glyph on a brand-color tile), orthogonal co
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/animated-aws-arch/SKILL.md -->
nnectors that flow
as marching-ants dashes, colored dots that ride real request journeys, numbered spine
steps, and dashed containment boundaries (AWS Cloud region ⊃ VPC / event-driven box).
One `.svg` file, no external assets, opens in any browser, and **animates inside a GitHub
README image embed**.

You author a small **JSON spec** (nodes + edges + groups + journeys); the bundled
generator computes the SVG. You never hand-type SVG XML.

## When to use

- **Default for any architecture / system / infra diagram.** Prefer this over a static
  image whenever the diagram represents things that move (requests, events, jobs, data).
- Contrast with `~/.claude/reference/architecture-diagrams.md` (draw.io): reach for
  **draw.io only** when the user explicitly wants a purely static, editable `.drawio`
  source, or an official-repo static PNG. Otherwise use this skill.

## Workflow

1. **Author the spec.** Copy `references/example-chatops-agent.json` and edit it. That
   file is the canonical, working example — a complete Chat-app × Bedrock AgentCore
   reference architecture. Read it first; it shows every field in use.
2. **Render:** `python3 scripts/gen_arch.py <spec>.json <out>.svg`
   (write the spec to a temp path; the deliverable is only the `.svg`).
3. **Verify (mandatory).** Headless-render to PNG and *read the PNG* — the generator can't
   see label collisions or off-canvas labels:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
     --screenshot=/tmp/arch.png --window-size=1480,920 --hide-scrollbars \
     --default-background-color=FFFFFFFF "file://$(pwd)/<out>.svg"
   ```
   Check: no label clipped at the right/top edge, no diagonal connectors (all segments
   orthogonal), every boundary fully contains its members, edge labels not sitting on
   top of each other. Fix by editing the JSON (move a node, add `mids`, nudge `lxy`) and
   re-render. Usually 2–4 rounds.
4. **Deliver** the `.svg`. Tell the user it opens in any browser and animates.

## Spec schema (see the example for a full instance)

```jsonc
{
  "title": "...", "subtitle": "...", "footer": "...",
  "canvas": {"w": 1480, "h": 900},
  "nodes": [
    {"id": "runtime", "x": 800, "y": 408, "icon": "agentcore",
     "label": "AgentCore Runtime", "sub": "Claude Agent SDK"}
  ],
  "groups": [
    {"kind": "region|subnet|event", "x": .., "y": .., "w": .., "h": ..,
     "label": "...", "lx": .., "ly": .., "labelPos": "bottom"}   // lx/ly/labelPos optional
  ],
  "edges": [
    {"from": "a", "fs": "r", "to": "b", "ts": "l", "flow": "request",
     "label": "...", "lxy": [x, y], "mids": [[x,y]], "static": false}
  ],
  "journeys": [
    {"flow": "request", "dur": 2.6, "reverse": false, "hops": [["a","b"],["b","c"]]}
  ],
  "steps": [["a","b",1]],                 // numbered ①.. badges on the midpoint of an edge
  "legend": ["request","reply","schedule","ambient","garden","tool"]
}
```

- `fs`/`ts` = exit/enter **side** of the icon: `l r t b` (edge stops at the 46px icon edge).
- `mids` = orthogonal waypoints. **Keep every segment horizontal or vertical — no diagonals.**
  A segment is diagonal iff consecutive points differ in *both* x and y; insert a waypoint.
- `flow` picks the color + animation: `request` blue, `reply` teal, `schedule` green,
  `ambient` violet, `garden` amber, `tool` sky, `aux` grey. `"static": true` draws a quiet
  dotted line (no marker, no animation) — use for cross-cutting deps (Secrets/KMS: draw ONE
  representative line, not one per consumer).
- `journeys` are the animated dots. `reverse: true` sends the dot backward along a forward
  edge's path (used for the reply traveling right→left on the spine). 3–5 journeys total.

## Layout conventions (this is what keeps it clean)

Left-to-right on a fixed grid. The example uses three horizontal bands:

- **Spine row** (`y≈408`): the main request path, left→right, one straight line:
  client → API Gateway → webhook → compute → gateway → model. Put the `steps` ①.. here.
- **Top band** (`y≈168`): event-driven / async producers (EventBridge + its Lambdas),
  wrapped in an `event` group box.
- **Bottom row** (`y≈660`): data stores (memory, DynamoDB, S3) + Secrets Manager.

Rules that prevent spaghetti:
- **Align nodes on shared x (vertical edges) and shared y (horizontal edges)** so those
  edges are dead straight. Columns in the example line up across bands (e.g. webhook and
  Dispatcher share x=576 → a straight vertical `deliver`).
- A vertical edge must not pass **through** an intermediate node on that column — route it
  up/over via a `mids` lane in clear space.
- External (non-AWS) systems sit **outside** the region box (client on the left, third
  parties on the right).

## Icons

`icon` is a filename key in `icons/` (56 official AWS icons bundled). Common keys:
`lambda apigateway agentcore bedrock dynamodb s3 cloudwatch ecr cloudfront xray eventbridge
secretsmanager sqs stepfunctions ec2 ecs eks rds kms iam cognito vpc route53 elb nat sagemaker
opensearch glue athena waf guardduty efs ebs connect`. Run `ls icons/` for the full list.

- The core set (lambda, apigateway, bedrock, dynamodb, s3, cloudwatch, ecr, cloudfront,
  agentcore, xray) are the **newer flat** official icons; the rest are the gradient
  generation, auto-flattened to their flat AWS category color by the generator's `FLATTEN`
  map. To add a service: drop `Arch_*.svg` (or any official icon SVG) into `icons/` as
  `<key>.svg`; if it uses a gradient tile, add `"<key>": "#<flatcolor>"` to `FLATTEN` in
  `scripts/gen_arch.py`.
- **Non-AWS nodes** use built-in tiles instead of a file: `tile:lark` (chat bubble),
  `tile:gateway` (router chevrons, for LiteLLM/proxies), `tile:external` (magnifier, for
  Exa / third-party APIs), `tile:generic`.
- **AgentCore rule:** AgentCore Runtime **and** Memory both use `agentcore` (the official
  Bedrock-AgentCore icon). AWS ships no per-sub-feature icons; the label distinguishes them.
  **Never draw AgentCore Memory as a database cylinder** — it reads as a plain DB.

## Boundaries

`region` = amber/teal dashed (AWS Cloud / Region / account / VPC-as-region); `subnet` =
purple dashed (VPC / private subnet / security group, nested inside a region); `event` =
pink dotted (an event-driven job cluster). Label top-left by default; set `"labelPos":
"bottom"` when the top is crowded. A boundary must clear its members by ≥20px on all sides.

## GitHub animation — the important caveat

- **In a README (`![](path.svg)` embed): it animates.** Same mechanism as the popular
  animated-SVG README badges. This is how an animated architecture README shows it moving.
- **Opening the standalone `.svg` blob page on github.com: usually static** — GitHub
  sanitizes SMIL in the file viewer. So embed it in markdown; don't tell the user to click
  the raw file to see motion.
- Locally / in any browser: full animation.

## Delivery

Commit the `.svg` and embed it in the README with `![Architecture](docs/<name>.svg)`.
Keep the file self-contained (no external refs — the generator inlines every icon).
The spec JSON is a build intermediate; keep it if you want cheap re-renders, but the README
only needs the `.svg`.
