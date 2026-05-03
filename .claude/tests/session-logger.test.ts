/**
 * session-logger.test.ts
 *
 * Unit tests for the .claude/hooks/session-logger.ts hook.
 * Tests session creation, prompt logging, response logging, and
 * delegated-mode behavior by piping JSON hook inputs via stdin
 * and inspecting the files created in a temp project directory.
 */

import {
  runHook,
  assert,
  assertEqual,
  assertIncludes,
  createTempProject,
  cleanupTempProject,
  getSessionDirs,
  readConversationLog,
  readMetadata,
} from './helpers';
import type { TestSuite } from './helpers';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { readFile } from 'node:fs/promises';

const TEST_SESSION_ID = 'test-session-logger-unit-001';

const suite: TestSuite = {
  name: 'session-logger',
  category: 'unit',
  tests: [
    // --- SessionStart ---

    {
      description:
        'creates session directory, agent_logs, and _metadata.json on SessionStart',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          const { exitCode } = await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
            transcript_path: '/tmp/test-transcript.jsonl',
            agent_type: 'test-unit-agent',
          });
          assertEqual(exitCode, 0);

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          assert(dirs.length === 1, 'Expected exactly one session directory');

          const meta = await readMetadata(dirs[0]);
          assert(meta !== null, 'Expected _metadata.json');
          assertEqual(meta!.agent_name, 'test-unit-agent');
          assert(
            typeof meta!.run_id === 'string' && meta!.run_id.length === 6,
            `Expected 6-char run_id, got "${meta!.run_id}"`
          );

          // agent_logs subdirectory must exist
          assert(
            existsSync(join(dirs[0], 'agent_logs')),
            'Expected agent_logs subdirectory'
          );
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'defaults agent_name to "global" when agent_type is missing',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: 'test-no-agent-type',
            cwd: tmpDir,
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const meta = await readMetadata(dirs[0]);
          assertEqual(meta!.agent_name, 'global');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- UserPromptSubmit (print mode) ---

    {
      description:
        'logs initial_prompt on first UserPromptSubmit in print mode',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          // Bootstrap the session first
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          // Submit a prompt in print mode
          const { exitCode } = await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'UserPromptSubmit',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              prompt: 'Hello, test prompt',
            },
            { CRYPLATIVE_PRINT_MODE: '1' }
          );
          assertEqual(exitCode, 0);

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const entries = await readConversationLog(dirs[0]);
          const initial = entries.filter((e) => e.type === 'initial_prompt');

          assertEqual(initial.length, 1, 'Expected exactly one initial_prompt');
          assertEqual(initial[0].prompt, 'Hello, test prompt');
          assert(
            initial[0].agent_run_id !== undefined,
            'Expected agent_run_id on initial_prompt entry'
          );
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description:
        'does not duplicate initial_prompt on second UserPromptSubmit in print mode',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          // First prompt
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'UserPromptSubmit',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              prompt: 'First prompt',
            },
            { CRYPLATIVE_PRINT_MODE: '1' }
          );

          // Second prompt (should be ignored)
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'UserPromptSubmit',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              prompt: 'Second prompt',
            },
            { CRYPLATIVE_PRINT_MODE: '1' }
          );

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const entries = await readConversationLog(dirs[0]);
          const initial = entries.filter((e) => e.type === 'initial_prompt');

          assertEqual(initial.length, 1, 'Expected only one initial_prompt');
          assertEqual(initial[0].prompt, 'First prompt');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- UserPromptSubmit (interactive mode) ---

    {
      description: 'logs all prompts as user_prompt in interactive mode',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          // No CRYPLATIVE_PRINT_MODE → interactive mode
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'UserPromptSubmit',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
            prompt: 'First prompt',
          });

          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'UserPromptSubmit',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
            prompt: 'Second prompt',
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const entries = await readConversationLog(dirs[0]);
          const userPrompts = entries.filter((e) => e.type === 'user_prompt');

          assertEqual(userPrompts.length, 2, 'Expected two user_prompt entries');
          assertEqual(userPrompts[0].prompt, 'First prompt');
          assertEqual(userPrompts[1].prompt, 'Second prompt');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- Stop ---

    {
      description: 'logs summary entry on Stop event',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
            last_assistant_message: 'Agent final response here',
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const entries = await readConversationLog(dirs[0]);
          const summaries = entries.filter((e) => e.type === 'summary');

          assertEqual(summaries.length, 1, 'Expected one summary entry');
          assertIncludes(
            summaries[0].response_preview as string,
            'Agent final response here'
          );
          assert(
            summaries[0].agent_run_id !== undefined,
            'Expected agent_run_id on summary entry'
          );
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'truncates response_preview to 500 characters',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          const longResponse = 'A'.repeat(1000);
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'Stop',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
            last_assistant_message: longResponse,
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const entries = await readConversationLog(dirs[0]);
          const summary = entries.find((e) => e.type === 'summary');

          assert(
            (summary!.response_preview as string).length <= 500,
            `Expected response_preview <= 500 chars, got ${(summary!.response_preview as string).length}`
          );
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- Delegated mode ---

    {
      description: 'skips conversation logging entirely in delegated mode',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          // SessionStart in delegated mode: creates dir + agent_logs but no metadata
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'SessionStart',
              session_id: 'delegated-child-session',
              cwd: tmpDir,
            },
            {
              CRYPLATIVE_DELEGATED_SESSION: '1',
              CRYPLATIVE_SESSION_ID: 'parent-session-id',
              CRYPLATIVE_AGENT_RUN_ID: 'abc123',
            }
          );

          // UserPromptSubmit in delegated mode: should be skipped entirely
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'UserPromptSubmit',
              session_id: 'delegated-child-session',
              cwd: tmpDir,
              prompt: 'This should NOT appear in the conversation log',
            },
            {
              CRYPLATIVE_DELEGATED_SESSION: '1',
              CRYPLATIVE_SESSION_ID: 'parent-session-id',
            }
          );

          // Stop in delegated mode: should skip conversation logging
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'Stop',
              session_id: 'delegated-child-session',
              cwd: tmpDir,
              last_assistant_message: 'Delegated response',
            },
            {
              CRYPLATIVE_DELEGATED_SESSION: '1',
              CRYPLATIVE_SESSION_ID: 'parent-session-id',
              CRYPLATIVE_AGENT_RUN_ID: 'abc123',
            }
          );

          const sessionsDir = join(tmpDir, '.claude', 'sessions');
          const dirs = await getSessionDirs(sessionsDir);

          // Session dir is created (by SessionStart) but no conversation entries
          if (dirs.length > 0) {
            const entries = await readConversationLog(dirs[0]);
            assertEqual(
              entries.length,
              0,
              'Expected no conversation entries in delegated mode'
            );

            // _metadata.json should NOT exist (delegated SessionStart exits early)
            const meta = await readMetadata(dirs[0]);
            assert(
              meta === null,
              'Expected no _metadata.json in delegated mode'
            );
          }
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- Edge cases ---

    {
      description: 'no-ops when session directory does not exist for UserPromptSubmit',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          // Skip SessionStart — dir doesn't exist yet
          const { exitCode } = await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'UserPromptSubmit',
            session_id: 'nonexistent-session',
            cwd: tmpDir,
            prompt: 'Orphan prompt',
          });

          assertEqual(exitCode, 0);

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          assertEqual(dirs.length, 0, 'Expected no session directories');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'no-ops on malformed hook input',
      fn: async () => {
        // Use the runHook helper with an invalid payload — it will still pipe
        // the string "not json" to stdin, which session-logger should handle.
        const tmpDir = await createTempProject();
        try {
          const { exitCode } = await runHook('.claude/hooks/session-logger.ts', {
            _malformed: true,
          } as Record<string, unknown>);

          // session-logger catches parse errors and exits 0
          assertEqual(exitCode, 0, 'Hook should exit 0 on malformed input');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    // --- Agent logs: race condition fix ---

    {
      description:
        'appends last_assistant_message to agent_logs when transcript is missing it (race condition)',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          // Bootstrap session
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          // Create a mock transcript that only has the user message
          // (simulates the race condition where the final assistant message
          // hasn't been flushed to disk when the Stop hook fires)
          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const meta = await readMetadata(dirs[0]);
          const transcriptPath = `/tmp/test-transcript-race-${TEST_SESSION_ID}.jsonl`;
          const { writeFile: wf } = await import('node:fs/promises');
          await wf(transcriptPath, JSON.stringify({ role: 'user', content: 'hello' }) + '\n');

          // Fire Stop hook — should detect missing assistant message and append it
          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'Stop',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              transcript_path: transcriptPath,
              last_assistant_message: 'Final agent response',
            }
          );

          // Read the agent_logs file
          const { rm } = await import('node:fs/promises');
          const agentLogFile = join(dirs[0], 'agent_logs', `global-${meta!.run_id}.jsonl`);
          assert(existsSync(agentLogFile), 'Expected agent_logs file to exist');
          const logContent = await readFile(agentLogFile, 'utf-8');
          const logLines = logContent.trim().split('\n');

          assertEqual(logLines.length, 2, 'Expected 2 entries in agent_logs (user + appended assistant)');
          const lastEntry = JSON.parse(logLines[1]);
          assertEqual(lastEntry.role, 'assistant', 'Last entry should be assistant');
          assertEqual(lastEntry.content, 'Final agent response', 'Appended content should match last_assistant_message');

          // Cleanup temp transcript
          await rm(transcriptPath, { force: true });
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description:
        'does not duplicate assistant message when transcript already has it',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const meta = await readMetadata(dirs[0]);

          // Create a transcript with BOTH user and assistant messages
          // (no race condition — transcript is complete)
          const transcriptPath = `/tmp/test-transcript-norace-${TEST_SESSION_ID}.jsonl`;
          const { writeFile: wf, rm } = await import('node:fs/promises');
          await wf(transcriptPath, [
            JSON.stringify({ role: 'user', content: 'hello' }),
            JSON.stringify({ role: 'assistant', content: 'Existing response' }),
          ].join('\n') + '\n');

          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'Stop',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              transcript_path: transcriptPath,
              last_assistant_message: 'Existing response',
            }
          );

          const agentLogFile = join(dirs[0], 'agent_logs', `global-${meta!.run_id}.jsonl`);
          const logContent = await readFile(agentLogFile, 'utf-8');
          const logLines = logContent.trim().split('\n');

          assertEqual(logLines.length, 2, 'Expected 2 entries, not 3 (no duplicate)');

          await rm(transcriptPath, { force: true });
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description:
        'appends response when transcript ends with tool_result user message',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await runHook('.claude/hooks/session-logger.ts', {
            hook_event_name: 'SessionStart',
            session_id: TEST_SESSION_ID,
            cwd: tmpDir,
          });

          const dirs = await getSessionDirs(join(tmpDir, '.claude', 'sessions'));
          const meta = await readMetadata(dirs[0]);

          // Simulate a transcript where the last entry is a tool_result (user role)
          // followed by a missing final assistant response
          const transcriptPath = `/tmp/test-transcript-toolresult-${TEST_SESSION_ID}.jsonl`;
          const { writeFile: wf, rm } = await import('node:fs/promises');
          await wf(transcriptPath, [
            JSON.stringify({ role: 'user', content: 'do something' }),
            JSON.stringify({ role: 'assistant', content: [{ type: 'tool_use', name: 'Bash', input: { command: 'ls' } }], stop_reason: 'tool_use' }),
            JSON.stringify({ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'abc', content: 'file1.txt\nfile2.txt' }] }),
          ].join('\n') + '\n');

          await runHook(
            '.claude/hooks/session-logger.ts',
            {
              hook_event_name: 'Stop',
              session_id: TEST_SESSION_ID,
              cwd: tmpDir,
              transcript_path: transcriptPath,
              last_assistant_message: 'Here are the files I found.',
            }
          );

          const agentLogFile = join(dirs[0], 'agent_logs', `global-${meta!.run_id}.jsonl`);
          const logContent = await readFile(agentLogFile, 'utf-8');
          const logLines = logContent.trim().split('\n');

          assertEqual(logLines.length, 4, 'Expected 4 entries (user + assistant_tool + user_tool_result + appended_final)');
          const lastEntry = JSON.parse(logLines[3]);
          assertEqual(lastEntry.role, 'assistant', 'Last entry should be appended assistant response');
          assertEqual(lastEntry.content, 'Here are the files I found.');

          await rm(transcriptPath, { force: true });
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },
  ],
};

export default suite;
