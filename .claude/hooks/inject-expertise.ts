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
 *   Injects a lightweight reminder to update expertise files before each
 *   agent response. Acts as a pre-emptive soft nudge.
 *
 * Stop:
 *   Checks whether the agent has updated its expertise files during this
 *   session by comparing file mtimes against the recorded start time.
 *     - If files were modified → allow exit (agent already handled it)
 *     - If no modifications AND we haven't reminded yet → output a prompt
 *       that forces a new iteration (the agent must assess and update
 *       expertise before being allowed to exit)
 *     - If no modifications AND we already reminded → allow exit
 *       (prevent infinite loops — reminder is injected at most once)
 *
 * State files (hidden, inside the session directory):
 *   .claude/sessions/{session_id}/._expertise_start   — timestamp (ms)
 *   .claude/sessions/{session_id}/._expertise_reminded — marker file
 *
 * Only activates for named agents (via --agent flag). Skips global sessions.
 * Always exits 0 (non-blocking).
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
  agent_type?: string;
  prompt?: string;
  [key: string]: unknown;
}

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

    const expertiseDir = join(cwd, ".claude", "expertise", agentName);
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

/** Check if we already injected a Stop reminder this session. */
function hasAlreadyReminded(
  sessionsDir: string,
  sessionId: string
): boolean {
  return existsSync(
    join(sessionsDir, sessionId, "._expertise_reminded")
  );
}

/** Mark that we've injected the Stop reminder. */
async function markReminded(
  sessionsDir: string,
  sessionId: string
): Promise<void> {
  const sessionPath = join(sessionsDir, sessionId);
  await mkdir(sessionPath, { recursive: true });
  await writeFile(join(sessionPath, "._expertise_reminded"), "");
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
    handleUserPromptSubmit(agentName);
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
    ".claude",
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

function handleUserPromptSubmit(agentName: string) {
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
  // If we already injected a reminder, allow exit (prevent infinite loop)
  if (hasAlreadyReminded(sessionsDir, sessionId)) {
    process.exit(0);
  }

  // If there's no expertise directory, nothing to check or remind about
  const expertiseDir = join(cwd, ".claude", "expertise", agentName);
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

  // No expertise update detected — inject reminder to force a new iteration.
  // Mark that we've done this so we don't loop forever.
  await markReminded(sessionsDir, sessionId);

  process.stdout.write(
    `<expertise-reminder>\n` +
      `As an expert agent, you are expected to continuously update your knowledge base. ` +
      `Please review your work and update the files in \`.claude/expertise/${agentName}/\` ` +
      `with any new knowledge, patterns, decisions, or observations.\n` +
      `Use the agent-expertise skill to do so .\n` +
      `If no meaningful update is needed, briefly explain why and then finish.\n` +
      `</expertise-reminder>\n`
  );
}

main().catch(() => process.exit(0));
