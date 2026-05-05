/**
 * End-to-end test for the fixed poll-transcript.ts script.
 * Creates a mock Claude Code transcript in native format, spawns
 * the poller as a real background process, and verifies that it
 * correctly writes to agent_logs.
 *
 * Note: The test does NOT verify process exit (timing-sensitive with
 * detached processes). The unit tests in debug-poller.test.ts cover
 * the extractMessage logic. This test validates the full script works
 * end-to-end against a real transcript file.
 */
import { mkdir, writeFile, rm, appendFile, writeFile as wf } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { assert, assertEqual } from './helpers';
import type { TestSuite } from './helpers';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const suite: TestSuite = {
  name: 'poll-transcript-e2e',
  category: 'unit',
  tests: [
    {
      description:
        'poll-transcript.ts correctly streams messages from Claude Code native transcript format',
      fn: async () => {
        const dir = join(tmpdir(), 'poll-e2e-' + randomUUID());
        const agentLogsDir = join(dir, 'agent_logs');
        const transcriptPath = join(dir, 'transcript.jsonl');
        const agentLogsPath = join(agentLogsDir, 'e2e-agent-e2e123.jsonl');
        const sentinelPath = join(dir, '.poll-stop');

        await mkdir(agentLogsDir, { recursive: true });

        // Write initial transcript entries in Claude Code native format
        await writeFile(
          transcriptPath,
          [
            JSON.stringify({ type: 'last-prompt', sessionId: 'abc' }),
            JSON.stringify({ type: 'agent-setting', agentSetting: 'test', sessionId: 'abc' }),
            JSON.stringify({
              type: 'user',
              message: { role: 'user', content: 'first prompt' },
              sessionId: 'abc',
              timestamp: '2026-05-05T00:00:00.000Z',
            }),
          ].join('\n') + '\n'
        );

        // Spawn the poller as a background process (non-detached for testability)
        const child = Bun.spawn(
          [
            'bun',
            join(process.cwd(), '.claude', 'scripts', 'poll-transcript.ts'),
            dir,
            'e2e-agent',
            'e2e123',
            transcriptPath,
          ],
          { stdout: 'pipe', stderr: 'pipe', stdin: 'ignore' }
        );

        try {
          // Wait for the poller to process the initial entries (2 seconds poll interval + buffer)
          await sleep(3500);

          // Verify first entries were written
          assert(existsSync(agentLogsPath), 'Expected agent_logs file after first poll');

          let content = readFileSync(agentLogsPath, 'utf-8');
          let lines = content.trim().split('\n');
          assertEqual(lines.length, 1, `Expected 1 entry after initial write, got ${lines.length}`);
          assertEqual(JSON.parse(lines[0]).content, 'first prompt');

          // Append a new assistant message to the transcript (simulating ongoing conversation)
          await appendFile(
            transcriptPath,
            JSON.stringify({
              type: 'assistant',
              message: { role: 'assistant', content: 'first response' },
              sessionId: 'abc',
              timestamp: '2026-05-05T00:00:01.000Z',
            }) + '\n'
          );

          // Wait for the poller to pick up the new entry
          await sleep(3500);

          content = readFileSync(agentLogsPath, 'utf-8');
          lines = content.trim().split('\n');
          assertEqual(lines.length, 2, `Expected 2 entries after second write, got ${lines.length}`);
          assertEqual(JSON.parse(lines[1]).role, 'assistant');
          assertEqual(JSON.parse(lines[1]).content, 'first response');

          // Signal the poller to stop via sentinel
          await wf(sentinelPath, '');

          // Wait for drain mode (3 seconds) + cleanup
          await sleep(5000);

          // Verify sentinel was cleaned up by the poller
          assert(!existsSync(sentinelPath), 'Expected sentinel to be cleaned up');
        } finally {
          // Ensure child is killed even if test fails
          try { child.kill(); } catch { /* already exited */ }
          await rm(dir, { recursive: true });
        }
      },
    },

    {
      description:
        'poll-transcript.ts handles non-message entries (attachments, file-history-snapshots) gracefully',
      fn: async () => {
        const dir = join(tmpdir(), 'poll-e2e-' + randomUUID());
        const agentLogsDir = join(dir, 'agent_logs');
        const transcriptPath = join(dir, 'transcript.jsonl');
        const agentLogsPath = join(agentLogsDir, 'e2e-agent-e2e456.jsonl');
        const sentinelPath = join(dir, '.poll-stop');

        await mkdir(agentLogsDir, { recursive: true });

        // Write a transcript with many non-message entries (like real Claude Code transcripts)
        await writeFile(
          transcriptPath,
          [
            JSON.stringify({ type: 'last-prompt', leafUuid: 'x', sessionId: 'abc' }),
            JSON.stringify({ type: 'agent-setting', agentSetting: 'test', sessionId: 'abc' }),
            JSON.stringify({ type: 'permission-mode', permissionMode: 'default', sessionId: 'abc' }),
            JSON.stringify({ type: 'attachment', parentUuid: 'u1', attachment: {}, sessionId: 'abc' }),
            JSON.stringify({ type: 'file-history-snapshot', messageId: 'x', snapshot: {}, sessionId: 'abc' }),
            // The only actual message
            JSON.stringify({
              type: 'user',
              message: { role: 'user', content: 'the only real message' },
              sessionId: 'abc',
              timestamp: '2026-05-05T00:00:00.000Z',
            }),
            // More noise
            JSON.stringify({ type: 'attachment', parentUuid: 'u2', attachment: {}, sessionId: 'abc' }),
          ].join('\n') + '\n'
        );

        const child = Bun.spawn(
          [
            'bun',
            join(process.cwd(), '.claude', 'scripts', 'poll-transcript.ts'),
            dir,
            'e2e-agent',
            'e2e456',
            transcriptPath,
          ],
          { stdout: 'pipe', stderr: 'pipe', stdin: 'ignore' }
        );

        try {
          await sleep(3500);

          assert(existsSync(agentLogsPath), 'Expected agent_logs file');
          const content = readFileSync(agentLogsPath, 'utf-8');
          const lines = content.trim().split('\n');
          assertEqual(lines.length, 1, `Expected exactly 1 message, got ${lines.length}`);
          assertEqual(JSON.parse(lines[0]).content, 'the only real message');

          await wf(sentinelPath, '');
          await sleep(5000);
          assert(!existsSync(sentinelPath), 'Expected sentinel cleanup');
        } finally {
          try { child.kill(); } catch { /* already exited */ }
          await rm(dir, { recursive: true });
        }
      },
    },
  ],
};

export default suite;
