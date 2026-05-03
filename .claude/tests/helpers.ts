/**
 * helpers.ts
 *
 * Shared utilities for the Claude Code extension test suite.
 * Provides assertion functions, process spawning helpers, and session
 * inspection utilities used by both unit and integration tests.
 */

import { readdir, rm, readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';

// ============ Types ============

export interface TestSuite {
  name: string;
  category: 'unit' | 'integration';
  tests: TestCase[];
}

export interface TestCase {
  description: string;
  fn: () => Promise<void>;
}

export interface TestResult {
  suite: string;
  category: 'unit' | 'integration';
  description: string;
  status: 'passed' | 'failed';
  duration: number;
  error?: string;
}

// ============ Assertions ============

export class AssertionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AssertionError';
  }
}

export function assert(condition: boolean, message: string): void {
  if (!condition) throw new AssertionError(message);
}

export function assertEqual<T>(actual: T, expected: T, label?: string): void {
  if (actual !== expected) {
    throw new AssertionError(
      `${label || 'Value'}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

export function assertIncludes(
  haystack: string,
  needle: string,
  label?: string
): void {
  if (!haystack.includes(needle)) {
    throw new AssertionError(
      `${label || 'String'}: expected to include "${needle}"`
    );
  }
}

export function assertNotIncludes(
  haystack: string,
  needle: string,
  label?: string
): void {
  if (haystack.includes(needle)) {
    throw new AssertionError(
      `${label || 'String'}: expected NOT to include "${needle}"`
    );
  }
}

export function assertMatch(
  text: string,
  pattern: RegExp,
  label?: string
): void {
  if (!pattern.test(text)) {
    throw new AssertionError(
      `${label || 'String'}: expected to match ${pattern.toString()}`
    );
  }
}

export function assertDefined<T>(
  value: T | undefined | null,
  label?: string
): asserts value is T {
  if (value === undefined || value === null) {
    throw new AssertionError(
      `${label || 'Value'}: expected to be defined, got ${JSON.stringify(value)}`
    );
  }
}

// ============ Process Helpers ============

/** Base env that clears all cryplative session vars to prevent leakage. */
const CLEAN_ENV: Record<string, string> = {
  CRYPLATIVE_SESSION_ID: '',
  CRYPLATIVE_DELEGATED_SESSION: '',
  CRYPLATIVE_PRINT_MODE: '',
  CRYPLATIVE_AGENT_RUN_ID: '',
  CLAUDE_AGENT_NAME: '',
  CLAUDE_ENV_FILE: '',
};

/**
 * Run a bun script (hook or skill) with JSON input piped to stdin.
 * All cryplative env vars are cleared; override with extraEnv.
 * Uses a temp file to pipe stdin (Bun.spawn needs a file path for stdin).
 */
export async function runHook(
  scriptPath: string,
  input: Record<string, unknown>,
  extraEnv?: Record<string, string>
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const stdinContent = JSON.stringify(input);
  const stdinPath = join(tmpdir(), `hook-stdin-${randomUUID()}.json`);
  await writeFile(stdinPath, stdinContent);

  try {
    const child = Bun.spawn(['bun', scriptPath], {
      stdout: 'pipe',
      stderr: 'pipe',
      stdin: Bun.file(stdinPath),
      env: { ...Bun.env, ...CLEAN_ENV, ...extraEnv },
    });

    const stdout = await new Response(child.stdout).text();
    const stderr = await new Response(child.stderr).text();
    const exitCode = await child.exited;

    return { stdout, stderr, exitCode };
  } finally {
    // Clean up temp stdin file
    if (existsSync(stdinPath)) {
      await rm(stdinPath, { force: true });
    }
  }
}

/**
 * Run a bun script with CLI args (no stdin).
 */
export async function runScript(
  scriptPath: string,
  args: string[] = [],
  extraEnv?: Record<string, string>
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const child = Bun.spawn(['bun', scriptPath, ...args], {
    stdout: 'pipe',
    stderr: 'pipe',
    env: { ...Bun.env, ...CLEAN_ENV, ...extraEnv },
  });

  const stdout = await new Response(child.stdout).text();
  const stderr = await new Response(child.stderr).text();
  const exitCode = await child.exited;

  return { stdout, stderr, exitCode };
}

/**
 * Run the claude CLI with given arguments.
 * Times out after timeoutMs (default 120 s).
 */
export async function runClaude(
  args: string[],
  timeoutMs: number = 120_000
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const child = Bun.spawn(['claude', ...args], {
    stdout: 'pipe',
    stderr: 'pipe',
    env: { ...Bun.env, ...CLEAN_ENV },
  });

  const timer = setTimeout(() => child.kill(), timeoutMs);

  const stdout = await new Response(child.stdout).text();
  const stderr = await new Response(child.stderr).text();
  const exitCode = await child.exited;

  clearTimeout(timer);

  return { stdout, stderr, exitCode };
}

// ============ Session Helpers ============

/**
 * Create a temporary project directory with .claude/sessions/ structure.
 * Returns the temp dir path. Caller must clean up.
 */
export async function createTempProject(): Promise<string> {
  const dir = join(tmpdir(), `cryplative-test-${randomUUID()}`);
  await mkdir(join(dir, '.claude', 'sessions'), { recursive: true });
  return dir;
}

/** Recursively remove a temp project directory. */
export async function cleanupTempProject(dir: string): Promise<void> {
  if (existsSync(dir)) {
    await rm(dir, { recursive: true, force: true });
  }
}

/**
 * List session directories inside a sessions dir.
 * Filters out hidden dirs and dirs starting with underscore.
 */
export async function getSessionDirs(sessionsDir: string): Promise<string[]> {
  if (!existsSync(sessionsDir)) return [];
  const entries = await readdir(sessionsDir, { withFileTypes: true });
  return entries
    .filter(
      (e) => e.isDirectory() && !e.name.startsWith('.') && !e.name.startsWith('_')
    )
    .map((e) => join(sessionsDir, e.name))
    .sort();
}

/** Read and parse every line of _conversation.jsonl. */
export async function readConversationLog(
  sessionDir: string
): Promise<Record<string, unknown>[]> {
  const file = join(sessionDir, '_conversation.jsonl');
  if (!existsSync(file)) return [];
  const content = await readFile(file, 'utf-8');
  return content
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as Record<string, unknown>;
      } catch {
        return null;
      }
    })
    .filter((e): e is Record<string, unknown> => e !== null);
}

/** Read and parse _metadata.json. */
export async function readMetadata(
  sessionDir: string
): Promise<Record<string, unknown> | null> {
  const file = join(sessionDir, '_metadata.json');
  if (!existsSync(file)) return null;
  try {
    const content = await readFile(file, 'utf-8');
    return JSON.parse(content) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Write entries to _conversation.jsonl (for seeding test data). */
export async function seedConversationLog(
  sessionDir: string,
  entries: Record<string, unknown>[]
): Promise<void> {
  const file = join(sessionDir, '_conversation.jsonl');
  await writeFile(file, entries.map((e) => JSON.stringify(e)).join('\n') + '\n');
}

/** Write _metadata.json (for seeding test data). */
export async function seedMetadata(
  sessionDir: string,
  metadata: Record<string, unknown>
): Promise<void> {
  const file = join(sessionDir, '_metadata.json');
  await writeFile(file, JSON.stringify(metadata, null, 2) + '\n');
}

/**
 * Run an integration test that calls claude CLI.
 * Snapshots sessions before and after, returning new session dirs.
 */
export async function runClaudeIntegration(
  sessionsDir: string,
  claudeArgs: string[],
  timeoutMs: number = 120_000
): Promise<{
  stdout: string;
  stderr: string;
  exitCode: number;
  newSessionDirs: string[];
}> {
  const before = new Set(await getSessionDirs(sessionsDir));

  const { stdout, stderr, exitCode } = await runClaude(claudeArgs, timeoutMs);

  const after = await getSessionDirs(sessionsDir);
  const newDirs = after.filter((d) => !before.has(d));

  return { stdout, stderr, exitCode, newSessionDirs: newDirs };
}

/** Remove session directories created during a test. */
export async function cleanupSessions(dirs: string[]): Promise<void> {
  for (const dir of dirs) {
    if (existsSync(dir)) {
      await rm(dir, { recursive: true, force: true });
    }
  }
}
