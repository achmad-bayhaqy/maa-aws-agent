---
name: fact-check-loop
description: "Iterative fact-checking loop for any document (PPT, Word, PDF, Markdown, etc.) against its original source. Spawns independent subagents in fresh contexts to eliminate confirmation bias. Each round checks all claims, the main agent fixes issues found, then a new subagent re-checks until zero issues remain. Use when: (1) user asks to fact-check a document, (2) user wants to veri"
---

# Fact-Check Loop

Iteratively fact-check a document against its original source using independent subagents.

The failure mode this skill exists to prevent: an agent that wrote a summary is a poor
judge of whether the summary is accurate. It already believes its own claims, so asking
it to re-read its work surfaces far fewer errors than it should
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/fact-check-loop/SKILL.md -->
. The fix is structural —
every check runs in a **fresh context** that has never seen the document being written,
only the document as it stands and the source it must match.

## Workflow

### 1. Gather inputs

Confirm two things (ask if not provided):

- **Document**: path to the file to check (`.pptx`, `.docx`, `.pdf`, `.md`, etc.)
- **Source**: the authoritative reference — URL(s), local file path(s), or a mix

### 2. Run the loop

Maintain a `fixes_log` list: `{round, page/section, issue, fix_applied}`.

For each round `N` (starting at 1):

**(a) Spawn a fact-check subagent.** Use the most capable model available to the runtime.
Each round MUST be a fresh subagent — never continue a conversation with a prior one.
Fresh context = independent judgment = no confirmation bias.

**(b) Build the subagent prompt** using the template in [references/subagent-prompt.md](references/subagent-prompt.md).
Include: document path, source location(s), cumulative `fixes_log`, round number, output format.

**(c) Parse the result.** The subagent returns either:
- **`ALL_PASS`** → exit the loop
- A list of issues → continue to (d)

**(d) Fix each issue** in the document. Append each fix to `fixes_log`.

**(e) Rebuild** if needed (e.g., re-run an HTML→PPTX build script so the fix lands in the artifact, not just the source).

**(f) Increment `N`**, repeat from (a). **Max 6 rounds** — if issues persist, report and stop.

### 3. Report

After the loop exits, output:

```
## Fact-Check Complete

| Round | Issues Found | Issues Fixed |
|-------|-------------|-------------|
| 1     | 7           | 7           |
| 2     | 3           | 3           |
| ...   | ...         | ...         |
| N     | 0 (PASS)    | —           |

Total rounds: N | Total issues fixed: X
Final file: <path>
```

## Key Rules

1. **Fresh agent every round.** A new subagent with a clean context is the entire point;
   reusing one collapses the check back into self-review.
2. **Cumulative fixes log.** Always pass the full history so each agent verifies prior
   fixes landed correctly and didn't introduce new errors.
3. **Error classification.** Instruct the subagent to classify each finding:
   - **Factual error** (wrong number, inverted labels, fabricated claim) — must fix
   - **Misleading omission** (missing context that changes meaning) — must fix
   - **Imprecise wording** (oversimplification, not wrong per se) — fix if easy
   - **Acceptable simplification** (inherent to summarization) — skip, don't count
4. **Source coverage.** The subagent must read the full source (chunk by chunk if needed)
   before reporting. A check against a partially-read source produces false passes on the
   sections it never opened.
5. **The subagent identifies, the main agent fixes.** Keep the roles split. A subagent that
   also edits starts justifying its own edits.

## Tooling

This skill is runtime-agnostic. It needs two capabilities; use whatever the runtime provides.

**Document text extraction:**

| Format | Approach |
|--------|----------|
| `.md` / `.txt` | Read the file directly |
| `.pdf` | A PDF reader that supports page ranges |
| `.pptx` / `.docx` | A converter such as [`markitdown`](https://github.com/microsoft/markitdown) (`pip install markitdown`), then `python3 -m markitdown <file>` |

**Source retrieval:**

| Source | Approach |
|--------|----------|
| Local file | Read directly; chunk large files with offset/limit |
| URL | Any web-fetch tool available (a built-in fetch tool, a crawler MCP, or `curl` piped through an HTML→Markdown converter). Chunk long pages and read sequentially until fully covered |

Record which extraction path was used in the final report — a check run against a bad text
extraction is worse than no check, because it looks like a pass.
