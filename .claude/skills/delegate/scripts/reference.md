# Delegate Script Reference

## Overview

The delegate script enables one agent to delegate a task to another agent via the `claude` CLI. It logs all delegation activity to a shared `_conversation.jsonl` file within the session directory, creating an auditable record of inter-agent communication.

## Usage

```bash
bun .claude/skills/delegate/scripts/delegate.ts <agent-name> <prompt>
```

- `agent-name`: The name of the target agent (as defined in `.claude/agents/<name>.md`).
- `prompt`: The task description or instructions for the target agent. If the prompt contains spaces, quote the entire prompt string.

## Environment Variables

| Variable | Description |
|:---------|:------------|
| `CRYPLATIVE_SESSION_ID` | Shared session UUID. If not set, the script generates one. All agents in a delegation chain share the same session ID and thus the same session directory. |
| `CLAUDE_AGENT_NAME` | Name of the calling agent. Used in the `from_agent` field of conversation entries. Set by the `session-logger` hook based on the `--agent` CLI flag. If not set, defaults to `"global"`. |

## Exit Codes

The script exits with the same exit code as the child `claude` process:

| Exit Code | Meaning |
|:----------|:--------|
| 0 | Task completed successfully |
| 1 | General failure (child process failed or script error) |
| Other | Propagated from the child `claude` process |

## Session Directory Structure

```
.claude/sessions/<CRYPLATIVE_SESSION_ID>/
  _conversation.jsonl     # All session entries (prompts, delegations, responses)
```

## `_conversation.jsonl` Entry Format

Each line is a JSON object. There are three entry types:

### Initial Prompt Entry

Logged once per session when the first user prompt is submitted (via the `session-logger` hook on `UserPromptSubmit`).

```json
{
  "type": "initial_prompt",
  "timestamp": "2026-05-02T12:00:00.000Z",
  "from_agent": "primary",
  "prompt": "The original user prompt that started the session"
}
```

The `from_agent` field reflects the agent name from the `--agent` CLI flag, or `"global"` if no agent was specified.

### Delegation Entry

Logged when an agent delegates a task to another agent. The `delegation_type` field distinguishes between explicit skill calls and Claude's internal subagent mechanism.

**Skill delegation** (via `/delegate` skill):

```json
{
  "type": "delegation",
  "timestamp": "2026-05-02T12:00:00.000Z",
  "from_agent": "primary",
  "delegation_type": "skill",
  "prompt": "Analyze the market data and return a summary",
  "delegation_id": "del-<uuid>"
}
```

**Internal delegation** (via Claude Code's internal subagent mechanism):

```json
{
  "type": "delegation",
  "timestamp": "2026-05-02T12:00:00.000Z",
  "from_agent": "parent-agent-name",
  "delegation_type": "internal",
  "prompt": "The task given to the subagent (or placeholder if unavailable)",
  "delegation_id": "del-<uuid>"
}
```

The `from_agent` in internal delegation entries is determined by scanning recent conversation log entries for the most recent non-subagent `from_agent` value. If unavailable, it defaults to `"unknown"`. The `prompt` is extracted from the hook input's `prompt` or `tool_input` fields; if neither is available, a placeholder string is used.

### Response Entry

Logged when an agent finishes responding. Used for all response types — agent final responses, skill delegation responses, and internal subagent responses.

```json
{
  "type": "response",
  "timestamp": "2026-05-02T12:00:05.000Z",
  "from_agent": "secondary",
  "delegation_id": "del-<uuid>",
  "response_preview": "First 500 characters of the agent's response",
  "exit_code": 0
}
```

The `delegation_id` links a response entry to its corresponding delegation entry (present when the response comes from a delegated agent). The `exit_code` field is only present for responses from skill delegations (via `delegate.ts`).

## Behavior Notes

- The child `claude` process is spawned with `--dangerously-skip-permissions` so it can complete its task without getting stuck waiting for human permission approvals.
- The child `claude` process is spawned with `CRYPLATIVE_SESSION_ID` in its environment, ensuring session continuity across the delegation chain.
- The child's stdout is passed through to the calling script's stdout so the delegating agent sees the response in its own context.
- If the child process fails (non-zero exit code), the response entry is still written with the error exit code, and the response preview will contain any partial stdout.
- The `_conversation.jsonl` file is append-only, making it safe for concurrent use by multiple delegations.
- Both explicit `/delegate` calls and Claude's internal subagent mechanism produce `delegation` entries in `_conversation.jsonl`, providing a unified view of all inter-agent communication.
