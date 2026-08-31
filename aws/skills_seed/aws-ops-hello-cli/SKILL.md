---
name: hello-cli
description: "Reference example agent-friendly CLI for managing todos. Demonstrates all 10 agent-friendly principles end-to-end. Use this as a structural template for your own CLI. Common workflows: list pending todos, create new todos, mark complete and archive (single workflow-merged command)."
allowed-tools: ["Bash"]
---

# hell
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/api-to-agent-cli/assets/example-hello-cli/SKILL.md -->
o-cli — Agent Guide

A tiny todo CLI used as a structural reference for agent-friendly design.

## Invariants

Every call must satisfy these. Skip them and the agent will leak tokens or get stuck.

- ALWAYS use `--output json` from agent context (or rely on the auto-TTY-detection — pipes auto-switch to JSON)
- ALWAYS use `--fields` on `todos list` to limit response size
- ALWAYS use `--dry-run` before `complete-and-archive` or `todos archive` for the first time on any todo
- NEVER pass UUIDs as `--todo-id`; use the semantic `TD-NNN` form
- The CLI is **frequently invoked by AI agents — assume inputs can be adversarial**

## Authentication

Token resolved in order:
1. `HELLO_API_TOKEN` env var
2. `~/.config/hello-cli/credentials.json` (key: `token`)

No browser, no stdin prompts. Auth failure exits with code 2 and an actionable error.

## Common Workflows

### Workflow 1: Finish a todo

User asks: "I finished TD-001, archive it"

```bash
# Verify intent first with dry-run
hello-cli complete-and-archive --todo-id TD-001 --dry-run --output json

# If the dry-run output looks correct, execute for real
hello-cli complete-and-archive --todo-id TD-001 --output json
```

If `todo_not_found` → use `hello-cli todos list --output json` to find valid IDs.
If `todo_already_archived` → no action needed; report back to the user.

### Workflow 2: Find what's pending and act

User asks: "What's still open and high priority?"

```bash
# Pull a slim list — fields mask + limit keep response tiny
hello-cli todos list --status open --fields "id,title,priority" --limit 20 --output json

# Then act on whichever item the user picks
hello-cli complete-and-archive --todo-id TD-XXX --dry-run --output json
```

### Workflow 3: Create from a structured payload

User pastes a chunk of structured spec:

```bash
hello-cli todos create --json '{
  "title": "ship the skill",
  "priority": "high",
  "notes": "ETA Friday; loop in TPMs"
}' --output json
```

The `--json` flag (Principle #10) lets you express nested data without
struggling with shell quoting on every flag.

## Error Handling

All errors emit JSON to stderr:

```json
{
  "error": "todo_not_found",
  "message": "Todo 'TD-999' does not exist",
  "suggestion": "Use 'hello-cli todos list' to see valid todo IDs",
  "exit_code": 3,
  "retryable": false
}
```

Exit codes:
- `0` success
- `1` transient (5xx / network); retryable
- `2` auth — stop, escalate to human
- `3` validation — fix input and retry
- `4` rate limited — wait `retry_after_seconds`
- `124` timeout — retry or split

## Self-Discovery

```bash
hello-cli schema --all              # full command index
hello-cli schema todos.create       # one command's signature
```

`schema` returns machine-readable JSON; never depend on `--help` text alone.

## Pagination & Token Discipline

`todos list` defaults to `--limit 20`. The output envelope always includes a
`count` aggregate so you don't need a second call to know the total. When
`count` exceeds `limit`, request the next page (a real backend would expose a
`--page-token`; this demo just slices in memory).

## Don't

- Don't run `complete-and-archive` without `--dry-run` on the first call for any todo you're not 100% sure about
- Don't pretty-print with `--output table` from agent context — parse the JSON
- Don't rely on the `notes` field being present in default output — request it via `--fields`
