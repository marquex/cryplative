---
name: agent-expertise
description: Manage structured YAML expertise files as personal mental models. Use when starting tasks (read for context), completing work (capture learnings), or when your understanding of the system needs updating.
---

# Agent expertise

## Instructions

You have personal expertise files — structured YAML documents that represent your mental model of the system you work on. These are YOUR files. You own them.

They are stored in `.agentic/expertise/{agent-name}/`, and initially should have only one file `.agentic/expertise/{agent-name}/{agent-name}-index.yaml`.

### When to Read

- **At the start of every task** — read your expertise index file `.agentic/expertise/{agent-name}/{agent-name}-index.yaml` before doing anything. Read any other expertise files linked by the index that are related to the task for gaining context and recalling what you've learned in the past about similar tasks. 
- **When you need to recall** prior observations, decisions, or patterns

### When to Update

- **After completing meaningful work** — capture what you learned
- **When you discover something new** about the system (architecture, patterns, gotchas)
- **After exploring the source code** — You explore because you don't know, update your expertise files with what you learn
- **When your knowledge changes** — update stale entries, don't just append

### How to Structure

Write structured YAML. Don't be rigid about categories — let the structure emerge from your work. But keep it organized enough that you can scan it quickly. Detect what's meaningful from your work

```yaml
# Good: structured, scannable, evolving
architecture:
  api_layer:
    pattern: "REST with WebSocket for real-time"
    key_files:
      - path: apps/server/routes.ts
        note: "All endpoints, ~400 lines"
    decisions:
      - "Chose Express over Fastify for ecosystem maturity"

features:
  auth:
    pattern: "JWT-based stateless auth"
  expertise-file: agent-name-auth.yaml

observations:
  - date: "2026-03-24"
    note: "Engineering team handles scope-heavy requests better when given explicit constraints"

open_questions:
  - "Should we split the auth module? It's growing fast."
```

### What NOT to Store

- Don't copy-paste entire files — reference them by path
- Don't store conversation logs — that's what the session log is for
- Don't store transient data (build output, test results) — just conclusions
- Don't be prescriptive about your own categories — evolve them naturally

### Line Limit Enforcement

Each expertise file has a 600 line limit. After every write to an expertise file:

1. Check the line count: `wc -l <file>`
2. If over the limit, trim immediately:
   - Remove least critical entries (old observations, resolved questions)
   - Condense verbose sections
   - Merge redundant entries
   - Summarize big entries about a topic for the index and link to a new yaml file in your expertise folder with the details
3. Re-check until within limit

This is not optional. The line limit is hard-enforced by the runtime — if your file exceeds the limit after a write, you'll get a warning that you must resolve before continuing.

## Routing to specific expertise files

As your expertise grows, you may want to create multiple expertise files for different topics. In that case, you can link to them from your index file with a key like `expertise-file: {file-name.yaml}`. When you read your index file, also read the linked expertise files for more context.

The index file should still have a small summary of the topic that the linked expertise file covers, so you can get a high-level understanding without having to read the details. The linked expertise file can then have more detailed information about the topic, and be read only when you need to dive deeper into that specific area.

Read only the linked expertise files that are relevant to the task at hand, to avoid information overload. You can always read more expertise files later if you need more context.

## Pay especial attention to inputs

The initial input that you receive and any user input during the session is crucial information that should be stored in your expertise files. This input often contains the requirements, constraints, and goals for the task at hand, and can provide important context for your current and future work.

### YAML Validation

After every write, validate your YAML is parseable. Malformed YAML is useless:

```bash
bun .claude/skills/agent-expertise/yaml-validator.ts .agentic/expertise/{agent-name}
```

Fix any syntax errors immediately.