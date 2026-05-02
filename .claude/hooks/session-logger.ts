/**
 * session-logger.ts
 *
 * Hook script for SessionStart, UserPromptSubmit, Stop, and SubagentStop events.
 * - On SessionStart: derives a CRYPLATIVE_SESSION_ID deterministically from the
 *   Claude session ID, detects the agent name from agent_type (or uses "global"),
 *   writes both to CLAUDE_ENV_FILE, and creates the session directory.
 * - On UserPromptSubmit: logs user prompts to _conversation.jsonl.
 *   - In print mode (-p flag, detected via CRYPLATIVE_PRINT_MODE env var):
 *     logs the first prompt as "initial_prompt" (only once per session).
 *   - In interactive mode (no CRYPLATIVE_PRINT_MODE):
 *     logs ALL prompts as "user_prompt" (every submission is stored).
 * - On Stop: logs the agent's final response as a "response" entry to
 *   _conversation.jsonl.
 * - On SubagentStop: logs a "delegation" entry (recording the internal subagent
 *   call) with delegation_type="internal", followed by a "response" entry with
 *   the subagent's response, both to _conversation.jsonl. The delegation entry
 *   is linked to the response entry via a shared delegation_id, and the parent
 *   agent is determined by scanning recent conversation log entries.
 *
 * IMPORTANT: All hooks derive the session ID deterministically from
 * input.session_id. They NEVER check process.env.CRYPLATIVE_SESSION_ID —
 * that env var is only consumed by the delegate.ts script (via Bash tool),
 * not by hook processes. This prevents session ID leakage when a child
 * claude process inherits the parent's CRYPLATIVE_SESSION_ID from the
 * Bash tool environment.
 *
 * CRYPLATIVE_PRINT_MODE detection: When delegate.ts spawns a child claude
 * process with -p, it sets CRYPLATIVE_PRINT_MODE=1 in the spawn env. This
 * env var is inherited by the child's hook processes (unlike CLAUDE_ENV_FILE
 * exports, which only propagate to Bash tool commands). The session-logger
 * checks this env var to determine whether to log as "initial_prompt" (print
 * mode) or "user_prompt" (interactive mode).
 *
 * Always exits 0 (non-blocking).
 */

