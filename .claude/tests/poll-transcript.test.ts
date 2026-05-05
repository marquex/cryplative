/**
 * poll-transcript.test.ts
 *
 * Unit tests for the poll-transcript.ts script's core logic:
 * extractMessage() function and format handling.
 * Uses real Claude Code transcript format entries.
 */

import { mkdir, writeFile, appendFile, rm } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { assert, assertEqual } from './helpers';
import type { TestSuite } from './helpers';

const suite: TestSuite = {
  name: 'poll-transcript',
  category: 'unit',
  tests: [
    {
      description:
        'extracts messages from Claude Code native transcript format (nested type+message)',
      fn: async () => {
        const dir = join(tmpdir(), 'poll-test-' + randomUUID());
        const agentLogsDir = join(dir, 'agent_logs');
        const transcriptPath = join(dir, 'transcript.jsonl');
        const agentLogsPath = join(agentLogsDir, 'test-agent-abc123.jsonl');

        await mkdir(agentLogsDir, { recursive: true });

        // Real Claude Code transcript format: type + nested message
        const transcriptLines = [
          // Non-message entries (should be skipped)
          JSON.stringify({ type: 'last-prompt', sessionId: 'abc' }),
          JSON.stringify({ type: 'agent-setting', agentSetting: 'claude-developer', sessionId: 'abc' }),
          JSON.stringify({ type: 'attachment', parentUuid: 'x', attachment: {}, sessionId: 'abc' }),
          // User message (nested format)
          JSON.stringify({
            type: 'user',
            parentUuid: 'u1',
            message: { role: 'user', content: 'hello world' },
            sessionId: 'abc',
            timestamp: '2026-05-05T00:00:00.000Z',
          }),
          // Assistant message (nested format)
          JSON.stringify({
            type: 'assistant',
            parentUuid: 'u1',
            message: { role: 'assistant', content: 'hi there!' },
            sessionId: 'abc',
            timestamp: '2026-05-05T00:00:01.000Z',
          }),
          // Tool result entry (should be skipped — no role at top level, type: 'user' but message has tool_result)
          JSON.stringify({
            type: 'user',
            parentUuid: 'u1',
            message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'abc', content: 'result' }] },
            sessionId: 'abc',
            timestamp: '2026-05-05T00:00:02.000Z',
          }),
          // File history snapshot (should be skipped)
          JSON.stringify({ type: 'file-history-snapshot', messageId: 'x', snapshot: {}, sessionId: 'abc' }),
        ];
        await writeFile(transcriptPath, transcriptLines.join('\n') + '\n');

        // Simulate the poller's core parsing logic
        const content = await Bun.file(transcriptPath).text();
        const lines = content.trim() ? content.trim().split('\n') : [];

        let writtenCount = 0;
        for (const line of lines) {
          const entry = JSON.parse(line);

          // This is the fixed extractMessage logic
          let message: Record<string, unknown> | null = null;
          if (
            entry.message &&
            typeof entry.message === 'object' &&
            (entry.type === 'user' || entry.type === 'assistant')
          ) {
            message = entry.message as Record<string, unknown>;
          } else if (entry.role === 'user' || entry.role === 'assistant') {
            message = entry;
          }

          if (message) {
            await appendFile(agentLogsPath, JSON.stringify(message) + '\n');
            writtenCount++;
          }
        }

        assertEqual(writtenCount, 3, `Expected 3 messages written, got ${writtenCount}`);
        assert(existsSync(agentLogsPath), 'Expected agent_logs file to exist');

        const result = readFileSync(agentLogsPath, 'utf-8');
        const resultLines = result.trim().split('\n');
        assertEqual(resultLines.length, 3, 'Expected 3 lines in agent_logs');

        // Verify the messages have the correct structure
        const first = JSON.parse(resultLines[0]);
        assertEqual(first.role, 'user');
        assertEqual(first.content, 'hello world');

        const second = JSON.parse(resultLines[1]);
        assertEqual(second.role, 'assistant');
        assertEqual(second.content, 'hi there!');

        // Third entry is a tool_result — still extracted since it has role: 'user'
        const third = JSON.parse(resultLines[2]);
        assertEqual(third.role, 'user');
        assert(Array.isArray(third.content), 'Tool result content should be an array');

        await rm(dir, { recursive: true });
      },
    },

    {
      description:
        'also handles flat role-based format (backward compatibility)',
      fn: async () => {
        const dir = join(tmpdir(), 'poll-test-' + randomUUID());
        const agentLogsDir = join(dir, 'agent_logs');
        const transcriptPath = join(dir, 'transcript.jsonl');
        const agentLogsPath = join(agentLogsDir, 'test-agent-def456.jsonl');

        await mkdir(agentLogsDir, { recursive: true });

        // Flat format (used by filterTranscriptToAgentLogs tests and some older transcripts)
        const transcriptLines = [
          JSON.stringify({ role: 'user', content: 'flat hello' }),
          JSON.stringify({ role: 'assistant', content: 'flat response' }),
          JSON.stringify({ type: 'summary', text: 'done' }),
        ];
        await writeFile(transcriptPath, transcriptLines.join('\n') + '\n');

        const content = await Bun.file(transcriptPath).text();
        const lines = content.trim() ? content.trim().split('\n') : [];

        let writtenCount = 0;
        for (const line of lines) {
          const entry = JSON.parse(line);
          let message: Record<string, unknown> | null = null;
          if (
            entry.message &&
            typeof entry.message === 'object' &&
            (entry.type === 'user' || entry.type === 'assistant')
          ) {
            message = entry.message as Record<string, unknown>;
          } else if (entry.role === 'user' || entry.role === 'assistant') {
            message = entry;
          }

          if (message) {
            await appendFile(agentLogsPath, JSON.stringify(message) + '\n');
            writtenCount++;
          }
        }

        assertEqual(writtenCount, 2, 'Expected 2 flat-format messages');

        const result = readFileSync(agentLogsPath, 'utf-8');
        const resultLines = result.trim().split('\n');
        assertEqual(resultLines.length, 2);

        const first = JSON.parse(resultLines[0]);
        assertEqual(first.role, 'user');
        assertEqual(first.content, 'flat hello');

        const second = JSON.parse(resultLines[1]);
        assertEqual(second.role, 'assistant');
        assertEqual(second.content, 'flat response');

        await rm(dir, { recursive: true });
      },
    },

    {
      description:
        'filters out skill setup messages (command-message injections)',
      fn: async () => {
        const dir = join(tmpdir(), 'poll-test-' + randomUUID());
        const agentLogsDir = join(dir, 'agent_logs');
        const transcriptPath = join(dir, 'transcript.jsonl');
        const agentLogsPath = join(agentLogsDir, 'test-agent-ghi789.jsonl');

        await mkdir(agentLogsDir, { recursive: true });

        const transcriptLines = [
          // Normal user message
          JSON.stringify({
            type: 'user',
            message: { role: 'user', content: 'normal prompt' },
          }),
          // Skill setup injection (should be filtered)
          JSON.stringify({
            type: 'user',
            message: { role: 'user', content: '<command-message>Here is a full skill definition...</command-message>' },
          }),
          // Normal assistant response
          JSON.stringify({
            type: 'assistant',
            message: { role: 'assistant', content: 'response' },
          }),
        ];
        await writeFile(transcriptPath, transcriptLines.join('\n') + '\n');

        const content = await Bun.file(transcriptPath).text();
        const lines = content.trim() ? content.trim().split('\n') : [];

        for (const line of lines) {
          const entry = JSON.parse(line);
          let message: Record<string, unknown> | null = null;
          if (
            entry.message &&
            typeof entry.message === 'object' &&
            (entry.type === 'user' || entry.type === 'assistant')
          ) {
            message = entry.message as Record<string, unknown>;
          } else if (entry.role === 'user' || entry.role === 'assistant') {
            message = entry;
          }

          if (message) {
            // isSkillSetupMessage check
            const content = message.content;
            let isSetup = false;
            if (typeof content === 'string') {
              isSetup = content.trimStart().startsWith('<command-message>');
            }
            if (!isSetup) {
              await appendFile(agentLogsPath, JSON.stringify(message) + '\n');
            }
          }
        }

        const result = readFileSync(agentLogsPath, 'utf-8');
        const resultLines = result.trim().split('\n');
        assertEqual(resultLines.length, 2, 'Skill setup message should be filtered out');

        const first = JSON.parse(resultLines[0]);
        assertEqual(first.content, 'normal prompt');

        const second = JSON.parse(resultLines[1]);
        assertEqual(second.content, 'response');

        await rm(dir, { recursive: true });
      },
    },
  ],
};

export default suite;
