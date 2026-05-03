---
description: "Delegate a task to another agent. Use when you need another specialized agent to handle a subtask, when you want to isolate work in a separate context, or when a task falls outside your domain expertise."
argument-hint: "<agent-name> <prompt>"
---

# Delegate Task

Use this skill to delegate a task to another agent by name. The delegation is logged to the shared session's conversation log, creating an auditable record of inter-agent communication.

## How to Use

Run the delegate script via Bash, providing the target agent name and the prompt:

```bash
bun .claude/skills/delegate/scripts/delegate.ts <agent-name> "<prompt>"
```

For example, to delegate a research task to an agent named `researcher`:

```bash
bun .claude/skills/delegate/scripts/delegate.ts researcher "Analyze the current BTC market trends and provide a summary"
```

## Important Notes

- The target agent must be defined in `.claude/agents/<agent-name>.md`.
- The target agent must be listed in the calling agent's `subordinates` frontmatter field. Delegation is enforced at two levels: (1) the `enforce-agent-access` PreToolUse hook denies Bash commands that call `delegate.ts` with an unauthorized target, and (2) the `delegate.ts` script itself checks the calling agent's frontmatter before spawning the child process.
- The `CRYPLATIVE_SESSION_ID` environment variable is automatically propagated to the child agent, ensuring all agents in a chain share the same session directory.
- The child agent's response is printed to stdout, which you will see in your context.
- Both the delegation and the response are logged to `.claude/sessions/<session-id>/_conversation.jsonl`.

## Reading Conversation History

To understand what has happened in the current session, read the conversation log:

```bash
cat .claude/sessions/$CRYPLATIVE_SESSION_ID/_conversation.jsonl
```

This file contains all user prompts, delegation and response entries for the session, allowing you to see the full history of inter-agent communication.

Entry types you'll see:
- **user_prompt**: A prompt submitted by the user in interactive mode (every submission is stored).
- **initial_prompt**: The first prompt in a print-mode session (e.g., from delegation).
- **delegation**: When one agent delegates a task to another. Logged both by the delegate skill (explicit `/delegate` calls) and by the session-logger hook for Claude's internal subagent mechanism.
- **response**: An agent's response (from Stop hook or delegation completion).
- **subagent_stop**: From Claude's internal subagent mechanism, paired with a `delegation` entry via a shared `delegation_id`.

For full details on the script API, entry format, and environment variables, see the [reference documentation](scripts/reference.md).