import { createHash, randomUUID } from "node:crypto";
import { mkdir, appendFile, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

interface HookInput {
  session_id: string;
  cwd: string;
  hook_event_name: string;
  agent_type?: string;
  prompt?: string;
  last_assistant_message?: string;
  // SubagentStop-specific fields:
  //   agent_id: string - unique subagent identifier
  //   agent_transcript_path: string - path to the subagent's own transcript JSONL
  //   transcript_path: string - parent session's transcript path
  //   stop_hook_active: boolean
  //   permission_mode: string
  [key: string]: unknown;
}

/**
 * Derive a deterministic cryplative session ID from the Claude session ID.
 * Uses SHA-256 hash formatted as a UUID. This ensures every hook event
 * can independently compute the same session folder path from input.session_id.
 */
function deriveSessionId(claudeSessionId: string): string {
  const hash = createHash("sha256").update(claudeSessionId).digest("hex");
  // Format the first 32 hex chars as UUID: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
  const h = hash;
  return [
    h.slice(0, 8),
    h.slice(8, 12),
    "4" + h.slice(13, 16),           // UUID version 4
    ((parseInt(h.slice(16, 17), 16) & 0x3) | 0x8).toString(16) + h.slice(17, 20), // UUID variant
    h.slice(20, 32),
  ].join("-");
}

/** Read the last N lines of a file. Returns empty string if file doesn't exist. */
async function readLastLines(filePath: string, maxLines: number): Promise<string> {
  try {
    const raw = await readFile(filePath, "utf-8");
    const lines = raw.trim().split("\n");
    return lines.slice(-maxLines).join("\n");
  } catch {
    return "";
  }
}

/** Check if _conversation.jsonl already has an initial_prompt entry. */
async function hasInitialPromptEntry(conversationFile: string): Promise<boolean> {
  const tail = await readLastLines(conversationFile, 50);
  if (!tail) return false;
  return tail.split("\n").some((line) => {
    try {
      const entry = JSON.parse(line);
      return entry.type === "initial_prompt";
    } catch {
      return false;
    }
  });
}

/**
 * Check if the current session is running in print mode (-p flag).
 * Print mode is detected via the CRYPLATIVE_PRINT_MODE env var, which is
 * set by delegate.ts when spawning child claude processes.
 */
function isPrintMode(): boolean {
  return process.env.CRYPLATIVE_PRINT_MODE === "1";
}

async function main() {
  const raw = await Bun.stdin.text();
  let input: HookInput;
  try {
    input = JSON.parse(raw) as HookInput;
  } catch {
    process.exit(0);
  }

  const projectDir = input.cwd;
  const sessionsDir = join(projectDir, ".claude", "sessions");

  if (input.hook_event_name === "SessionStart") {
    await handleSessionStart(sessionsDir, input);
  } else if (input.hook_event_name === "UserPromptSubmit") {
    await handleUserPromptSubmit(sessionsDir, input);
  } else if (input.hook_event_name === "Stop") {
    await handleStop(sessionsDir, input);
  } else if (input.hook_event_name === "SubagentStop") {
    await handleSubagentStop(sessionsDir, input);
  }

  process.exit(0);
}

async function handleSessionStart(sessionsDir: string, input: HookInput) {
  const envFile = process.env.CLAUDE_ENV_FILE;

  // Always derive session ID deterministically from Claude session ID.
  // This ensures consistency even if CRYPLATIVE_SESSION_ID leaks from a
  // parent process env (e.g., when running `claude -p` from Bash tool).
  const sessionId = deriveSessionId(input.session_id);

  // Create session directory
  const sessionPath = join(sessionsDir, sessionId);
  await mkdir(sessionPath, { recursive: true });

  // Determine agent name: use agent_type from hook input if --agent was used,
  // otherwise default to "global"
  const agentName = input.agent_type ?? "global";

  // Write environment variables to CLAUDE_ENV_FILE so they propagate to Bash commands.
  // These are consumed by scripts like delegate.ts, NOT by other hook processes
  // (hooks don't source CLAUDE_ENV_FILE).
  if (envFile) {
    await appendFile(envFile, `export CRYPLATIVE_SESSION_ID="${sessionId}"\n`);
    await appendFile(envFile, `export CLAUDE_AGENT_NAME="${agentName}"\n`);
    await appendFile(envFile, `export CLAUDE_SESSION_ID="${input.session_id}"\n`);
  }

  process.exit(0);
}

async function handleUserPromptSubmit(sessionsDir: string, input: HookInput) {
  // ALWAYS derive from input.session_id — never check process.env.CRYPLATIVE_SESSION_ID.
  // The env var may be leaked from a parent claude process (via Bash tool env),
  // which would cause this hook to write to the wrong session directory.
  const claudeSessionId = input.session_id;
  const sessionId = deriveSessionId(claudeSessionId);
  const agentName = input.agent_type ?? "global";

  const prompt = input.prompt;
  if (!prompt) {
    process.exit(0);
  }

  const sessionPath = join(sessionsDir, sessionId);

  // Ensure session directory exists
  if (!existsSync(sessionPath)) {
    process.exit(0);
  }

  const conversationFile = join(sessionPath, "_conversation.jsonl");

  if (isPrintMode()) {
    // Print mode (-p flag): log the first prompt as "initial_prompt" only.
    // Used by delegate.ts which spawns child processes with -p.
    // Only one prompt per session in print mode, so guard with hasInitialPromptEntry.
    if (await hasInitialPromptEntry(conversationFile)) {
      process.exit(0);
    }

    const entry = {
      type: "initial_prompt",
      timestamp: new Date().toISOString(),
      from_agent: agentName,
      prompt,
    };

    await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  } else {
    // Interactive mode: log ALL user prompts as "user_prompt".
    // No guard — every prompt submission is stored in the conversation.
    const entry = {
      type: "user_prompt",
      timestamp: new Date().toISOString(),
      from_agent: agentName,
      prompt,
    };

    await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  }

  process.exit(0);
}

async function handleStop(sessionsDir: string, input: HookInput) {
  // ALWAYS derive from input.session_id — never check process.env.
  const claudeSessionId = input.session_id;
  const sessionId = deriveSessionId(claudeSessionId);
  const agentName = input.agent_type ?? "global";

  const lastMessage = input.last_assistant_message ?? "";
  if (!lastMessage) {
    process.exit(0);
  }

  const sessionPath = join(sessionsDir, sessionId);

  // Ensure session directory exists
  if (!existsSync(sessionPath)) {
    process.exit(0);
  }

  const conversationFile = join(sessionPath, "_conversation.jsonl");

  const entry = {
    type: "response",
    timestamp: new Date().toISOString(),
    from_agent: agentName,
    response_preview: lastMessage.substring(0, 500),
  };

  await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  process.exit(0);
}

/**
 * Determine the parent agent that spawned a subagent by scanning recent
 * conversation log entries. Returns the from_agent of the most recent
 * non-subagent entry (user_prompt, initial_prompt, response, or delegation
 * from delegate.ts).
 */
async function findParentAgent(conversationFile: string): Promise<string> {
  const tail = await readLastLines(conversationFile, 50);
  if (!tail) return "unknown";

  // Walk backwards through entries to find the most recent non-subagent entry
  const lines = tail.split("\n").reverse();
  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      // Skip internal subagent responses — they won't tell us who the parent is
      if (entry.delegation_type === "internal") {
        continue;
      }
      if (entry.from_agent) {
        return entry.from_agent as string;
      }
    } catch {
      continue;
    }
  }

  return "unknown";
}

