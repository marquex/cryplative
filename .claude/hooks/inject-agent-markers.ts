#!/usr/bin/env bun
/**
 * inject-agent-markers.ts
 *
 * PostToolUse hook that expands markers in agent files at runtime.
 * When an agent file containing <!-- ACCESS_RULES --> or <!-- SUBORDINATES -->
 * is read, this hook outputs the formatted content derived from the YAML
 * frontmatter as additional context. The file on disk is NEVER modified —
 * markers persist in the file and are expanded in memory each time.
 *
 *   <!-- ACCESS_RULES -->   → formatted list of access rules from frontmatter
 *   <!-- SUBORDINATES -->   → formatted list of subordinate agents with descriptions
 *
 * Always exits 0 (non-blocking).
 */

import { readFileSync } from 'node:fs';
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

// ---------- formatting ----------

/**
 * Format the access rules as a bullet list string.
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

// ---------- main ----------

async function main() {
  const raw = await Bun.stdin.text();
  let input: HookInput;
  try {
    input = JSON.parse(raw) as HookInput;
  } catch {
    process.exit(0);
  }

  // Only process Read tool on agent files
  if (input.tool_name !== 'Read') {
    process.exit(0);
  }

  const toolInput = input.tool_input ?? {};
  const filePath = (toolInput.file_path as string | undefined) ?? '';

  // Only process agent files
  if (!filePath.endsWith('.md') || !filePath.includes('.claude/agents/')) {
    process.exit(0);
  }

  try {
    const content = readFileSync(filePath, 'utf-8');
    const fm = parseFrontmatter(content);
    if (!fm) process.exit(0);

    const expansions: string[] = [];

    if (content.includes('<!-- ACCESS_RULES -->')) {
      expansions.push(`<!-- ACCESS_RULES --> expands to:\n${formatAccessRules(fm.access)}`);
    }

    if (content.includes('<!-- SUBORDINATES -->')) {
      expansions.push(`<!-- SUBORDINATES --> expands to:\n${formatSubordinates(fm.subordinates, process.cwd())}`);
    }

    if (expansions.length > 0) {
      process.stdout.write(expansions.join('\n\n'));
    }
  } catch {
    // File may not exist or be unreadable — non-critical
  }

  process.exit(0);
}

main();
