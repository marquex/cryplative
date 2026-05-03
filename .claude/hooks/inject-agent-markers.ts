#!/usr/bin/env bun
/**
 * inject-agent-markers.ts
 *
 * PostToolUse hook that replaces markers in agent files with actual content
 * derived from the YAML frontmatter:
 *
 *   <!-- ACCESS_RULES -->  → formatted list of access rules
 *   <!-- SUBORDINATES -->  → formatted list of subordinate agents with descriptions
 *
 * This hook fires after any Write, Edit, or MultiEdit tool that targets a file
 * in `.claude/agents/`. It reads the file, replaces the markers, and writes
 * the modified content back. This ensures agent files always have up-to-date
 * access rules and subordinates lists without manual maintenance.
 *
 * The replacement is idempotent — if a marker is already replaced, the hook
 * does nothing (no marker found, no replacement).
 *
 * Always exits 0 (non-blocking).
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

// ---------- types ----------

interface HookInput {
  hook_event_name: string;
  tool_name: string;
  tool_input?: Record<string, unknown>;
}

interface AccessRule {
  path: string;
  permissions: string[];
}

interface AgentFrontmatter {
  access: AccessRule[];
  subordinates: string[];
  [key: string]: unknown;
}

// ---------- minimal YAML frontmatter parser ----------

function stripQuotes(s: string): string {
  if (!s) return s;
  if ((s.startsWith('"') && s.endsWith('"')) ||
      (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}

const VALID_VERBS: ReadonlySet<string> = new Set(['read', 'write', 'delete']);

function parseFrontmatter(md: string): AgentFrontmatter | null {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return null;
  const body = m[1]!;
  const lines = body.split(/\r?\n/);

  const out: AgentFrontmatter = { access: [], subordinates: [] };
  let i = 0;

  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim() || line.trim().startsWith('#')) { i++; continue; }

    // Parse access block
    if (/^access\s*:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const l = lines[i]!;
        if (l.length && !/^\s/.test(l)) break;
        if (!l.trim()) { i++; continue; }

        const pathMatch = l.match(/^\s*-\s*path\s*:\s*(.+?)\s*$/);
        if (!pathMatch) { i++; continue; }
        const rule: AccessRule = { path: stripQuotes(pathMatch[1]!), permissions: [] };
        i++;

        while (i < lines.length) {
          const sub = lines[i]!;
          if (!sub.trim()) { i++; continue; }
          if (/^\s*-\s/.test(sub) || !/^\s{2,}/.test(sub)) break;

          const permMatch = sub.match(/^\s*permissions\s*:\s*\[(.*)\]\s*$/);
          if (permMatch) {
            rule.permissions = permMatch[1]!
              .split(',')
              .map((s) => stripQuotes(s.trim()).toLowerCase())
              .filter((v) => VALID_VERBS.has(v));
          }
          i++;
        }
        out.access.push(rule);
      }
      continue;
    }

    // Parse subordinates block
    if (/^subordinates\s*:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const l = lines[i]!;
        if (l.length && !/^\s/.test(l)) break;
        if (!l.trim()) { i++; continue; }
        const itemMatch = l.match(/^\s*-\s*(.+?)\s*$/);
        if (itemMatch) out.subordinates.push(stripQuotes(itemMatch[1]!));
        i++;
      }
      continue;
    }

    // Parse top-level scalars (with inline list support for subordinates)
    const kv = line.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/);
    if (kv) {
      const key = kv[1]!;
      const rawVal = stripQuotes(kv[2]!.trim());
      if (key === 'subordinates' && rawVal.startsWith('[') && rawVal.endsWith(']')) {
        out.subordinates = rawVal
          .slice(1, -1)
          .split(',')
          .map((s) => stripQuotes(s.trim()))
          .filter(Boolean);
      } else {
        out[key] = rawVal;
      }
    }
    i++;
  }
  return out;
}

// ---------- marker replacement ----------

/**
 * Format the access rules as a bullet list string.
 * Example output:
 *   - `.claude/expertise/primary/**` — read, write, delete
 *   - `src/**` — read
 */
function formatAccessRules(rules: AccessRule[]): string {
  if (rules.length === 0) return '(none)';
  return rules
    .map((rule) => `- \`${rule.path}\` — ${rule.permissions.join(', ')}`)
    .join('\n');
}

/**
 * Format the subordinates list with descriptions.
 * Reads each subordinate's agent file to get its description.
 * Example output:
 *   - `secondary` — Secondary test agent that receives delegated tasks.
 */
function formatSubordinates(subordinates: string[], cwd: string): string {
  if (subordinates.length === 0) return '(none)';

  return subordinates
    .map((name) => {
      let desc = 'description not available';
      const agentFile = join(cwd, '.claude', 'agents', `${name}.md`);
      try {
        const content = readFileSync(agentFile, 'utf-8');
        const fm = parseFrontmatter(content);
        if (fm && typeof fm.description === 'string') {
          desc = fm.description;
        }
      } catch {
        // Agent file not found — use default description
      }
      return `- \`${name}\` — ${desc}`;
    })
    .join('\n');
}

/**
 * Replace markers in agent file content with formatted values from frontmatter.
 * Returns the modified content, or null if no markers were found.
 */
function replaceMarkers(content: string, cwd: string): string | null {
  let modified = false;

  if (content.includes('<!-- ACCESS_RULES -->') || content.includes('<!-- ACCESS_RULES -->')) {
    const fm = parseFrontmatter(content);
    if (fm) {
      const formatted = formatAccessRules(fm.access);
      content = content.replace(/<!--\s*ACCESS_RULES\s*-->/g, formatted);
      modified = true;
    }
  }

  if (content.includes('<!-- SUBORDINATES -->')) {
    const fm = parseFrontmatter(content);
    if (fm) {
      const formatted = formatSubordinates(fm.subordinates, cwd);
      content = content.replace(/<!--\s*SUBORDINATES\s*-->/g, formatted);
      modified = true;
    }
  }

  return modified ? content : null;
}

// ---------- main ----------

async function main() {
  const raw = await Bun.stdin.text();
  let input: HookInput;
  try {
    input = JSON.parse(raw) as HookInput;
  } catch {
    process.exit(0);
  }

  // Only process Write, Edit, MultiEdit tools
  if (input.tool_name !== 'Write' && input.tool_name !== 'Edit' && input.tool_name !== 'MultiEdit') {
    process.exit(0);
  }

  const toolInput = input.tool_input ?? {};
  const filePath = (toolInput.file_path as string | undefined) ?? '';

  // Only process agent files
  if (!filePath.endsWith('.md') || !filePath.includes('.claude/agents/')) {
    process.exit(0);
  }

  // Read the (just-written) file
  try {
    const content = readFileSync(filePath, 'utf-8');
    const cwd = process.cwd();
    const replaced = replaceMarkers(content, cwd);
    if (replaced) {
      writeFileSync(filePath, replaced, 'utf-8');
    }
  } catch {
    // File may not exist yet or be unreadable — non-critical
  }

  process.exit(0);
}

main();
