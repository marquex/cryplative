#!/usr/bin/env bun
/**
 * runner.ts
 *
 * Test runner for Claude Code extensions.
 * Discovers and executes unit + integration test suites, reports results.
 *
 * Usage:
 *   bun .claude/tests/runner.ts                   # run all tests
 *   bun .claude/tests/runner.ts --unit            # unit tests only
 *   bun .claude/tests/runner.ts --integration     # integration tests only
 *   bun .claude/tests/runner.ts --filter <name>   # filter suites by name
 *   bun .claude/tests/runner.ts --no-cleanup      # keep integration session dirs
 *   bun .claude/tests/runner.ts --timeout <ms>    # integration test timeout (default 120000)
 *   bun .claude/tests/runner.ts --list            # list tests without running
 *
 * To add a new test suite:
 *   1. Create .claude/tests/<name>.test.ts
 *   2. Export default { name: string, category: 'unit'|'integration', tests: TestCase[] }
 *   3. Import and register the suite in the ALL_SUITES array below.
 */

import type { TestSuite, TestResult } from './helpers';

// ANSI helpers
const G = '\x1b[32m'; // green
const R = '\x1b[31m'; // red
const Y = '\x1b[33m'; // yellow
const DIM = '\x1b[90m';
const BOLD = '\x1b[1m';
const RESET = '\x1b[0m';

// ============ Suite Registry ============
// Import all test suites here. Each file exports a default TestSuite.

import enforceAccessSuite from './enforce-agent-access.test';
import sessionLoggerSuite from './session-logger.test';
import yamlValidatorSuite from './yaml-validator.test';
import sessionLoggingSuite from './session-logging.test';
import delegationSuite from './delegation.test';
import accessControlSuite from './access-control.test';

const ALL_SUITES: TestSuite[] = [
  enforceAccessSuite,
  sessionLoggerSuite,
  yamlValidatorSuite,
  sessionLoggingSuite,
  delegationSuite,
  accessControlSuite,
];

// ============ CLI Args ============

function parseArgs(args: string[]): {
  mode: 'unit' | 'integration' | 'all';
  filter: string | null;
  noCleanup: boolean;
  timeout: number;
  list: boolean;
} {
  let mode: 'unit' | 'integration' | 'all' = 'all';
  let filter: string | null = null;
  let noCleanup = false;
  let timeout = 120_000;
  let list = false;

  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === '--unit') mode = 'unit';
    else if (a === '--integration') mode = 'integration';
    else if (a === '--all') mode = 'all';
    else if (a === '--filter' && args[i + 1]) filter = args[++i]!;
    else if (a === '--no-cleanup') noCleanup = true;
    else if (a === '--timeout' && args[i + 1]) timeout = parseInt(args[++i]!, 10);
    else if (a === '--list') list = true;
    else {
      console.error(`Unknown argument: ${a}`);
      process.exit(1);
    }
  }

  return { mode, filter, noCleanup, timeout, list };
}

// ============ Test Execution ============

async function runSuite(suite: TestSuite): Promise<TestResult[]> {
  const results: TestResult[] = [];

  for (const test of suite.tests) {
    const start = Date.now();
    try {
      await test.fn();
      const duration = Date.now() - start;
      results.push({
        suite: suite.name,
        category: suite.category,
        description: test.description,
        status: 'passed',
        duration,
      });
      console.log(
        `  ${G}✓${RESET} ${test.description} ${DIM}(${duration}ms)${RESET}`
      );
    } catch (err) {
      const duration = Date.now() - start;
      const message = err instanceof Error ? err.message : String(err);
      results.push({
        suite: suite.name,
        category: suite.category,
        description: test.description,
        status: 'failed',
        duration,
        error: message,
      });
      console.log(
        `  ${R}✗${RESET} ${test.description} ${DIM}(${duration}ms)${RESET}`
      );
      // Print first 3 lines of error, indented
      for (const line of message.split('\n').slice(0, 3)) {
        console.log(`    ${DIM}${line}${RESET}`);
      }
    }
  }

  return results;
}

// ============ Main ============

async function main() {
  const { mode, filter, list } = parseArgs(
    process.argv.slice(2)
  );

  // Filter suites by mode
  let suites = ALL_SUITES;
  if (mode === 'unit') {
    suites = suites.filter((s) => s.category === 'unit');
  } else if (mode === 'integration') {
    suites = suites.filter((s) => s.category === 'integration');
  }

  // Filter by name pattern
  if (filter) {
    const lower = filter.toLowerCase();
    suites = suites.filter((s) => s.name.toLowerCase().includes(lower));
  }

  // --list: just print and exit
  if (list) {
    console.log('Available test suites:\n');
    for (const s of suites) {
      const cat = s.category === 'unit' ? 'UNIT' : 'INTEGRATION';
      console.log(`  [${cat}] ${s.name} (${s.tests.length} tests)`);
      for (const t of s.tests) {
        console.log(`    - ${t.description}`);
      }
      console.log();
    }
    return;
  }

  // Header
  console.log(`\n${BOLD}Claude Code Extension Tests${RESET}`);
  console.log('='.repeat(40));

  if (mode === 'unit') console.log(`Mode: ${Y}unit only${RESET}`);
  else if (mode === 'integration')
    console.log(`Mode: ${Y}integration only${RESET} (uses Claude API)`);
  else console.log(`Mode: ${Y}all${RESET}`);

  const allResults: TestResult[] = [];

  // Run unit tests
  const unitSuites = suites.filter((s) => s.category === 'unit');
  if (unitSuites.length > 0) {
    console.log(`\n${BOLD}[UNIT]${RESET}`);
    for (const suite of unitSuites) {
      console.log(`\n${suite.name}`);
      const results = await runSuite(suite);
      allResults.push(...results);
    }
  }

  // Run integration tests
  const intSuites = suites.filter((s) => s.category === 'integration');
  if (intSuites.length > 0) {
    console.log(`\n${BOLD}[INTEGRATION]${RESET} ${DIM}(uses Claude API, may incur costs)${RESET}`);
    for (const suite of intSuites) {
      console.log(`\n${suite.name}`);
      const results = await runSuite(suite);
      allResults.push(...results);
    }
  }

  // ============ Summary ============

  const passed = allResults.filter((r) => r.status === 'passed');
  const failed = allResults.filter((r) => r.status === 'failed');
  const totalTime = allResults.reduce((sum, r) => sum + r.duration, 0);

  console.log(`\n${'='.repeat(40)}`);

  if (failed.length === 0) {
    console.log(
      `${G}✓ All ${passed.length} tests passed${RESET} ${DIM}(${formatDuration(totalTime)})${RESET}`
    );
  } else {
    console.log(
      `${R}✗ ${passed.length}/${allResults.length} passed, ${failed.length} failed${RESET} ${DIM}(${formatDuration(totalTime)})${RESET}`
    );
    console.log(`\nFailed tests:`);
    for (const f of failed) {
      console.log(`  ${R}✗${RESET} [${f.suite}] ${f.description}`);
      for (const line of (f.error || '').split('\n').slice(0, 2)) {
        console.log(`    ${DIM}${line}${RESET}`);
      }
    }
  }

  process.exit(failed.length > 0 ? 1 : 0);
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

main().catch((err) => {
  console.error(`${R}Runner error: ${err}${RESET}`);
  process.exit(2);
});
