# Agent expertise

## Instructions

You have personal expertise files — structured YAML documents that represent your mental model of the system you work on. These are YOUR files. You own them.

They are stored in `.agentic/expertise/{agent-name}/`, and initially should have only one file `.agentic/expertise/{agent-name}/{agent-name}-index.yaml`.

Checking your expertise is your first approach to everything: first check your expertise then go to the code to verify details.
  
### When to Read

The index is injected automatically at the start of every task. 

When you receive a task, analyze it, and assess if there is some other expertise file that might be relevant to the task. If so, read it for context before doing anything.

Also read your expertise files when you need to recall prior observations, decisions, or patterns that might be relevant to the current work.

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

observations:
  - date: "2026-03-24"
    note: "Engineering team handles scope-heavy requests better when given explicit constraints"

open_questions:
  - "Should we split the auth module? It's growing fast."
```

DO NOT USE COMMENTS to capture information. If it's important, it should be in the YAML structure.

### What to store

- Key architectural patterns and decisions
- High level notes on how things work, not low level details. You can always have a look at the code for that.
- Whys behind decisions, not just whats
- Observations from your work and interactions with the system
- Insights provided by the user prompts and feedback

### What NOT to Store

- Don't copy-paste entire files — reference them by path
- Don't store conversation logs
- Don't store transient data (build output, test results) — just conclusions
- Don't be prescriptive about your own categories — evolve them naturally

### Line Limit Enforcement

Each expertise file has a 600-line limit. After every write to an expertise file:

1. Check the line count: `wc -l <file>`
2. If over the limit, trim immediately:
   - Remove least critical entries (old observations, resolved questions)
   - Condense verbose sections
   - Merge redundant entries
   - Summarize big entries about a topic for the index and link to a new yaml file in your expertise folder with the details
3. Re-check until within limit

This is not optional. The line limit is hard-enforced by the runtime — if your file exceeds the limit after a write, you'll get a warning that you must resolve before continuing.

On the other hand, there is a maximum of 300 characters per line to keep your entries concise and scannable. Always try to keep it short, as this is a mental model not a detailed description. If you find yourself writing very long lines, consider if you need to keep so much information about the entry, or break it down into multiple entries. 

NEVER break lines for displaying purposes, the line limit is about keeping your expertise concise and scannable, not about formatting.

### YAML Validation

After every write, validate your YAML is parseable. Malformed YAML is useless:

```bash
npm run yaml-validator -- .agentic/expertise/{agent-name}
```

Fix any syntax errors immediately.