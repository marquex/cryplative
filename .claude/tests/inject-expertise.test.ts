/**
 * inject-expertise.test.ts
 *
 * Unit tests for the inject-expertise.ts hook.
 * Tests SessionStart expertise injection, UserPromptSubmit reminder,
 * and Stop gate (mtime check + forced continuation).
 */

import { mkdir, writeFile, rm, appendFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { createHash } from 'node:crypto';

import {
  runHook,
  assertIncludes,
  assertNotIncludes,
  assertEqual,
  assert,
} from './helpers';

const HOOK_PATH = join(
  import.meta.dir,
  '..',
  'hooks',
  'inject-expertise.ts'
);

/** Same derivation as the hook — needed to predict session directory paths. */
function deriveSessionId(claudeSessionId: string): string {
  const hash = createHash('sha256').update(claudeSessionId).digest('hex');
  const h = hash;
  return [
    h.slice(0, 8),
    h.slice(8, 12),
    '4' + h.slice(13, 16),
    ((parseInt(h.slice(16, 17), 16) & 0x3) | 0x8).toString(16) + h.slice(17, 20),
    h.slice(20, 32),
  ].join('-');
}

/**
 * Create a temp dir with fake project structure:
 *   .claude/expertise/test-agent/test-agent-index.yaml
 *   .claude/sessions/{derived-session-id}/
 */
async function createFakeProject(
  sessionId = 'test-session-123'
): Promise<string> {
  const dir = join(tmpdir(), `inject-expertise-${randomUUID()}`);
  const derivedId = deriveSessionId(sessionId);
  await mkdir(join(dir, '.claude', 'expertise', 'test-agent'), {
    recursive: true,
  });
  await mkdir(join(dir, '.claude', 'sessions', derivedId), {
    recursive: true,
  });
  return dir;
}

/** Write the start time file that SessionStart would create. */
async function writeStartTime(
  dir: string,
  sessionId = 'test-session-123',
  time?: number
): Promise<void> {
  const derivedId = deriveSessionId(sessionId);
  const startFile = join(dir, '.claude', 'sessions', derivedId, '._expertise_start');
  await writeFile(startFile, String(time ?? Date.now()));
}

/** Write the prompt count file that Stop creates. */
async function writePromptCount(
  dir: string,
  sessionId = 'test-session-123',
  count: number = 2
): Promise<void> {
  const derivedId = deriveSessionId(sessionId);
  const countFile = join(dir, '.claude', 'sessions', derivedId, '._expertise_prompt_count');
  await writeFile(countFile, String(count));
}

/** Write an expertise index file for test-agent. */
async function writeExpertiseFile(
  dir: string,
  content: string
): Promise<void> {
  await writeFile(
    join(dir, '.claude', 'expertise', 'test-agent', 'test-agent-index.yaml'),
    content
  );
}

const TEST_SESSION_ID = 'test-session-123';

export default {
  name: 'inject-expertise',
  category: 'unit' as const,
  tests: [
    // ---- SessionStart ----

    {
      description:
        'SessionStart: injects expertise content and records start time',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');

          const { stdout, exitCode } = await runHook(HOOK_PATH, {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          assertEqual(exitCode, 0, 'exit code');
          assertIncludes(stdout, '<expertise-context>', 'opening tag');
          assertIncludes(stdout, '</expertise-context>', 'closing tag');
          assertIncludes(stdout, 'key: value', 'expertise content');

          // Verify start time file was created
          const derivedId = deriveSessionId(TEST_SESSION_ID);
          const startFile = join(
            dir, '.claude', 'sessions', derivedId, '._expertise_start'
          );
          assert(existsSync(startFile), 'start time file should exist');
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'SessionStart: skips silently for global session (no agent_type)',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'SessionStart',
          session_id: TEST_SESSION_ID,
          cwd: dir,
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise-context>', 'no injection');

        await rm(dir, { recursive: true, force: true });
      },
    },

    {
      description:
        'SessionStart: skips silently when agent has no expertise folder',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'SessionStart',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          agent_type: 'nonexistent-agent',
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise-context>', 'no injection');

        await rm(dir, { recursive: true, force: true });
      },
    },

    // ---- UserPromptSubmit ----

    {
      description:
        'UserPromptSubmit: injects expertise reminder for named agent',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'UserPromptSubmit',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          agent_type: 'test-agent',
          prompt: 'do some work',
        });

        assertEqual(exitCode, 0, 'exit code');
        assertIncludes(stdout, '<expertise-reminder>', 'reminder tag');
        assertIncludes(stdout, 'expertise file', 'reminder mentions expertise');

        await rm(dir, { recursive: true, force: true });
      },
    },

    {
      description:
        'UserPromptSubmit: skips silently for global session',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'UserPromptSubmit',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          prompt: 'do some work',
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise-reminder>', 'no reminder');

        await rm(dir, { recursive: true, force: true });
      },
    },

    // ---- Stop: mtime gate ----

    {
      description:
        'Stop: allows exit when expertise files were modified after start',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');
          // Record a start time in the past
          const derivedId = deriveSessionId(TEST_SESSION_ID);
          await writeFile(
            join(dir, '.claude', 'sessions', derivedId, '._expertise_start'),
            String(Date.now() - 5000) // 5 seconds ago
          );
          // Modify expertise file (bump mtime)
          await appendFile(
            join(dir, '.claude', 'expertise', 'test-agent', 'test-agent-index.yaml'),
            'new_entry: added\n'
          );

          const { stdout, exitCode } = await runHook(HOOK_PATH, {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          assertEqual(exitCode, 0, 'exit code');
          assertNotIncludes(stdout, '<expertise', 'no reminder when updated');
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'Stop: blocks exit with JSON when no expertise files were modified',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');
          // Set start time far in the future so existing files are "old"
          await writeStartTime(dir, TEST_SESSION_ID, Date.now() + 60_000);

          const { stdout, exitCode } = await runHook(HOOK_PATH, {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          assertEqual(exitCode, 0, 'exit code');
          // Should output JSON with the advanced Stop hook API format
          const parsed = JSON.parse(stdout);
          assertEqual(parsed.decision, 'block', 'decision should be block');
          assertIncludes(parsed.reason, 'expertise', 'reason mentions expertise');
          assertIncludes(parsed.reason, '.claude/expertise/test-agent/', 'expertise path in reason');
          assertIncludes(parsed.reason, 'agent-expertise skill', 'reason mentions skill');
          assertIncludes(parsed.systemMessage, 'attempt 1', 'systemMessage shows attempt count');

          // Verify prompt count file was created (counter incremented to 1)
          const derivedId = deriveSessionId(TEST_SESSION_ID);
          assert(
            existsSync(join(dir, '.claude', 'sessions', derivedId, '._expertise_prompt_count')),
            'prompt count file should be created'
          );
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'Stop: allows exit when max block attempts reached (prevents infinite loop)',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');
          await writeStartTime(dir, TEST_SESSION_ID);
          await writePromptCount(dir, TEST_SESSION_ID, 1); // already at max
          // Files not modified, but we already blocked max times — should allow exit

          const { stdout, exitCode } = await runHook(HOOK_PATH, {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          assertEqual(exitCode, 0, 'exit code');
          assertEqual(stdout, '', 'no output when max blocks reached');
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'UserPromptSubmit resets block counter so Stop can block again',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');
          await writeStartTime(dir, TEST_SESSION_ID, Date.now() + 60_000);
          await writePromptCount(dir, TEST_SESSION_ID, 1); // already at max

          // UserPromptSubmit should reset the counter
          await runHook(HOOK_PATH, {
            hook_event_name: 'UserPromptSubmit',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
            prompt: 'new task',
          });

          // Stop should now block again (counter was reset to 0)
          const { stdout, exitCode } = await runHook(HOOK_PATH, {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          assertEqual(exitCode, 0, 'exit code');
          const parsed = JSON.parse(stdout);
          assertEqual(parsed.decision, 'block', 'should block again after reset');
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },

    {
      description:
        'Stop: allows exit for global session (no agent_type)',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'Stop',
          session_id: TEST_SESSION_ID,
          cwd: dir,
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise', 'no reminder for global');

        await rm(dir, { recursive: true, force: true });
      },
    },

    {
      description:
        'Stop: allows exit when no expertise directory exists',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        await writeStartTime(dir, TEST_SESSION_ID);
        // No expertise dir for test-agent-other at all

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'Stop',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          agent_type: 'test-agent-other',
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise', 'no reminder without expertise dir');

        await rm(dir, { recursive: true, force: true });
      },
    },

    {
      description:
        'Stop: blocks exit when start time file is missing (graceful fallback)',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        await writeExpertiseFile(dir, 'key: value\n');
        // No ._expertise_start file — session wasn't started by this hook

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'Stop',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          agent_type: 'test-agent',
        });

        assertEqual(exitCode, 0, 'exit code');
        // When start time is missing, checkExpertiseUpdated returns false,
        // so the block is triggered. That's acceptable — it's a fallback
        // that ensures the agent gets at least one reminder.
        const parsed = JSON.parse(stdout);
        assertEqual(parsed.decision, 'block', 'blocks as fallback');

        await rm(dir, { recursive: true, force: true });
      },
    },

    // ---- Edge cases ----

    {
      description:
        'handles malformed JSON input gracefully',
      async fn() {
        const stdinPath = join(tmpdir(), `hook-stdin-${randomUUID()}.json`);
        await writeFile(stdinPath, 'not json at all');

        try {
          const child = Bun.spawn(['bun', HOOK_PATH], {
            stdout: 'pipe',
            stderr: 'pipe',
            stdin: Bun.file(stdinPath),
            env: {
              ...Bun.env,
              CRYPLATIVE_SESSION_ID: '',
              CRYPLATIVE_DELEGATED_SESSION: '',
              CRYPLATIVE_PRINT_MODE: '',
              CRYPLATIVE_AGENT_RUN_ID: '',
              CLAUDE_AGENT_NAME: '',
              CLAUDE_ENV_FILE: '',
            },
          });

          const stdout = await new Response(child.stdout).text();
          const exitCode = await child.exited;

          assertEqual(exitCode, 0, 'exit code');
          assertNotIncludes(stdout, '<expertise', 'no injection on bad input');
        } finally {
          if (existsSync(stdinPath)) {
            await rm(stdinPath, { force: true });
          }
        }
      },
    },

    {
      description:
        'handles unknown hook event gracefully',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);

        const { stdout, exitCode } = await runHook(HOOK_PATH, {
          hook_event_name: 'UnknownEvent',
          session_id: TEST_SESSION_ID,
          cwd: dir,
          agent_type: 'test-agent',
        });

        assertEqual(exitCode, 0, 'exit code');
        assertNotIncludes(stdout, '<expertise', 'no injection for unknown event');

        await rm(dir, { recursive: true, force: true });
      },
    },

    {
      description:
        'SessionStart: expertise content comes after separator',
      async fn() {
        const dir = await createFakeProject(TEST_SESSION_ID);
        try {
          await writeExpertiseFile(dir, 'key: value\n');

          const { stdout } = await runHook(HOOK_PATH, {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: dir,
            agent_type: 'test-agent',
          });

          const separatorIdx = stdout.indexOf('---');
          const contentIdx = stdout.indexOf('key: value');
          assert(
            contentIdx > separatorIdx,
            'expertise content should come after separator'
          );
        } finally {
          await rm(dir, { recursive: true, force: true });
        }
      },
    },
  ],
};
