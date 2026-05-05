#!/usr/bin/env bun
/**
 * inject-expertise.ts
 *
 * Hook for SessionStart, UserPromptSubmit, and Stop events that automates
 * expertise management.
 *
 * SessionStart:
 *   Records the session start timestamp (for later mtime comparison) and
 *   reads the agent's expertise index file, injecting it into the
 *   conversation as initial context.
 *
 * UserPromptSubmit:
 *   Injects an expertise reminder and resets the Stop block counter so each
 *   new prompt cycle gets a fresh expertise check at the end.
 *
 * Stop:
 *   Uses the advanced Stop hook API ("decision": "block") to prevent session
 *   exit when the agent hasn't updated its expertise files. The hook checks
 *   file mtimes against the recorded session start time. If no update is
 *   detected, it blocks the exit and feeds a prompt back to the agent
 *   instructing it to update expertise. Blocks at most once per prompt cycle
 *   (the counter resets on each UserPromptSubmit) to prevent infinite loops.
 *
 * State files (hidden, inside the session directory):
 *   .claude/sessions/{session_id}/._expertise_start       — timestamp (ms)
 *   .claude/sessions/{session_id}/._expertise_prompt_count — counter (max 1, reset per prompt)
 *
 * Only activates for named agents (via --agent flag). Skips global sessions.
 * Always exits 0 (non-blocking).
 *
 * Reference: Ralph Wiggum plugin stop-hook pattern for the advanced
 * Stop hook API (decision: block / reason / systemMessage).
 */

