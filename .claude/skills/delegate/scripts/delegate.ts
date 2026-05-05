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
import { existsSync, readFileSync } from "node:fs";
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
  const fromAgent = process.env.CLAUDE_AGENT_NAME || "global";

  // Enforce subordinates hierarchy before delegating.
  // Read the calling agent's frontmatter and verify the target is listed
  // as a subordinate. This is a belt-and-suspenders check alongside the
  // enforce-agent-access PreToolUse hook.
  if (fromAgent !== "global") {
    const validationError = validateDelegation(fromAgent, agentName, projectDir);
    if (validationError) {
      console.error(validationError);
      process.exit(1);
    }
  }

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
 * Minimal YAML frontmatter parser — extracts the 'subordinates' list.
 * Reuses the same pattern as enforce-agent-access.ts parseFrontmatter.
 */
function stripQuotes(s: string): string {
  if (!s) return s;
  if ((s.startsWith('"') && s.endsWith('"')) ||
      (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}

function parseSubordinatesFromFrontmatter(md: string): string[] {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return [];
  const body = m[1]!;
  const lines = body.split(/\r?\n/);
  const subordinates: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim()) { i++; continue; }

    // Block form: subordinates:\n  - agent1\n  - agent2
    if (/^subordinates\s*:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const l = lines[i]!;
        if (l.length && !/^\s/.test(l)) break;
        if (!l.trim()) { i++; continue; }
        const itemMatch = l.match(/^\s*-\s*(.+?)\s*$/);
        if (itemMatch) subordinates.push(stripQuotes(itemMatch[1]!));
        i++;
      }
      return subordinates;
    }

    // Inline form: subordinates: [agent1, agent2]
    const kv = line.match(/^subordinates\s*:\s*(.*)$/);
    if (kv) {
      const rawVal = stripQuotes(kv[1]!.trim());
      if (rawVal.startsWith('[') && rawVal.endsWith(']')) {
        return rawVal
          .slice(1, -1)
          .split(',')
          .map((s) => stripQuotes(s.trim()))
          .filter(Boolean);
      }
    }
    i++;
  }
  return subordinates;
}

/**
 * Validate that the calling agent is allowed to delegate to the target agent.
 * Returns an error message string if delegation is not allowed, or null if OK.
 */
function validateDelegation(fromAgent: string, targetAgent: string, projectDir: string): string | null {
  const agentFile = join(projectDir, ".claude", "agents", `${fromAgent}.md`);
  if (!existsSync(agentFile)) {
    return `Delegation error: cannot find agent file for '${fromAgent}' at ${agentFile}`;
  }

  const content = readFileSync(agentFile, "utf-8");
  const subordinates = parseSubordinatesFromFrontmatter(content);

  if (subordinates.length === 0) {
    return (
      `Delegation error: agent '${fromAgent}' has no subordinates and cannot delegate to anyone. ` +
      `Add a 'subordinates' field to the agent's frontmatter or remove the delegate skill.`
    );
  }

  if (!subordinates.includes(targetAgent)) {
    return (
      `Delegation error: agent '${fromAgent}' cannot delegate to '${targetAgent}' — ` +
      `authorized subordinates: [${subordinates.join(", ")}]`
    );
  }

  return null;
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

/**
 * Extract text content from a single message object.
 * Handles both string content and array of content blocks (text only).
 */
function extractTextFromMessage(message: Record<string, unknown>): string {
  const content = message.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const textParts: string[] = [];
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
    return textParts.join("\n").trim();
  }
  return "";
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
  // Note: --dangerously-skip-permissions skips permission prompts so the subagent
  //       can complete its task without getting stuck waiting for human approval
  const child = Bun.spawn(
    ["claude", "--agent", agentName, "-p", prompt, "--verbose", "--output-format", "stream-json", "--dangerously-skip-permissions"],
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
  // Stream user/assistant messages to agent_logs in real-time so logs appear
  // as the agent works, not just after it finishes.
  const agentLogsPath = join(agentLogsDir, `${agentName}-${runId}.jsonl`);
  const streamJsonLines: string[] = [];
  const reader = child.stdout.getReader();
  const decoder = new TextDecoder();

  // Progress tracking: keep the calling agent informed that the child is still running.
  // Without output, Claude Code's Bash tool may appear stuck/disconnected.
  let firstAssistantMessagePrinted = false;
  let lastAssistantText = "";
  let lastPrintedProgressMessage = "";
  let dotCount = 0;
  let isChildComplete = false;

  // Print a dot every 5 seconds to stderr (keepalive).
  // Every 60 seconds (12th dot), print the latest assistant message if it changed,
  // or a '*' wildcard if there's no new message.
  const keepaliveInterval = setInterval(() => {
    if (isChildComplete) return;
    dotCount++;
    process.stderr.write(".");

    // Every 60 seconds, print progress update
    if (dotCount % 12 === 0) {
      if (lastAssistantText && lastAssistantText !== lastPrintedProgressMessage) {
        const preview =
          lastAssistantText.length > 300
            ? lastAssistantText.substring(0, 300) + "..."
            : lastAssistantText;
        process.stderr.write(`\n${preview}\n`);
        lastPrintedProgressMessage = lastAssistantText;
      } else {
        process.stderr.write("\n*\n");
      }
    }
  }, 5000);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (!line.trim()) continue;
        streamJsonLines.push(line);

        try {
          const event = JSON.parse(line);

          // Print the first assistant message to stderr immediately as progress
          if (
            event.type === "assistant" &&
            event.message &&
            !firstAssistantMessagePrinted
          ) {
            const text = extractTextFromMessage(event.message);
            if (text) {
              process.stderr.write(`[assistant] ${text.substring(0, 300)}${text.length > 300 ? "..." : ""}\n`);
              firstAssistantMessagePrinted = true;
              lastAssistantText = text;
            }
          }

          // Track the latest assistant text for minute-by-minute progress updates
          if (event.type === "assistant" && event.message) {
            const text = extractTextFromMessage(event.message);
            if (text) {
              lastAssistantText = text;
            }
          }

          // Stream user/assistant messages to agent_logs in real-time.
          // The Stop hook checks if this file exists and skips writing if so,
          // avoiding any race condition between the two writers.
          if ((event.type === "user" || event.type === "assistant") && event.message) {
            if (!isSkillSetupMessage(event.message)) {
              await appendFile(agentLogsPath, JSON.stringify(event.message) + "\n");
            }
          }
        } catch {
          // Not valid JSON or not a message event — skip
          continue;
        }
      }
    }
  } finally {
    isChildComplete = true;
    clearInterval(keepaliveInterval);
    reader.releaseLock();
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
