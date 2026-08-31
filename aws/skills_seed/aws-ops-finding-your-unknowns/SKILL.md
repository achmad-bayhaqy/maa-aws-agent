---
name: finding-your-unknowns
description: "Use at the start of a non-trivial agentic coding task, or when a long-horizon task keeps coming back wrong. Surfaces the gaps between what you told the agent (the 'map') and where the work actually happens (the 'territory') — your unknowns — before, during, and after implementation. Runs a blind-spot pass, brainstorm/prototype, interview, references, and an implementation plan "
---

# Finding Your Unknowns

When you work with an agent, the **map** is what you hand it (prompts, skills, context) and the **territory** is where the work actually happens (the codebase, rea
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/finding-your-unknowns/SKILL.md -->
l constraints). The gap between them is your **unknowns** — every time the agent hits one, it can only make a decision based on its best guess of what you want. The quality of the work is often bottlenecked not by the model's ability, but by your ability to clarify its unknowns.

This skill turns "find and clarify your unknowns" into an executable pre / during / post workflow, with a copy-paste prompt for every step. **Core constraint:** don't let the agent run a long task blind — spending the cheap effort to surface unknowns first is far cheaper than reworking later.

> Method from Thariq Shihipar's (Anthropic) field guide *Finding your unknowns* (claude.com/blog, 2026-07-06). This skill is an executable packaging of it.

## When to use

- You're starting a **non-trivial** agentic coding task (multi-file / unfamiliar codebase / unfamiliar domain / design work)
- A long-horizon task **keeps coming back wrong** — usually not the model failing, but unknowns left undefined
- You **can't quite articulate what you want**, or don't know what "good" looks like
- You're about to **hand off** a large agent-authored change for buy-in, or want to confirm you actually understand what it did

## When not to use

- A one-line, single-file change (just state the request; don't add process for its own sake)
- Pure Q&A / research (there's no "implementation," so no pre/during/post)
- You're already deeply in sync with the codebase and the task, with very few unknowns (that's the state the best coders are in; this skill helps you approach it, not something to run every time)

---

## Core model (internalize first)

**Four quadrants** — break the task down four ways to decide which pattern to use (details in [references/four-quadrants.md](references/four-quadrants.md)):

| | You know you know | You know you don't |
|---|---|---|
| **Can articulate** | Known Knowns (goes in the prompt) | Known Unknowns (list them, resolve each) |
| **Can't articulate** | Unknown Knowns (recognize-on-sight → surface via brainstorm/prototype) | **Unknown Unknowns (most expensive → dig out via a blind-spot pass)** |

**One balance:** too specific and the agent follows even when a pivot is better; too vague and it fills gaps with generic best practices that may not fit you. Give it **context about your starting point** (what stage of thinking you're at, how much you know, the state of the codebase) and let it work as a thought partner, rather than just taking orders.

---

## Workflow: before → during → after

**All copy-paste prompts live in [references/prompt-library.md](references/prompt-library.md).** Per-pattern rationale and how to choose is in [references/phase-playbook.md](references/phase-playbook.md). You don't need to run every pattern every time — pick by the density of unknowns in the task, but **run at least one pre-implementation pattern, keep implementation-notes during, and quiz at least once after.**

### Pre-implementation · surface the unknowns

1. **Blind Spot Pass** — do this first in an unfamiliar area. Literally tell the agent to "do a blind spot pass, find my unknown unknowns" and state who you are and how much you know. Targets unknown unknowns.
2. **Brainstorm + prototype** — for unknown knowns (recognize-on-sight criteria). Ask for 3–4 **wildly different** directions / a throwaway HTML mock, and react. Open almost every session this way to set scope.
3. **Interview (have the agent question you)** — when ambiguity remains after brainstorming, have it ask one question at a time, **prioritizing questions whose answer would change the architecture**.
4. **References** — when you can't describe it, point at a reference. **The best reference is source code** (point it at the folder, even in another language) — richer than a screenshot.
5. **Implementation Plan** — when you think you're ready, ask for a plan that **leads with the parts most likely to change** (data model / interfaces / anything user-facing) and buries the mechanical work.

### During implementation · log deviations

6. **Start a new session** and pass in the artifacts (plan / spec / prototype) — a fresh context window with all the planning information.
7. Have the agent maintain **`implementation-notes.md`**: when an edge case forces a deviation from the plan, pick the conservative option, log it under `Deviations`, and keep going. Template: [assets/implementation-notes.template.md](assets/implementation-notes.template.md).

### Post-implementation · verify through unknowns

8. **Pitch / Explainer** — package prototype + spec + notes into one doc for buy-in, so reviewers starting with the same unknowns you had can catch up fast. Template: [assets/handoff.template.md](assets/handoff.template.md).
9. **Quiz (have the agent test you)** — after a long session, reading the diff isn't enough. Ask for a context-rich report plus a quiz at the bottom, and **only merge after you pass it perfectly**.

---

## Closing principle

The better models get, the more you can achieve with the right approach. When a long task comes back wrong, it's usually that unknowns weren't defined enough, or you were missing a plan that lets you and the agent adapt mid-course. **Every explainer, brainstorm, interview, prototype, and reference is a cheap way to find out what you didn't know before it gets expensive to fix.** Start your next project by asking the agent to help you find your unknowns.

## Files

- [references/four-quadrants.md](references/four-quadrants.md) — the four-quadrant model + how to use it to pick a pattern
- [references/prompt-library.md](references/prompt-library.md) — copy-paste prompts for each pattern (verbatim originals + generalized templates)
- [references/phase-playbook.md](references/phase-playbook.md) — per-pattern rationale and when to use each
- [assets/implementation-notes.template.md](assets/implementation-notes.template.md) — the during-phase notes file template
- [assets/handoff.template.md](assets/handoff.template.md) — the post-phase pitch / explainer document template

## Source

Method from the Anthropic blog post [A field guide to Claude Fable 5: Finding your unknowns](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns), by Thariq Shihipar (member of technical staff, Anthropic), 2026-07-06. This skill faithfully packages that method; the patterns and their names follow the original.
