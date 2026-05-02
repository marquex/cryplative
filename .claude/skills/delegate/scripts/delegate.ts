/**
 * delegate.ts
 *
 * Delegation script that spawns a child claude process targeting a specific agent.
 * Logs delegation and response entries to the session's _conversation.jsonl.
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

  runDelegation(
    sessionsDir,
    sessionId,
    delegationId,
    fromAgent,
    agentName,
    prompt
  ).catch((err) => {
    console.error(`Delegation failed: ${(err as Error).message}`);
    process.exit(1);
  });
}

async function runDelegation(
  sessionsDir: string,
  sessionId: string,
  delegationId: string,
  fromAgent: string,
  agentName: string,
  prompt: string
) {
  const sessionPath = join(sessionsDir, sessionId);
  const conversationFile = join(sessionPath, "_conversation.jsonl");

  // Ensure session directory exists
  if (!(await Bun.file(sessionPath).exists())) {
    await mkdir(sessionPath, { recursive: true });
  }

  // Write delegation entry
  const delegationEntry = {
    type: "delegation",
    timestamp: new Date().toISOString(),
    from_agent: fromAgent,
    delegation_type: "skill",
    prompt,
    delegation_id: delegationId,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(delegationEntry) + "\n"
  );

  // Spawn child claude process using Bun.spawn
  const child = Bun.spawn(
    ["claude", "--agent", agentName, "-p", prompt],
    {
      env: {
        ...Bun.env,
        CRYPLATIVE_SESSION_ID: sessionId,
        CRYPLATIVE_PRINT_MODE: "1",
      },
      stdout: "pipe",
      stderr: "pipe",
    }
  );

  const stdout = await new Response(child.stdout).text();
  const stderr = await new Response(child.stderr).text();
  const exitCode = await child.exited;

  // Output the child's response to stdout (so the calling agent sees it)
  if (stdout) {
    process.stdout.write(stdout);
  }

  // Write response entry
  const responseEntry = {
    type: "response",
    timestamp: new Date().toISOString(),
    from_agent: agentName,
    delegation_id: delegationId,
    response_preview: stdout.substring(0, 500),
    exit_code: exitCode,
  };

  await appendFile(
    conversationFile,
    JSON.stringify(responseEntry) + "\n"
  );

  // Exit with the child's exit code
  process.exit(exitCode);
}

main();
