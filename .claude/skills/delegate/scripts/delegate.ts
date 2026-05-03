/**
 * delegate.ts
 *
 * Delegation script that spawns a child claude process targeting a specific agent.
 * Uses --output-format stream-json to capture the full conversation event stream,
 * writes it to agent_logs/{agent-name}-{run-id}.jsonl, and logs delegation and
 * response entries to the session's _conversation.jsonl.
 *
 * Usage: bun .claude/skills/delegate/scripts/delegate.ts <agent-name> <prompt>
 *
 * Environment variables:
 *   CRYPLATIVE_SESSION_ID - Shared session ID for all agents in a chain.
 *                           Generated if not set.
 *   CRYPLATIVE_PRINT_MODE - Set to "1" for child processes spawned with -p,
 *                           so the session-logger logs the prompt as
 *                           "initial_prompt" instead of "user_prompt".
 */

import { mkdir, appendFile } from "node:fs/promises";
import { join } from "node:path";

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error(
      "Usage: bun .claude/skills/delegate/scripts/delegate.ts <agent-name> <prompt>"
    );
    process.exit(1);
  }

  const agentName = args[0];
  const prompt = args.slice(1).join(" ");
  const projectDir = process.cwd();
  const sessionsDir = join(projectDir, ".claude", "sessions");

  // Get or generate session ID
  let sessionId = process.env.CRYPLATIVE_SESSION_ID;
  if (!sessionId) {
    sessionId = crypto.randomUUID();
  }

  const delegationId = `del-${crypto.randomUUID()}`;

  // Determine the calling agent name (from env or default to "global")
  const fromAgent = process.env.CLAUDE_AGENT_NAME ?? "global";

  // Generate a 6-char run ID for this agent invocation.
  // This is passed to the child process so its hooks use the same run_id.
  const runId = generateRunId();

  runDelegation(
    sessionsDir,
    sessionId,
    delegationId,
    fromAgent,
    agentName,
    prompt,
    runId
  ).catch((err) => {
    console.error(`Delegation failed: ${(err as Error).message}`);
    process.exit(1);
  });
}

/**
 * Generate a 6-character random alphanumeric string for agent run identification.
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
 * Check if a message is a Claude Code skill setup injection.
 * These are user messages whose first content block's text starts with
 * <command-message> — they contain the full skill definition and are
 * very large, so we filter them out from agent_logs.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
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

/**
 * Extract the final text result from stream-json output.
 * Scans for the "result" event type and returns its "result" field.
 * Falls back to concatenating all assistant text content blocks.
 */
function extractTextFromStreamJson(lines: string[]): string {
  // Try to find the result event (final summary)
  for (const line of lines) {
    try {
      const event = JSON.parse(line);
      if (event.type === "result" && typeof event.result === "string") {
        return event.result;
      }
    } catch {
      continue;
    }
  }

  // Fallback: collect all text from assistant messages
  const textParts: string[] = [];
  for (const line of lines) {
    try {
      const event = JSON.parse(line);
      if (event.type === "assistant" && event.message?.content) {
        const content = event.message.content;
        if (typeof content === "string") {
          textParts.push(content);
        } else if (Array.isArray(content)) {
          for (const block of content) {
            if (
              block &&
              typeof block === "object" &&
              block.type === "text" &&
              typeof block.text === "string"
            ) {
              textParts.push(block.text);
            }
          }
        }
      }
    } catch {
      continue;
    }
  }

  return textParts.join("\n").trim();
}

async function runDelegation(
  sessionsDir: string,
  sessionId: string,
  delegationId: string,
  fromAgent: string,
  agentName: string,
  prompt: string,
  runId: string
) {
  const sessionPath = join(sessionsDir, sessionId);
  const conversationFile = join(sessionPath, "_conversation.jsonl");
  const agentLogsDir = join(sessionPath, "agent_logs");

  // Ensure session and agent_logs directories exist
  if (!(await Bun.file(sessionPath).exists())) {
    await mkdir(sessionPath, { recursive: true });
  }
  if (!(await Bun.file(agentLogsDir).exists())) {
    await mkdir(agentLogsDir, { recursive: true });
  }

  // Write delegation entry
  const delegationEntry = {
    type: "delegation",
    timestamp: new Date().toISOString(),
    agent: fromAgent,
    delegated_to: agentName,
    delegation_type: "skill",
    prompt,
    delegation_id: delegationId,
    agent_run_id: runId,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(delegationEntry) + "\n"
  );

  // Spawn child claude process with --output-format stream-json
  // Note: --verbose is required when using --output-format stream-json with --print
  const child = Bun.spawn(
    ["claude", "--agent", agentName, "-p", prompt, "--verbose", "--output-format", "stream-json"],
    {
      env: {
        ...Bun.env,
        CRYPLATIVE_SESSION_ID: sessionId,
        CRYPLATIVE_DELEGATED_SESSION: "1",
        CRYPLATIVE_PRINT_MODE: "1",
        CRYPLATIVE_AGENT_RUN_ID: runId,
        CLAUDE_AGENT_NAME: agentName,
      },
      stdout: "pipe",
      stderr: "pipe",
    }
  );

  // Read stdout stream line by line, collecting all lines for text extraction.
  // Note: agent_logs are NOT written here — the child's Stop hook handles
  // that via filterTranscriptToAgentLogs. Writing here would cause a race
  // condition with the Stop hook (both writing to the same file).
  const streamJsonLines: string[] = [];
  const reader = child.stdout.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (!line.trim()) continue;
        streamJsonLines.push(line);
      }
    }
  } finally {
    // No file handle to close — agent_logs handled by Stop hook
  }

  const stderr = await new Response(child.stderr).text();
  const exitCode = await child.exited;

  // If child failed, log stderr for diagnostics
  if (exitCode !== 0 && stderr) {
    process.stderr.write(`Child process stderr (exit ${exitCode}):\n${stderr}\n`);
  }

  // Extract the final text response from stream-json output
  const textResponse = extractTextFromStreamJson(streamJsonLines);

  // Output the child's text response to stdout (so the calling agent sees it)
  if (textResponse) {
    process.stdout.write(textResponse);
  }

  // Write response entry
  const responseEntry = {
    type: "response",
    timestamp: new Date().toISOString(),
    agent: agentName,
    delegation_id: delegationId,
    response_preview: textResponse.substring(0, 500),
    exit_code: exitCode,
    agent_run_id: runId,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(responseEntry) + "\n"
  );

  // Exit with the child's exit code
  process.exit(exitCode);
}

main();