/**
 * Try to extract the prompt/task that was given to the subagent.
 * Checks direct fields in the hook input, then reads the subagent's
 * own transcript (agent_transcript_path) to find the initial user message.
 */
async function extractSubagentPrompt(input: HookInput): Promise<string> {
  // Check direct fields in the hook input
  if (typeof input.prompt === "string" && input.prompt) {
    return input.prompt;
  }

  // Check for tool_input which might contain the subagent's task
  const toolInput = input["tool_input"];
  if (toolInput && typeof toolInput === "object") {
    const obj = toolInput as Record<string, unknown>;
    for (const key of ["prompt", "task", "message", "instruction"]) {
      if (typeof obj[key] === "string" && obj[key]) {
        return obj[key] as string;
      }
    }
  }

  // Read the subagent's own transcript to extract the initial user message.
  // agent_transcript_path points to the subagent's conversation transcript
  // (e.g., ~/.claude/projects/.../subagents/agent-<id>.jsonl), which starts
  // with the user message containing the exact task/prompt given to the subagent.
  const agentTranscriptPath = input["agent_transcript_path"] as
    | string
    | undefined;
  if (
    agentTranscriptPath &&
    typeof agentTranscriptPath === "string"
  ) {
    const prompt = await extractPromptFromTranscript(agentTranscriptPath);
    if (prompt) return prompt;
  }

  return "internal subagent call (prompt not available)";
}

/**
 * Try to extract the initial user message (the task/prompt) from a
 * Claude Code transcript file. Claude Code transcripts are JSONL files
 * where each line is a message. The first user message is the prompt
 * given to the subagent.
 *
 * Handles two common formats:
 * - Flat: { type: "user", content: "..." }
 * - Nested: { type: "user", message: { content: "..." } }
 */
