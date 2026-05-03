/**
 * delegation.test.ts
 *
 * Integration tests for the delegation system.
 * Tests the delegate script directly (spawning a real claude child process)
 * and verifies that delegation + response entries appear in the session log
 * and agent_logs are created for the child agent.
 *
 * These tests call the real Claude API and may incur costs.
 */

import {
  assert,
  assertEqual,
  assertIncludes,
  runScript,
  readConversationLog,
  getSessionDirs,
} from './helpers';
import type { TestSuite } from './helpers';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { rm, readdir, readFile } from 'node:fs/promises';

const PROJECT_DIR = process.cwd();
const SESSIONS_DIR = join(PROJECT_DIR, '.claude', 'sessions');

const suite: TestSuite = {
  name: 'delegation',
  category: 'integration',
  tests: [
    {
      description:
        'delegate script creates session with delegation and response entries',
      fn: async () => {
        const testSessionId = `test-delegation-${Date.now()}`;
        const marker = `DELEGATE_PONG_${Date.now()}`;
        const prompt = `Reply with exactly the word: ${marker}`;

        await getSessionDirs(SESSIONS_DIR); // snapshot before state

        const { stdout, exitCode } = await runScript(
          '.claude/skills/delegate/scripts/delegate.ts',
          ['secondary', prompt],
          { CRYPLATIVE_SESSION_ID: testSessionId }
        );

        assertEqual(exitCode, 0, `delegate script exited with code ${exitCode}`);
        assertIncludes(
          stdout,
          marker,
          'Expected child agent response to contain the marker'
        );

        // Check the session directory
        const sessionPath = join(SESSIONS_DIR, testSessionId);
        assert(
          existsSync(sessionPath),
          `Expected session dir at ${sessionPath}`
        );
        assert(
          existsSync(join(sessionPath, '_conversation.jsonl')),
          'Expected _conversation.jsonl'
        );

        const entries = await readConversationLog(sessionPath);

        const delegations = entries.filter((e) => e.type === 'delegation');
        assertEqual(
          delegations.length,
          1,
          'Expected exactly one delegation entry'
        );
        assertEqual(
          delegations[0].delegation_type,
          'skill',
          'Expected delegation_type "skill"'
        );
        assertIncludes(
          delegations[0].prompt as string,
          marker,
          'Expected delegation prompt to contain the marker'
        );
        assert(
          delegations[0].delegation_id !== undefined,
          'Expected delegation_id on delegation entry'
        );

        const responses = entries.filter((e) => e.type === 'response');
        assert(responses.length >= 1, 'Expected at least one response entry');

        // The response from the secondary agent should be linked via delegation_id
        const delegationId = delegations[0].delegation_id as string;
        const linkedResponse = responses.find(
          (e) => e.delegation_id === delegationId
        );
        assert(
          linkedResponse !== undefined,
          'Expected a response entry linked to the delegation via delegation_id'
        );
        assertEqual(
          linkedResponse!.agent,
          'secondary',
          'Expected response agent to be "secondary"'
        );

        // Cleanup
        if (existsSync(sessionPath)) {
          await rm(sessionPath, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'delegate script creates agent_logs for the child agent',
      fn: async () => {
        const testSessionId = `test-delegation-logs-${Date.now()}`;
        const prompt = `Reply with exactly: LOG_TEST_PONG`;

        const { exitCode } = await runScript(
          '.claude/skills/delegate/scripts/delegate.ts',
          ['secondary', prompt],
          { CRYPLATIVE_SESSION_ID: testSessionId }
        );

        assertEqual(exitCode, 0, `delegate script exited with code ${exitCode}`);

        const sessionPath = join(SESSIONS_DIR, testSessionId);
        const agentLogsDir = join(sessionPath, 'agent_logs');

        assert(
          existsSync(agentLogsDir),
          'Expected agent_logs directory to exist'
        );

        // Check that at least one .jsonl file exists in agent_logs
        const files = await readdir(agentLogsDir);
        const logFiles = files.filter((f) => f.endsWith('.jsonl'));
        assert(
          logFiles.length >= 1,
          `Expected at least 1 agent_log file, got ${logFiles.length}: ${files.join(', ')}`
        );

        // The log file should be named secondary-{run_id}.jsonl
        const secondaryLogs = logFiles.filter((f) => f.startsWith('secondary-'));
        assert(
          secondaryLogs.length >= 1,
          `Expected secondary-*.jsonl in agent_logs, got: ${logFiles.join(', ')}`
        );

        // Verify the secondary agent log contains an assistant response
        // (regression test for the race condition where the final assistant
        // message wasn't flushed to the transcript before the Stop hook fired)
        const secondaryLogPath = join(agentLogsDir, secondaryLogs[0]);
        const secondaryLogContent = await readFile(secondaryLogPath, 'utf-8');
        const secondaryLogLines = secondaryLogContent.trim().split('\n');

        const assistantLines = secondaryLogLines.filter((line) => {
          try {
            return JSON.parse(line).role === 'assistant';
          } catch {
            return false;
          }
        });
        assert(
          assistantLines.length >= 1,
          `Expected at least 1 assistant message in secondary agent_log, got ${assistantLines.length} assistant lines out of ${secondaryLogLines.length} total. Log: ${secondaryLogContent.substring(0, 500)}`
        );
        assertIncludes(
          secondaryLogContent,
          'LOG_TEST_PONG',
          'Expected assistant response to contain the marker'
        );

        // Cleanup
        if (existsSync(sessionPath)) {
          await rm(sessionPath, { recursive: true, force: true });
        }
      },
    },
  ],
};

export default suite;
