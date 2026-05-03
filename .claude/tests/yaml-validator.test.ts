/**
 * yaml-validator.test.ts
 *
 * Unit tests for the .claude/skills/agent-expertise/yaml-validator.ts script.
 * Tests YAML validation on valid files, invalid files, and edge cases.
 */

import { runScript, assertEqual, assertIncludes, createTempProject, cleanupTempProject } from './helpers';
import type { TestSuite } from './helpers';
import { writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const suite: TestSuite = {
  name: 'yaml-validator',
  category: 'unit',
  tests: [
    {
      description: 'validates a single valid YAML file',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await writeFile(
            join(tmpDir, 'valid.yaml'),
            'key: value\nnested:\n  sub: 123\n'
          );

          const { stdout, exitCode } = await runScript(
            '.claude/skills/agent-expertise/yaml-validator.ts',
            [tmpDir]
          );

          assertEqual(exitCode, 0);
          assertIncludes(stdout, '1/1 files valid');
          assertIncludes(stdout, 'All YAML files are valid');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'rejects an invalid YAML file',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await writeFile(
            join(tmpDir, 'broken.yaml'),
            'key: [unclosed bracket\n'
          );

          const { stdout, stderr, exitCode } = await runScript(
            '.claude/skills/agent-expertise/yaml-validator.ts',
            [tmpDir]
          );

          assertEqual(exitCode, 1);
          assertIncludes(stdout, '0/1 files valid');
          assertIncludes(stderr, 'broken.yaml');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'handles mixed valid and invalid YAML files',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          await writeFile(join(tmpDir, 'good.yaml'), 'a: 1\n');
          await writeFile(join(tmpDir, 'bad.yaml'), 'unclosed: [\n');
          await writeFile(join(tmpDir, 'also-good.yaml'), 'b: 2\n');

          const { stdout, exitCode } = await runScript(
            '.claude/skills/agent-expertise/yaml-validator.ts',
            [tmpDir]
          );

          assertEqual(exitCode, 1);
          assertIncludes(stdout, '2/3 files valid');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'handles empty directory gracefully',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          const { stdout, exitCode } = await runScript(
            '.claude/skills/agent-expertise/yaml-validator.ts',
            [tmpDir]
          );

          assertEqual(exitCode, 0);
          assertIncludes(stdout, 'No YAML files found');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },

    {
      description: 'exits with error for nonexistent directory',
      fn: async () => {
        const { stderr, exitCode } = await runScript(
          '.claude/skills/agent-expertise/yaml-validator.ts',
          ['/tmp/nonexistent-dir-xyz']
        );

        assertEqual(exitCode, 1);
        assertIncludes(stderr, 'does not exist');
      },
    },

    {
      description: 'validates YAML files in nested subdirectories',
      fn: async () => {
        const tmpDir = await createTempProject();
        try {
          const nestedDir = join(tmpDir, 'deep', 'nested');
          await mkdir(nestedDir, { recursive: true });

          await writeFile(join(nestedDir, 'deep.yaml'), 'deep: true\n');

          const { stdout, exitCode } = await runScript(
            '.claude/skills/agent-expertise/yaml-validator.ts',
            [tmpDir]
          );

          assertEqual(exitCode, 0);
          assertIncludes(stdout, '1/1 files valid');
        } finally {
          await cleanupTempProject(tmpDir);
        }
      },
    },
  ],
};

export default suite;