async function extractPromptFromTranscript(
  transcriptPath: string
): Promise<string | null> {
  try {
    const content = await readFile(transcriptPath, "utf-8");
    const lines = content.trim().split("\n");
    for (const line of lines) {
      try {
        const msg = JSON.parse(line);
        const isUser =
          msg.role === "user" || msg.type === "user" || msg.type === "human";
        if (!isUser) continue;

        // Content may be at top level or nested inside msg.message
        const msgContent =
          msg.content ?? (msg.message as Record<string, unknown>)?.content;

        if (typeof msgContent === "string" && msgContent.trim()) {
          return msgContent.trim();
        }
        if (Array.isArray(msgContent)) {
          const textBlock = msgContent.find(
            (b: Record<string, unknown>) => b.type === "text"
          );
          if (
            textBlock &&
            typeof textBlock.text === "string" &&
            textBlock.text.trim()
          ) {
            return textBlock.text.trim();
          }
        }
      } catch {
        continue;
      }
    }
  } catch {
    // Can't read transcript
  }
  return null;
}

/**
 * Extract the clean text response from last_assistant_message.
 * Handles:
 * - Plain text (returned as-is)
 * - JSON content block arrays (extracts only text blocks)
 * - XML thinking/anticipation tags (strips them)
 */
function extractCleanResponse(lastMessage: string): string {
  // Try parsing as JSON content blocks array
  try {
    const parsed = JSON.parse(lastMessage);
    if (Array.isArray(parsed)) {
      const textParts: string[] = [];
      for (const block of parsed) {
        if (
          block &&
          typeof block === "object" &&
          block.type === "text" &&
          typeof block.text === "string"
        ) {
          textParts.push(block.text);
        }
      }
      if (textParts.length > 0) {
        return textParts.join("\n").trim();
      }
    }
  } catch {
    // Not JSON — handle as plain text below
  }

  // Strip XML thinking/anticipation blocks
  let cleaned = lastMessage;
  cleaned = cleaned.replace(/<thinking>[\s\S]*?<\/thinking>/gi, "");
  cleaned = cleaned.replace(/<anticipation>[\s\S]*?<\/anticipation>/gi, "");
  cleaned = cleaned.trim();

  return cleaned || lastMessage;
}

async function handleSubagentStop(sessionsDir: string, input: HookInput) {
  // ALWAYS derive from input.session_id — never check process.env.
  // SubagentStop fires for Claude's internal subagent mechanism (not delegate.ts).
  // The subagent shares the parent's Claude session_id, so it derives the same
  // session ID and writes to the same session directory.
  const claudeSessionId = input.session_id;
  const sessionId = deriveSessionId(claudeSessionId);
  const subagentType = input.agent_type ?? "";
  const rawMessage = input.last_assistant_message ?? "";

  // Skip empty agent_type — these are Claude Code internal subagents
  // (e.g., background processing), not real agent delegations.
  if (!subagentType || !rawMessage) {
    process.exit(0);
  }

  const sessionPath = join(sessionsDir, sessionId);

  // Ensure session directory exists
  if (!existsSync(sessionPath)) {
    await mkdir(sessionPath, { recursive: true });
  }

  const conversationFile = join(sessionPath, "_conversation.jsonl");
  const delegationId = `del-${randomUUID()}`;

  // Determine the parent agent and the prompt given to the subagent
  const parentAgent = await findParentAgent(conversationFile);
  const prompt = await extractSubagentPrompt(input);

  // Clean the response: extract text content, strip thinking/tool blocks
  const cleanResponse = extractCleanResponse(rawMessage);

  // Log a delegation entry to record that an internal subagent call occurred.
  // This parallels the delegation entries written by delegate.ts for explicit
  // /delegate skill calls, so all inter-agent calls appear uniformly in the log.
  const delegationEntry = {
    type: "delegation",
    timestamp: new Date().toISOString(),
    from_agent: parentAgent,
    delegation_type: "internal",
    prompt,
    delegation_id: delegationId,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(delegationEntry) + "\n"
  );

  // Log the response entry linked to the delegation via delegation_id.
  // Modeled like the response from a /delegate skill call.
  const stopEntry = {
    type: "response",
    timestamp: new Date().toISOString(),
    from_agent: subagentType,
    response_preview: cleanResponse.substring(0, 500),
    delegation_id: delegationId,
  };

  await appendFile(conversationFile, JSON.stringify(stopEntry) + "\n");
  process.exit(0);
}

main().catch(() => process.exit(0));
