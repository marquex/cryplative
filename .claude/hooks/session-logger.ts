/**
 * session-logger.ts
 *
 * Hook script for SessionStart, UserPromptSubmit, Stop, and SubagentStop events.
 * - On SessionStart: derives a CRYPLATIVE_SESSION_ID deterministically from the
 *   Claude session ID, generates a CRYPLATIVE_AGENT_RUN_ID (6-char random string),
 *   detects the agent name from agent_type (or uses "global"), writes env vars
 *   to CLAUDE_ENV_FILE, creates the session directory + agent_logs subdirectory,
 *   and writes session metadata to _metadata.json.
 * - On UserPromptSubmit: logs user prompts to _conversation.jsonl with agent_run_id.
 *   - In print mode (-p flag, detected via CRYPLATIVE_PRINT_MODE env var):
 *     logs the first prompt as "initial_prompt" (only once per session).
 *   - In interactive mode (no CRYPLATIVE_PRINT_MODE):
 *     logs ALL prompts as "user_prompt" (every submission is stored).
 * - On Stop: logs the agent's final response as a "response" entry with agent_run_id
 *   to _conversation.jsonl, and copies the session transcript to agent_logs.
 * - On SubagentStop: logs a "delegation" entry with delegation_type="internal",
 *   followed by a "response" entry with agent_run_id and the subagent's response,
 *   and copies the subagent transcript to agent_logs.
 *
 * IMPORTANT: All hooks derive the session ID deterministically from
 * input.session_id. They NEVER check process.env.CRYPLATIVE_SESSION_ID —
 * that env var is only consumed by the delegate.ts script (via Bash tool),
 * not by hook processes. This prevents session ID leakage when a child
 * claude process inherits the parent's CRYPLATIVE_SESSION_ID from the
 * Bash tool environment.
 *
 * Agent Run ID: A 6-character random alphanumeric string that uniquely identifies
 * each agent run. For the main agent (interactive sessions), one run_id is generated
 * per session and reused across all prompts/responses. For sub-agents, a fresh
 * run_id is generated per invocation. The run_id is stored in:
 * - _metadata.json (for main agent, persisted across hooks)
 * - agent_run_id field in _conversation.jsonl entries
 * - agent_logs/{agent-name}-{run_id}.jsonl filename
 *
 * Always exits 0 (non-blocking).
 */

