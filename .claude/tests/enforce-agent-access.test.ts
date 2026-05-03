/**
 * enforce-agent-access.test.ts
 *
 * Unit tests for the .claude/scripts/enforce-agent-access.ts hook.
 * Tests access control decisions for various agents, tools, and paths.
 */

import {
  runHook,
  assertEqual,
  assertIncludes,
} from './helpers';
import type { TestSuite } from './helpers';

const PROJECT_DIR = process.cwd();

/** Parse the hook's JSON decision from stdout. */
function parseDecision(stdout: string): {
  decision: string;
  reason: string;
} {
  const result = JSON.parse(stdout);
  const output = result.hookSpecificOutput;
  return {
    decision: output.permissionDecision,
    reason: output.permissionDecisionReason,
  };
}

const suite: TestSuite = {
  name: 'enforce-agent-access',
  category: 'unit',
  tests: [
    // --- Main agent (no agent_type) ---

    {
      description: 'allows main agent (no agent_type)',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          tool_name: 'Read',
          tool_input: { file_path: 'any-file.txt' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'allow');
        assertIncludes(reason, 'main agent');
      },
    },

    // --- Unknown / missing agent ---

    {
      description: 'denies request for unknown agent',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'nonexistent-agent',
          tool_name: 'Read',
          tool_input: { file_path: 'test.txt' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'deny');
        assertIncludes(reason, 'cannot locate agent file');
      },
    },

    // --- Secondary agent ---

    {
      description: 'allows secondary to read .claude/sessions/**',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'Read',
          tool_input: { file_path: '.claude/sessions/abc123/_conversation.jsonl' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    {
      description: 'denies secondary to read files outside its domain',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'Read',
          tool_input: { file_path: 'package.json' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'deny');
      },
    },

    {
      description: 'denies secondary write to .claude/sessions/** (read-only)',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'Write',
          tool_input: { file_path: '.claude/sessions/test/file.txt' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'deny');
        assertIncludes(reason, "lacks 'write' permission");
      },
    },

    {
      description: 'allows secondary to read nested session files',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'Read',
          tool_input: {
            file_path: '.claude/sessions/abc-123/agent_logs/secondary-x1y2z3.jsonl',
          },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    // --- Primary agent ---

    {
      description: 'allows primary to write to .claude/sessions/**',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'primary',
          tool_name: 'Write',
          tool_input: { file_path: '.claude/sessions/test/file.txt' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    {
      description: 'denies primary delete on .claude/sessions/** (no delete permission)',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'primary',
          tool_name: 'Bash',
          tool_input: { command: 'rm -rf .claude/sessions/test-dir' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'deny');
        assertIncludes(reason, "lacks 'delete' permission");
      },
    },

    // --- Claude-developer agent ---

    {
      description: 'allows claude-developer to read inside .claude/',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Read',
          tool_input: { file_path: '.claude/agents/primary.md' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    {
      description: 'allows claude-developer to write inside .claude/',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Edit',
          tool_input: { file_path: '.claude/agents/test.md' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    {
      description: 'denies claude-developer to read files outside .claude/',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Read',
          tool_input: { file_path: 'src/index.ts' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'deny');
        assertIncludes(reason, 'no access rule');
      },
    },

    // --- Tool classification ---

    {
      description: 'skips (allows) unknown tools like WebFetch',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'WebFetch',
          tool_input: { url: 'https://example.com' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'allow');
        assertIncludes(reason, 'not governed');
      },
    },

    {
      description: 'skips (allows) read-only bash commands',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'secondary',
          tool_name: 'Bash',
          tool_input: { command: 'ls .claude/sessions' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    // --- Path traversal ---

    {
      description: 'denies path traversal outside project',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Read',
          tool_input: { file_path: '../../etc/passwd' },
          cwd: PROJECT_DIR,
        });
        const { decision, reason } = parseDecision(stdout);
        assertEqual(decision, 'deny');
        assertIncludes(reason, 'outside project');
      },
    },

    {
      description: 'denies absolute path outside project',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Read',
          tool_input: { file_path: '/etc/passwd' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'deny');
      },
    },

    // --- Grep tool ---

    {
      description: 'allows claude-developer to Grep inside .claude/',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Grep',
          tool_input: { pattern: 'test', path: '.claude/agents/' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'allow');
      },
    },

    {
      description: 'denies claude-developer to Grep outside .claude/',
      fn: async () => {
        const { stdout } = await runHook('.claude/scripts/enforce-agent-access.ts', {
          agent_type: 'claude-developer',
          tool_name: 'Grep',
          tool_input: { pattern: 'test', path: 'src/' },
          cwd: PROJECT_DIR,
        });
        const { decision } = parseDecision(stdout);
        assertEqual(decision, 'deny');
      },
    },
  ],
};

export default suite;
