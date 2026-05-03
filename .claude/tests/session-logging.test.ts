/**
 * session-logging.test.ts
 *
 * Integration tests for session logging via the claude CLI.
 * Verifies that `claude -p` and `claude --agent X -p` create proper
 * session directories with expected _conversation.jsonl entries and
 * _metadata.json files.
 *
 * These tests call the real Claude API and may incur costs.
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
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const PROJECT_DIR = process.cwd();
const SESSIONS_DIR = join(PROJECT_DIR, '.claude', 'sessions');

const suite: TestSuite = {
  name: 'session-logging',
  category: 'integration',
  tests: [
    {
      description:
        'basic claude -p creates session with user_prompt and response entries',
      fn: async () => {
        const marker = `INTEGRATION_MARKER_${Date.now()}`;
        const prompt = `Reply with exactly the word: ${marker}`;

        const result = await runClaudeIntegration(SESSIONS_DIR, ['-p', prompt]);

        assertEqual(result.exitCode, 0, `claude exited with code ${result.exitCode}`);
        assert(
          result.newSessionDirs.length >= 1,
          `Expected at least 1 new session dir, got ${result.newSessionDirs.length}`
        );

        // Inspect the newest session
        const sessionDir =
          result.newSessionDirs[result.newSessionDirs.length - 1];
        assert(
          existsSync(join(sessionDir, '_conversation.jsonl')),
          'Expected _conversation.jsonl'
        );
        assert(
          existsSync(join(sessionDir, '_metadata.json')),
          'Expected _metadata.json'
        );

        const entries = await readConversationLog(sessionDir);
        const userPrompts = entries.filter(
          (e) => e.type === 'user_prompt' || e.type === 'initial_prompt'
        );
        assert(userPrompts.length >= 1, 'Expected at least one prompt entry');

        const responses = entries.filter((e) => e.type === 'response');
        assert(responses.length >= 1, 'Expected at least one response entry');

        // Verify the response contains our marker
        const responseText = responses.map(
          (e) => (e.response_preview as string) || ''
        ).join('\n');
        assertIncludes(
          result.stdout,
          marker,
          'Expected claude output to contain the marker'
        );

        const meta = await readMetadata(sessionDir);
        assertEqual(meta!.agent_name, 'global', 'Expected agent_name "global"');
        assert(
          typeof meta!.run_id === 'string' && meta!.run_id.length === 6,
          `Expected 6-char run_id in metadata`
        );
      },
    },

    {
      description:
        'claude --agent primary -p creates session with correct agent metadata',
      fn: async () => {
        const marker = `AGENT_MARKER_${Date.now()}`;
        const prompt = `Reply with exactly the word: ${marker}`;

        const result = await runClaudeIntegration(
          SESSIONS_DIR,
          ['--agent', 'primary', '-p', prompt],
          120_000
        );

        assertEqual(result.exitCode, 0, `claude exited with code ${result.exitCode}`);
        assert(
          result.newSessionDirs.length >= 1,
          `Expected at least 1 new session dir, got ${result.newSessionDirs.length}`
        );

        const sessionDir =
          result.newSessionDirs[result.newSessionDirs.length - 1];
        const meta = await readMetadata(sessionDir);

        assert(meta !== null, 'Expected _metadata.json');
        assertEqual(
          meta!.agent_name,
          'primary',
          `Expected agent_name "primary", got "${meta!.agent_name}"`
        );

        const entries = await readConversationLog(sessionDir);
        const prompts = entries.filter(
          (e) => e.type === 'user_prompt' || e.type === 'initial_prompt'
        );
        assert(prompts.length >= 1, 'Expected prompt entry in session');
      },
    },
  ],
};

export default suite;