import { createHash, randomUUID } from "node:crypto";
import { mkdir, appendFile, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

interface HookInput {
  session_id: string;
  cwd: string;
  hook_event_name: string;
  transcript_path?: string;
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

interface SessionMetadata {
  run_id: string;
  agent_name: string;
  transcript_path?: string;
}

/**
 * Generate a 6-character random alphanumeric string for agent run identification.
 * Uses crypto.getRandomValues for secure randomness.
 */
function generateRunId(): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  for (let i = 0; i < 6; i++) {
    result += chars[bytes[i] % chars.length];
  }
  return result;
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

/**
 * Check if the current hook process is running in a delegated session.
 * Delegated sessions are child claude processes spawned by delegate.ts.
 * They should share the parent's session directory instead of creating their own.
 */
function isDelegatedSession(): boolean {
  return process.env.CRYPLATIVE_DELEGATED_SESSION === "1";
}

/**
 * Get the session ID for the current hook invocation.
 * For delegated sessions (spawned by delegate.ts), uses CRYPLATIVE_SESSION_ID
 * from the env so the child writes to the parent's session directory.
 * For normal sessions, derives from input.session_id deterministically.
 */
function getSessionId(input: HookInput): string {
  if (isDelegatedSession() && process.env.CRYPLATIVE_SESSION_ID) {
    return process.env.CRYPLATIVE_SESSION_ID;
  }
  return deriveSessionId(input.session_id);
}

/**
 * Get the agent run ID for the current hook invocation.
 * For delegated sessions, reads CRYPLATIVE_AGENT_RUN_ID from the env
 * (set by delegate.ts). For normal sessions, returns undefined so the
 * caller reads from _metadata.json instead.
 */
function getRunId(): string | undefined {
  if (isDelegatedSession()) {
    return process.env.CRYPLATIVE_AGENT_RUN_ID;
  }
  return undefined;
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
 * Check if a message is a Claude Code skill setup injection.
 * These are user messages whose first content block's text starts with
 * <command-message> — they contain the full skill definition and are
 * very large, so we filter them out from agent_logs.
 */
function isSkillSetupMessage(message: Record<string, unknown>): boolean {
  if (message.role !== "user") return false;
  const content = message.content;
  if (typeof content === "string") {
    return (content as string).trimStart().startsWith("<command-message>");
  }
  if (Array.isArray(content) && content.length > 0) {
    const first = content[0];
    if (
      first &&
      typeof first === "object" &&
      (first as Record<string, unknown>).type === "text" &&
      typeof (first as Record<string, unknown>).text === "string"
    ) {
      return ((first as Record<string, unknown>).text as string)
        .trimStart()
        .startsWith("<command-message>");
    }
  }
  return false;
}

/**
 * Check if the current session is running in print mode (-p flag).
 * Print mode is detected via the CRYPLATIVE_PRINT_MODE env var, which is
 * set by delegate.ts when spawning child claude processes.
 */
function isPrintMode(): boolean {
  return process.env.CRYPLATIVE_PRINT_MODE === "1";
}

/** Read session metadata from _metadata.json. Returns null if not found. */
async function readMetadata(sessionPath: string): Promise<SessionMetadata | null> {
  const metadataPath = join(sessionPath, "_metadata.json");
  try {
    const raw = await readFile(metadataPath, "utf-8");
    return JSON.parse(raw) as SessionMetadata;
  } catch {
    return null;
  }
}

/** Write session metadata to _metadata.json. */
async function writeMetadata(
  sessionPath: string,
  metadata: SessionMetadata
): Promise<void> {
  const metadataPath = join(sessionPath, "_metadata.json");
  await writeFile(metadataPath, JSON.stringify(metadata, null, 2) + "\n");
}

/**
 * Filter a transcript file and write only user/assistant messages to agent_logs.
 * Each output line is just the "message" object from matching entries.
 * Handles both formats:
 * - stream-json: { type: "user"|"assistant", message: {...} } → extract message
 * - Claude transcript: { role: "user"|"assistant", ... } → keep as-is
 *
 * If lastAssistantMessage is provided, it's appended as the final assistant
 * entry when the transcript's last filtered entry is not an assistant message.
 * This handles a race condition where the Stop hook fires before the final
 * assistant message is flushed to the transcript file on disk. The hook
 * receives last_assistant_message in memory (via hook input), but the
 * transcript file may lag by one entry.
 */
async function filterTranscriptToAgentLogs(
  sessionPath: string,
  agentName: string,
  runId: string,
  transcriptPath: string,
  lastAssistantMessage?: string
): Promise<void> {
  const agentLogsDir = join(sessionPath, "agent_logs");
  if (!existsSync(agentLogsDir)) {
    await mkdir(agentLogsDir, { recursive: true });
  }

  const destPath = join(agentLogsDir, `${agentName}-${runId}.jsonl`);

  try {
    if (!existsSync(transcriptPath)) return;

    const content = await readFile(transcriptPath, "utf-8");
    const lines = content.trim().split("\n");
    const filtered: string[] = [];

    for (const line of lines) {
      try {
        const entry = JSON.parse(line);
        let message: Record<string, unknown> | null = null;
        if (entry.message && (entry.type === "user" || entry.type === "assistant")) {
          // stream-json format: extract only the message field
          message = entry.message as Record<string, unknown>;
        } else if (entry.role === "user" || entry.role === "assistant") {
          // Claude transcript format: already a message
          message = entry;
        }
        if (message && !isSkillSetupMessage(message)) {
          filtered.push(JSON.stringify(message));
        }
      } catch {
        continue;
      }
    }

    // Race condition fix: if the last filtered entry is not an assistant
    // message, the final assistant response hasn't been written to the
    // transcript yet. Append it from the hook input's last_assistant_message.
    if (lastAssistantMessage) {
      const lastEntryIsAssistant =
        filtered.length > 0 &&
        (() => {
          try {
            return JSON.parse(filtered[filtered.length - 1]).role === "assistant";
          } catch {
            return false;
          }
        })();

      if (!lastEntryIsAssistant) {
        filtered.push(
          JSON.stringify({
            role: "assistant",
            content: lastAssistantMessage,
          })
        );
      }
    }

    if (filtered.length > 0) {
      await writeFile(destPath, filtered.join("\n") + "\n");
    }
  } catch {
    // Transcript may not be readable — non-critical
  }
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
  // Use parent's session directory for delegated sessions, derive for normal ones
  const sessionId = getSessionId(input);

  // Create session directory (no-op if already exists, needed for delegated sessions)
  const sessionPath = join(sessionsDir, sessionId);
  await mkdir(sessionPath, { recursive: true });

  // Create agent_logs subdirectory
  const agentLogsDir = join(sessionPath, "agent_logs");
  await mkdir(agentLogsDir, { recursive: true });

  // Determine agent name: use agent_type from hook input if --agent was used,
  // otherwise default to "global"
  const agentName = input.agent_type ?? "global";

  // Generate or reuse agent run ID.
  // Delegated sessions get it from env (set by delegate.ts).
  // Normal sessions generate a new one.
  let runId = process.env.CRYPLATIVE_AGENT_RUN_ID;
  if (!runId) {
    runId = generateRunId();
  }

  // For delegated sessions: don't write _metadata.json (would overwrite parent's).
  // But DO write CLAUDE_AGENT_NAME to CLAUDE_ENV_FILE so that Bash tool commands
  // (e.g., delegate.ts) in the child know which agent is running. Without this,
  // the inherited CLAUDE_AGENT_NAME from the parent's env leaks through and
  // delegation entries incorrectly attribute the child as the parent agent.
  if (isDelegatedSession()) {
    const envFile = process.env.CLAUDE_ENV_FILE;
    if (envFile) {
      await appendFile(envFile, `export CLAUDE_AGENT_NAME="${agentName}"\n`);
    }
    process.exit(0);
  }

  // Write metadata file so other hooks can read the run_id and transcript_path.
  // This is necessary because CLAUDE_ENV_FILE exports don't propagate to hook
  // processes — only to Bash tool commands.
  await writeMetadata(sessionPath, {
    run_id: runId,
    agent_name: agentName,
    transcript_path: input.transcript_path,
  });

  // Write environment variables to CLAUDE_ENV_FILE so they propagate to Bash commands.
  const envFile = process.env.CLAUDE_ENV_FILE;
  if (envFile) {
    await appendFile(envFile, `export CRYPLATIVE_SESSION_ID="${sessionId}"\n`);
    await appendFile(envFile, `export CLAUDE_AGENT_NAME="${agentName}"\n`);
    await appendFile(envFile, `export CLAUDE_SESSION_ID="${input.session_id}"\n`);
    await appendFile(envFile, `export CRYPLATIVE_AGENT_RUN_ID="${runId}"\n`);
  }

  process.exit(0);
}

async function handleUserPromptSubmit(sessionsDir: string, input: HookInput) {
  // In delegated mode, skip conversation logging — delegate.ts already writes
  // the delegation entry to _conversation.jsonl with the prompt.
  if (isDelegatedSession()) {
    process.exit(0);
  }

  const sessionId = getSessionId(input);
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

  // Get run_id from metadata (written by SessionStart hook)
  const runId = (await readMetadata(sessionPath))?.run_id;

  if (isPrintMode()) {
    // Print mode (-p flag): log the first prompt as "initial_prompt" only.
    if (await hasInitialPromptEntry(conversationFile)) {
      process.exit(0);
    }

    const entry = {
      type: "initial_prompt",
      timestamp: new Date().toISOString(),
      from_agent: agentName,
      prompt,
      ...(runId && { agent_run_id: runId }),
    };

    await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  } else {
    // Interactive mode: log ALL user prompts as "user_prompt".
    const entry = {
      type: "user_prompt",
      timestamp: new Date().toISOString(),
      from_agent: agentName,
      prompt,
      ...(runId && { agent_run_id: runId }),
    };

    await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  }

  process.exit(0);
}

async function handleStop(sessionsDir: string, input: HookInput) {
  const sessionId = getSessionId(input);
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

  // Get run_id: from env for delegated sessions, from metadata for normal ones
  const metadata = await readMetadata(sessionPath);
  const runId = getRunId() ?? metadata?.run_id;

  // In delegated mode, skip conversation logging — delegate.ts already writes
  // the response entry to _conversation.jsonl. But still copy transcript to
  // agent_logs for debugging and audit trail.
  if (!isDelegatedSession()) {
    const conversationFile = join(sessionPath, "_conversation.jsonl");

    const entry = {
      type: "response",
      timestamp: new Date().toISOString(),
      from_agent: agentName,
      response_preview: lastMessage.substring(0, 500),
      ...(runId && { agent_run_id: runId }),
    };

    await appendFile(conversationFile, JSON.stringify(entry) + "\n");
  }

  // Copy the session transcript to agent_logs.
  // Use transcript_path from hook input (Stop includes it), falling back to
  // the transcript_path stored in metadata by SessionStart.
  // Pass last_assistant_message so the final response is guaranteed to be
  // in the log even if the transcript file hasn't been flushed yet.
  const transcriptPath =
    input.transcript_path ?? metadata?.transcript_path;
  const cleanLastMessage = extractCleanResponse(lastMessage);
  if (transcriptPath && runId) {
    await filterTranscriptToAgentLogs(
      sessionPath,
      agentName,
      runId,
      transcriptPath,
      cleanLastMessage
    );
  }

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
 * Claude Code transcript file.
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
  const sessionId = getSessionId(input);
  const subagentType = input.agent_type ?? "";
  const rawMessage = input.last_assistant_message ?? "";

  // Skip empty agent_type — these are Claude Code internal subagents
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

  // Generate a fresh run_id for this sub-agent invocation
  const runId = generateRunId();

  // Determine the parent agent and the prompt given to the subagent
  const parentAgent = await findParentAgent(conversationFile);
  const prompt = await extractSubagentPrompt(input);

  // Clean the response: extract text content, strip thinking/tool blocks
  const cleanResponse = extractCleanResponse(rawMessage);

  // Log a delegation entry to record that an internal subagent call occurred.
  const delegationEntry = {
    type: "delegation",
    timestamp: new Date().toISOString(),
    from_agent: parentAgent,
    delegation_type: "internal",
    prompt,
    delegation_id: delegationId,
    agent_run_id: runId,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(delegationEntry) + "\n"
  );

  // Log the response entry linked to the delegation via delegation_id.
  const stopEntry = {
    type: "response",
    timestamp: new Date().toISOString(),
    from_agent: subagentType,
    response_preview: cleanResponse.substring(0, 500),
    delegation_id: delegationId,
    agent_run_id: runId,
  };

  await appendFile(conversationFile, JSON.stringify(stopEntry) + "\n");

  // Copy the subagent's transcript to agent_logs.
  // Pass cleanResponse so the final response is guaranteed to be in the log
  // even if the transcript file hasn't been flushed yet.
  const agentTranscriptPath = input[
    "agent_transcript_path"
  ] as string | undefined;
  if (agentTranscriptPath) {
    await filterTranscriptToAgentLogs(
      sessionPath,
      subagentType,
      runId,
      agentTranscriptPath,
      cleanResponse
    );
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
