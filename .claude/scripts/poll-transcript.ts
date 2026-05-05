/**
 * poll-transcript.ts
 *
 * Background process that polls a Claude Code transcript file for new entries
 * and streams filtered user/assistant messages to agent_logs in near-real-time.
 *
 * Spawns from the SessionStart hook for non-delegated sessions. Uses a line-count
 * tracker to only process new entries on each poll.
 *
 * Lifecycle:
 * 1. Polls transcript every 2 seconds, filtering role=user|assistant entries
 * 2. When a .poll-stop sentinel file appears (written by the Stop hook),
 *    switches to a drain mode: polls every 500ms for up to 3 seconds
 * 3. Exits after 3 seconds of no new entries in drain mode
 * 4. Cleans up the sentinel file on exit
 *
 * Usage: bun .claude/scripts/poll-transcript.ts <session-path> <agent-name> <run-id> <transcript-path>
 *
 * Exit conditions:
 * - .poll-stop sentinel detected AND 3 seconds elapsed with no new transcript entries
 * - Unrecoverable error (exits silently to avoid disrupting the session)
 */

import { appendFile, readFile, unlink } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

const POLL_INTERVAL = 2000; // Normal poll interval: 2 seconds
const DRAIN_INTERVAL = 500; // After sentinel: poll every 500ms
const DRAIN_TIMEOUT = 3000; // After sentinel: keep polling for 3 seconds
const NO_CHANGE_LIMIT = Math.ceil(DRAIN_TIMEOUT / DRAIN_INTERVAL); // 6 iterations

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
    return content.trimStart().startsWith("<command-message>");
  }
  if (Array.isArray(content) && content.length > 0) {
    const first = content[0];
    if (
      first &&
      typeof first === "object" &&
      first.type === "text" &&
      typeof first.text === "string"
    ) {
      return first.text.trimStart().startsWith("<command-message>");
    }
  }
  return false;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 4) {
    process.exit(1);
  }

  const [sessionPath, agentName, runId, transcriptPath] = args as [
    string,
    string,
    string,
    string,
  ];
  const agentLogsDir = join(sessionPath, "agent_logs");
  const agentLogsPath = join(agentLogsDir, `${agentName}-${runId}.jsonl`);
  const sentinelPath = join(sessionPath, ".poll-stop");

  // Ignore SIGHUP so the poller survives if the parent process exits
  process.on("SIGHUP", () => {});

  let processedLines = 0;
  let sentinelDetected = false;
  let noChangeCount = 0;

  while (true) {
    // Check for stop sentinel
    if (!sentinelDetected && existsSync(sentinelPath)) {
      sentinelDetected = true;
      noChangeCount = 0;
    }

    // Check if transcript file exists yet
    if (!existsSync(transcriptPath)) {
      if (sentinelDetected) {
        noChangeCount++;
        if (noChangeCount >= NO_CHANGE_LIMIT) break;
        await sleep(DRAIN_INTERVAL);
      } else {
        await sleep(POLL_INTERVAL);
      }
      continue;
    }

    // Read the transcript and process new lines
    try {
      const content = await readFile(transcriptPath, "utf-8");
      const lines = content.trim() ? content.trim().split("\n") : [];

      if (lines.length > processedLines) {
        // New entries found — reset the no-change counter
        noChangeCount = 0;

        const newLines = lines.slice(processedLines);

        for (const line of newLines) {
          try {
            const entry = JSON.parse(line);
            if (
              (entry.role === "user" || entry.role === "assistant") &&
              !isSkillSetupMessage(entry)
            ) {
              await appendFile(agentLogsPath, JSON.stringify(entry) + "\n");
            }
          } catch {
            // Malformed line — skip
            continue;
          }
        }

        processedLines = lines.length;
      } else {
        // No new lines since last poll
        noChangeCount++;
      }
    } catch {
      // Transcript may be temporarily unavailable (e.g., being rotated)
      noChangeCount++;
    }

    // In drain mode, exit after NO_CHANGE_LIMIT consecutive polls with no new entries
    if (sentinelDetected && noChangeCount >= NO_CHANGE_LIMIT) {
      break;
    }

    await sleep(sentinelDetected ? DRAIN_INTERVAL : POLL_INTERVAL);
  }

  // Clean up sentinel file
  try {
    if (existsSync(sentinelPath)) {
      await unlink(sentinelPath);
    }
  } catch {
    // Ignore cleanup errors
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