import { readFile, writeFile, mkdir, stat, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";

// ---------- types ----------

interface HookInput {
  session_id: string;
  cwd: string;
  hook_event_name: string;
  transcript_path?: string;
  agent_type?: string;
  prompt?: string;
  [key: string]: unknown;
}

const MAX_BLOCK_ATTEMPTS = 1;

// ---------- Session ID derivation ----------

/**
 * Derive a deterministic session ID from the Claude session ID.
 * Same logic as session-logger.ts — SHA-256 hash formatted as UUID.
 * Duplicated to avoid a shared module dependency; extract if a third
 * consumer appears.
 */
function deriveSessionId(claudeSessionId: string): string {
  const hash = createHash("sha256")
    .update(claudeSessionId)
    .digest("hex");
  const h = hash;
  return [
    h.slice(0, 8),
    h.slice(8, 12),
    "4" + h.slice(13, 16),
    ((parseInt(h.slice(16, 17), 16) & 0x3) | 0x8).toString(16) +
      h.slice(17, 20),
    h.slice(20, 32),
  ].join("-");
}

// ---------- State helpers ----------

/** Record the session start timestamp for later mtime comparison. */
async function recordSessionStart(
  sessionsDir: string,
  sessionId: string
): Promise<void> {
  const sessionPath = join(sessionsDir, sessionId);
  await mkdir(sessionPath, { recursive: true });
  await writeFile(
    join(sessionPath, "._expertise_start"),
    String(Date.now())
  );
}

/**
 * Check if any non-hidden file in the expertise directory was modified
 * since the recorded session start time. Uses a 1-second buffer to
 * avoid false positives from writes that happen right at session start.
 */
async function checkExpertiseUpdated(
  cwd: string,
  agentName: string,
  sessionsDir: string,
  sessionId: string
): Promise<boolean> {
  const startTimeFile = join(sessionsDir, sessionId, "._expertise_start");
  try {
    const startTimeStr = await readFile(startTimeFile, "utf-8");
    const startTime = parseInt(startTimeStr.trim(), 10) - 1000; // 1s buffer
    if (isNaN(startTime)) return false;

    const expertiseDir = join(cwd, ".agentic", "expertise", agentName);
    if (!existsSync(expertiseDir)) return false;

    const entries = await readdir(expertiseDir);
    for (const entry of entries) {
      if (entry.startsWith(".")) continue; // skip hidden files
      const filePath = join(expertiseDir, entry);
      const fileStat = await stat(filePath);
      if (fileStat.isFile() && fileStat.mtimeMs > startTime) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

/** Get the current block attempt count for this session. */
async function getBlockCount(
  sessionsDir: string,
  sessionId: string
): Promise<number> {
  const countFile = join(sessionsDir, sessionId, "._expertise_prompt_count");
  try {
    const content = await readFile(countFile, "utf-8");
    return parseInt(content.trim(), 10) || 0;
  } catch {
    return 0;
  }
}

/** Reset the block counter (called on each new UserPromptSubmit). */
async function resetBlockCount(
  sessionsDir: string,
  sessionId: string
): Promise<void> {
  const countFile = join(sessionsDir, sessionId, "._expertise_prompt_count");
  if (existsSync(countFile)) {
    await writeFile(countFile, "0");
  }
}

/** Increment and return the block attempt count. */
async function incrementBlockCount(
  sessionsDir: string,
  sessionId: string
): Promise<number> {
  const sessionPath = join(sessionsDir, sessionId);
  await mkdir(sessionPath, { recursive: true });
  const countFile = join(sessionPath, "._expertise_prompt_count");
  const current = await getBlockCount(sessionsDir, sessionId);
  const next = current + 1;
  await writeFile(countFile, String(next));
  return next;
}

// ---------- main ----------

async function main() {
  const raw = await Bun.stdin.text();
  let input: HookInput;
  try {
    input = JSON.parse(raw) as HookInput;
  } catch {
    process.exit(0);
  }

  const agentName = input.agent_type;
  if (!agentName) {
    process.exit(0);
  }

  const sessionId = deriveSessionId(input.session_id);
  const sessionsDir = join(input.cwd, ".claude", "sessions");

  if (input.hook_event_name === "SessionStart") {
    await handleSessionStart(input.cwd, agentName, sessionId, sessionsDir);
  } else if (input.hook_event_name === "UserPromptSubmit") {
    await handleUserPromptSubmit(sessionId, sessionsDir);
  } else if (input.hook_event_name === "Stop") {
    await handleStop(input.cwd, agentName, sessionId, sessionsDir);
  }

  process.exit(0);
}

// ---------- SessionStart ----------

async function handleSessionStart(
  cwd: string,
  agentName: string,
  sessionId: string,
  sessionsDir: string
) {
  // Record start time for the Stop hook's mtime comparison
  await recordSessionStart(sessionsDir, sessionId);

  // Inject expertise content
  const expertiseIndex = join(
    cwd,
    ".agentic",
    "expertise",
    agentName,
    `${agentName}-index.yaml`
  );

  if (!existsSync(expertiseIndex)) {
    process.exit(0);
  }

  try {
    const content = await readFile(expertiseIndex, "utf-8");

    process.stdout.write(
      `<expertise-context>\n` +
        `Your expertise index is loaded below. Review it for relevant context before starting your task. It contains links to relevant files that you may want to read after understanding the scope of your task.\n` +
        `---\n` +
        `${content.trim()}\n` +
        `</expertise-context>\n`
    );
  } catch {
    // File unreadable — non-critical
  }
}

// ---------- UserPromptSubmit ----------

async function handleUserPromptSubmit(
  sessionId: string,
  sessionsDir: string
) {
  // Reset the block counter so each prompt cycle gets a fresh expertise check
  await resetBlockCount(sessionsDir, sessionId);

  process.stdout.write(
    `<expertise-reminder>Remember to read your expertise file to get the task in context.</expertise-reminder>\n`
  );
}

// ---------- Stop ----------

async function handleStop(
  cwd: string,
  agentName: string,
  sessionId: string,
  sessionsDir: string
) {
  // If there's no expertise directory, nothing to check or remind about
  const expertiseDir = join(cwd, ".agentic", "expertise", agentName);
  if (!existsSync(expertiseDir)) {
    process.exit(0);
  }

  // Check if expertise files were modified since session start
  const updated = await checkExpertiseUpdated(
    cwd,
    agentName,
    sessionsDir,
    sessionId
  );
  if (updated) {
    // Agent already updated expertise — allow exit
    process.exit(0);
  }

  // No expertise update detected — check if we've already blocked enough
  const blockCount = await getBlockCount(sessionsDir, sessionId);
  if (blockCount >= MAX_BLOCK_ATTEMPTS) {
    // Already blocked MAX_BLOCK_ATTEMPTS times — allow exit to prevent
    // infinite loops
    process.exit(0);
  }

  // Increment the counter and block the exit using the advanced Stop hook API
  await incrementBlockCount(sessionsDir, sessionId);

  const systemMessage = `As an expert agent, you MUST check updating your knowledge base before exiting.
  Use the agent-expertise skill for instruction on how to update your expertise files.
  If you genuinely have nothing new to learn or record from this session, say just "No update needed for my mental model".`;

  const reason = `Update expertise check`;

  // Output JSON using the advanced Stop hook API to block exit and feed
  // the prompt back to the agent
  process.stdout.write(
    JSON.stringify({
      decision: "block",
      reason,
      systemMessage,
    })
  );
}

main().catch(() => process.exit(0));
