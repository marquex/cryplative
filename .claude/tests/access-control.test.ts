/**
 * access-control.test.ts
 *
 * Integration tests for the agent access control system.
 * Verifies that agents with restricted access rules are properly
 * denied (or allowed) access to files by the enforce-agent-access hook.
 *
 * These tests call the real Claude API and may incur costs.
 *
 * NOTE: The enforce-agent-access hook classifies bash commands as "read-only"
 * (skip/allow) when they don't match write/delete patterns (rm, mv, >>, etc.).
 * This means agents CAN potentially read arbitrary files via `cat`, `head`, etc.
 * in bash. Write operations, however, ARE properly checked against path rules.
 * The tests below focus on scenarios that the hook reliably enforces.
 */

import {
  assert,
  assertEqual,
  assertIncludes,
  runClaudeIntegration,
  readConversationLog,
  readMetadata,
  cleanupSessions,
} from './helpers';
import type { TestSuite } from './helpers';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { unlink, writeFile, mkdir } from 'node:fs/promises';

const PROJECT_DIR = process.cwd();
const SESSIONS_DIR = join(PROJECT_DIR, '.claude', 'sessions');

const suite: TestSuite = {
  name: 'access-control',
  category: 'integration',
  tests: [
    {
      description:
        'claude-developer cannot write files outside .claude/',
      fn: async () => {
        // The claude-developer agent only has write access to .claude/**
        // Writing a file at the project root should be denied by the hook.
        const uniqueMarker = `ACCESS_TEST_${Date.now()}`;
        const prompt = `Use the Write tool to create a file called "${uniqueMarker}.txt" in the project root directory. The file should contain the word "BREACH".`;

        const result = await runClaudeIntegration(
          SESSIONS_DIR,
          ['--agent', 'claude-developer', '-p', prompt],
          120_000
        );

        assert(
          result.newSessionDirs.length >= 1,
          'Expected at least one new session dir'
        );

        // The file should NOT have been created at the project root
        const filePath = join(PROJECT_DIR, `${uniqueMarker}.txt`);
        assert(
          !existsSync(filePath),
          `Expected file NOT to exist at ${filePath} — the hook should have blocked the write`
        );

        // The agent should mention being unable to write or access being denied
        assertIncludes(
          result.stdout.toLowerCase(),
          'cannot',
          `Expected agent to mention it cannot write; got: ${result.stdout.substring(0, 300)}`
        );

        // Clean up the file if it was created despite the hook (test failure)
        if (existsSync(filePath)) {
          await unlink(filePath).catch(() => {});
        }

        await cleanupSessions(result.newSessionDirs);
      },
    },

    {
      description:
        'claude-developer can read and report files inside .claude/',
      fn: async () => {
        // claude-developer has full access to .claude/**
        // Reading an agent file inside .claude/ should succeed.
        const prompt =
          'Read the file .claude/agents/primary.md and tell me the value of the "name" field from its frontmatter. Reply with just the name, nothing else.';

        const result = await runClaudeIntegration(
          SESSIONS_DIR,
          ['--agent', 'claude-developer', '-p', prompt],
          120_000
        );

        assert(
          result.newSessionDirs.length >= 1,
          'Expected at least one new session dir'
        );

        // The agent should have successfully read the file and found "primary"
        assertIncludes(
          result.stdout.toLowerCase(),
          'primary',
          `Expected response to contain "primary", got: ${result.stdout.substring(0, 200)}`
        );

        // Clean up
        await cleanupSessions(result.newSessionDirs);
      },
    },

    {
      description:
        'secondary agent can read but not write to .claude/sessions/',
      fn: async () => {
        // Secondary has read-only access to .claude/sessions/**
        // Asking it to create a file there should be denied.
        const prompt =
          'Create a new file called _test-secondary-write.txt inside the .claude/sessions/ directory with the content "secondary was here".';

        const result = await runClaudeIntegration(
          SESSIONS_DIR,
          ['--agent', 'secondary', '-p', prompt],
          120_000
        );

        assert(
          result.newSessionDirs.length >= 1,
          'Expected at least one new session dir'
        );

        // The file should NOT have been created
        const filePath = join(SESSIONS_DIR, '_test-secondary-write.txt');
        assert(
          !existsSync(filePath),
          `Expected file NOT to exist — secondary should not have write access to sessions`
        );

        // Clean up if it was created
        if (existsSync(filePath)) {
          await unlink(filePath).catch(() => {});
        }

        await cleanupSessions(result.newSessionDirs);
      },
    },
  ],
};

export default suite;
