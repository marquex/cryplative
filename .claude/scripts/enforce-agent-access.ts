#!/usr/bin/env bun
/**
 * Claude Code PreToolUse hook: enforce per-subagent filesystem access.
 *
 * Run with Bun (https://bun.sh). Bun executes TypeScript directly with no
 * build step. Uses only Node-compatible APIs (fs, path, os, process).
 *
 * Reads agent policy from the calling subagent's frontmatter `access` block:
 *
 *   ---
 *   name: docs-writer
 *   access:
 *     - path: docs/**
 *       permissions: [read, write]
 *     - path: src/**
 *       permissions: [read]
 *   ---
 *
 * Permission verbs: read, write, delete.
 *
 * Decision rules:
 *   - No `agent_type` on the event → main agent, allow.
 *   - No agent file found / no `access` block → fail closed: deny.
 *   - Path matches no rule → deny.
 *   - Path matches a rule but lacks the required verb → deny.
 *   - Otherwise → allow.
 *
 * Output: a PreToolUse hook JSON decision on stdout. Always exits 0 — the
 * decision rides in the JSON, not the exit code, so Claude sees the reason.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';

// ---------- types ----------

type Verb = 'read' | 'write' | 'delete';
type Decision = 'allow' | 'deny' | 'ask';

interface AccessRule {
  path: string;
  permissions: Verb[];
}

interface AgentPolicy {
  access: AccessRule[];
  subordinates: string[];
  [key: string]: unknown;
}

interface HookEvent {
  agent_type?: string;
  cwd?: string;
  tool_name: string;
  tool_input?: Record<string, unknown>;
}

interface ToolClassification {
  verb?: Verb;
  targets?: string[];
  skip?: boolean;
}

interface RuleMatchResult {
  matched: boolean;
  granted: boolean;
  rule: AccessRule | null;
}

// ---------- decision helpers ----------

function decide(decision: Decision, reason: string): never {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: decision,
      permissionDecisionReason: reason,
    },
  }));
  process.exit(0);
}

const allow = (reason: string): never => decide('allow', reason);
const deny  = (reason: string): never => decide('deny',  reason);

// ---------- read stdin ----------

function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c: string) => { data += c; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

// ---------- minimal YAML frontmatter parser ----------
// Supports exactly what we need: top-level scalars, and an `access:` list of
// `{ path: <string>, permissions: [<verb>, ...] }`. Anything fancier and we
// stop and let a real YAML parser handle it — but this avoids a dependency.

function stripQuotes(s: string): string {
  if (!s) return s;
  if ((s.startsWith('"') && s.endsWith('"')) ||
      (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}

const VALID_VERBS: ReadonlySet<string> = new Set(['read', 'write', 'delete']);

function parseFrontmatter(md: string): AgentPolicy | null {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return null;
  const body = m[1]!;
  const lines = body.split(/\r?\n/);

  const out: AgentPolicy = { access: [], subordinates: [] };
  let i = 0;

  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim() || line.trim().startsWith('#')) { i++; continue; }

    if (/^access\s*:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const l = lines[i]!;
        if (l.length && !/^\s/.test(l)) break;       // dedent → end of block
        if (!l.trim()) { i++; continue; }

        const pathMatch = l.match(/^\s*-\s*path\s*:\s*(.+?)\s*$/);
        if (!pathMatch) { i++; continue; }
        const rule: AccessRule = {
          path: stripQuotes(pathMatch[1]!),
          permissions: [],
        };
        i++;

        // sibling keys of this list item (indented further than the `-`)
        while (i < lines.length) {
          const sub = lines[i]!;
          if (!sub.trim()) { i++; continue; }
          if (/^\s*-\s/.test(sub) || !/^\s{2,}/.test(sub)) break;

          const permMatch = sub.match(/^\s*permissions\s*:\s*\[(.*)\]\s*$/);
          if (permMatch) {
            rule.permissions = permMatch[1]!
              .split(',')
              .map((s) => stripQuotes(s.trim()).toLowerCase())
              .filter((v): v is Verb => VALID_VERBS.has(v));
          }
          i++;
        }
        out.access.push(rule);
      }
      continue;
    }

    if (/^subordinates\s*:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const l = lines[i]!;
        if (l.length && !/^\s/.test(l)) break;       // dedent → end of block
        if (!l.trim()) { i++; continue; }
        const itemMatch = l.match(/^\s*-\s*(.+?)\s*$/);
        if (itemMatch) out.subordinates.push(stripQuotes(itemMatch[1]!));
        i++;
      }
      continue;
    }

    const kv = line.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/);
    if (kv) {
      const key = kv[1]!;
      const rawVal = stripQuotes(kv[2]!.trim());
      // Handle inline list: subordinates: [a, b, c]
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

// ---------- locate the agent file ----------

function findAgentFile(agentType: string, cwd: string): string | null {
  const candidates = [
    path.join(cwd, '.claude', 'agents', `${agentType}.md`),
    path.join(os.homedir(), '.claude', 'agents', `${agentType}.md`),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

// ---------- glob matching ----------
// Supports **, *, ?. Matches against POSIX-style paths relative to cwd.

function globToRegex(glob: string): RegExp {
  let re = '^';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i]!;
    if (c === '*') {
      if (glob[i + 1] === '*') {
        // **/  → match any number of path segments (including zero)
        if (glob[i + 2] === '/') { re += '(?:.*/)?'; i += 2; }
        else                     { re += '.*';        i += 1; }
      } else {
        re += '[^/]*';                                // *  → no slash
      }
    } else if (c === '?')      re += '[^/]';
    else if ('.+^$(){}|\\'.includes(c)) re += '\\' + c;
    else                       re += c;
  }
  return new RegExp(re + '$');
}

/**
 * Extract the directory prefix from a glob pattern that targets directory
 * contents. E.g. "platform/**" → "platform", "src/lib/*" → "src/lib".
 * Returns null for patterns that don't target a directory's contents.
 */
function getDirectoryPrefix(rulePath: string): string | null {
  const m = rulePath.match(/^(.+)\/\*\*?$/);
  return m ? m[1] : null;
}

function matchesAnyRule(absPath: string, rules: AccessRule[], verb: Verb, baseDir: string): RuleMatchResult {
  // rules with empty permissions = explicit deny for that path
  for (const rule of rules) {
    const normalizedTarget = absPath.split(path.sep).join("/"); const ruleAbsPath = path.resolve(baseDir, rule.path).split(path.sep).join("/"); const directMatch = globToRegex(ruleAbsPath).test(normalizedTarget);
    // A rule like "platform/**" or "platform/*" should also grant access to
    // the directory itself ("platform"), since you need to reach the directory
    // to access its contents (e.g. ls, stat, mkdir -p).
    const dirPrefix = getDirectoryPrefix(rule.path);
    const dirAbsMatch = dirPrefix !== null && normalizedTarget === path.resolve(baseDir, dirPrefix).split(path.sep).join("/"); const dirMatch = dirAbsMatch;

    if (directMatch || dirMatch) {
      if (rule.permissions.length === 0) {
        return { matched: true, granted: false, rule };
      }
      if (rule.permissions.includes(verb)) {
        return { matched: true, granted: true, rule };
      }
      return { matched: true, granted: false, rule };
    }
  }
  return { matched: false, granted: false, rule: null };
}

// ---------- map tool → required verb + target path(s) ----------

const READ_TOOLS:  ReadonlySet<string> = new Set(['Read', 'Grep', 'Glob']);
const WRITE_TOOLS: ReadonlySet<string> = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit']);

const DELETE_PATTERNS: readonly RegExp[] = [
  /\brm\b/,
  /\bunlink\b/,
  /\bshred\b/,
  /\bmv\s+[^|;&]+\s+\/dev\/null\b/,
];

const WRITE_BASH_PATTERNS: readonly RegExp[] = [
  />>?\s*\S/,                  // shell redirection
  /\btee\b/,
  /\bcp\b/, /\bmv\b/,
  /\bmkdir\b/, /\btouch\b/,
  /\bsed\s+-i\b/,
  /\b(?:dd|chmod|chown)\b/,
];

function extractBashTargets(cmd: string): string[] {
  const cleaned = cmd
    .replace(/(["'])(?:\\.|(?!\1).)*\1/g, (m) => m.slice(1, -1))  // unquote
    .replace(/[<>]+/g, ' ');                                       // drop redirects
  const tokens = cleaned.split(/\s+/).filter(Boolean);
  return tokens.filter((t) =>
    t.includes('/') || /^\.{1,2}$/.test(t) || /^[\w.-]+\.\w+$/.test(t)
  );
}

function classifyTool(toolName: string, toolInput: Record<string, unknown>): ToolClassification {
  const filePath = (toolInput.file_path ?? toolInput.path ?? toolInput.pattern) as string | undefined;

  if (READ_TOOLS.has(toolName)) {
    return { verb: 'read', targets: filePath ? [filePath] : [] };
  }
  if (WRITE_TOOLS.has(toolName)) {
    return { verb: 'write', targets: filePath ? [filePath] : [] };
  }
  if (toolName === 'Bash') {
    const cmd = (toolInput.command as string | undefined) ?? '';
    const isDelete = DELETE_PATTERNS.some((r) => r.test(cmd));
    const isWrite  = WRITE_BASH_PATTERNS.some((r) => r.test(cmd));
    if (!isDelete && !isWrite) return { skip: true };  // read-only bash, allow
    return {
      verb: isDelete ? 'delete' : 'write',
      targets: extractBashTargets(cmd),
    };
  }
  // Unknown tool (WebFetch, Task, MCP, etc.) — not our concern.
  return { skip: true };
}

// ---------- delegation detection ----------

/**
 * Detect if a Bash command is a delegation (calls delegate.ts) and extract
 * the target agent name.
 * Matches: bun .claude/skills/delegate/scripts/delegate.ts <agent-name> ...
 */
function detectDelegation(cmd: string): { target: string } {
  const match = cmd.match(/delegate\.ts\s+(\S+)/);
  return { target: match?.[1] ?? '' };
}

// ---------- main ----------

async function main(): Promise<never> {
  let event: HookEvent;
  try {
    event = JSON.parse(await readStdin()) as HookEvent;
  } catch (e) {
    return deny(`enforce-agent-access: malformed hook input (${(e as Error).message})`);
  }

  const agentType = event.agent_type;
  const cwd       = event.cwd || process.cwd();
  const toolName  = event.tool_name;
  const toolInput = event.tool_input ?? {};

  if (!agentType) return allow('main agent, no per-agent policy');

  const agentFile = findAgentFile(agentType, cwd);
  if (!agentFile) return deny(`enforce-agent-access: cannot locate agent file for '${agentType}'`);

  let policy: AgentPolicy | null;
  try {
    policy = parseFrontmatter(fs.readFileSync(agentFile, 'utf8'));
  } catch (e) {
    return deny(`enforce-agent-access: cannot parse '${agentFile}': ${(e as Error).message}`);
  }
  if (!policy || !Array.isArray(policy.access) || policy.access.length === 0) {
    return deny(`enforce-agent-access: agent '${agentType}' has no 'access' block`);
  }

  // --- Delegation enforcement ---
  // Before checking file access rules, verify that delegation commands
  // only target agents listed in the 'subordinates' frontmatter field.
  if (toolName === 'Bash') {
    const cmd = (toolInput.command as string | undefined) ?? '';
    const delegation = detectDelegation(cmd);
    if (delegation.target) {
      if (!Array.isArray(policy.subordinates) || policy.subordinates.length === 0) {
        return deny(
          `enforce-delegation: agent '${agentType}' has no subordinates and cannot delegate to anyone. ` +
          `Remove the delegate skill or add a 'subordinates' field to the agent's frontmatter.`
        );
      }
      if (!policy.subordinates.includes(delegation.target)) {
        return deny(
          `enforce-delegation: agent '${agentType}' cannot delegate to '${delegation.target}' — ` +
          `authorized subordinates: [${policy.subordinates.join(', ')}]`
        );
      }
      return allow(
        `enforce-delegation: agent '${agentType}' delegates to '${delegation.target}' (authorized subordinate)`
      );
    }
  }

  const cls = classifyTool(toolName, toolInput);
  if (cls.skip) return allow(`tool '${toolName}' not governed by access policy`);
  if (!cls.targets || cls.targets.length === 0) {
    return deny(`enforce-agent-access: ${toolName} call without resolvable path`);
  }
  const verb = cls.verb!;

  for (const raw of cls.targets) {
    // Resolve to absolute, then back to a path relative to cwd. realpath on
    // the parent dir defeats `..` traversal even if the file doesn't exist yet.
    let abs: string;
    try {
      const resolved = path.resolve(cwd, raw);
      const parent   = path.dirname(resolved);
      abs = fs.existsSync(parent)
        ? path.join(fs.realpathSync(parent), path.basename(resolved))
        : resolved;
    } catch {
      abs = path.resolve(cwd, raw);
    }

    const cwdReal = fs.existsSync(cwd) ? fs.realpathSync(cwd) : cwd;
    const rel = path.relative(cwdReal, abs).split(path.sep).join('/');

    if (rel.startsWith('..') || path.isAbsolute(rel)) {
      return deny(`agent '${agentType}' may not access path outside project: ${raw}`);
    }

    // Auto-allow agents to read their own agent file.
    // This is needed for the marker injection system (PostToolUse hook) to
    // expand <!-- ACCESS_RULES --> and <!-- SUBORDINATES --> so the agent
    // knows its own permissions. Without this, agents with no explicit rule
    // covering .claude/agents/<name>.md can never see their own access rules.
    const agentFileReal = fs.existsSync(agentFile)
      ? fs.realpathSync(agentFile)
      : agentFile;
    if (verb === 'read' && abs === agentFileReal) {
      continue;
    }

    const result = matchesAnyRule(abs, policy.access, verb, cwdReal);
    if (!result.matched) {
      return deny(`agent '${agentType}' has no access rule covering '${rel}'`);
    }
    if (!result.granted) {
      const perms = result.rule!.permissions.join(', ') || 'none';
      return deny(
        `agent '${agentType}' lacks '${verb}' permission on '${rel}' ` +
        `(rule: ${result.rule!.path} → [${perms}])`
      );
    }
  }

  return allow(`agent '${agentType}' has '${verb}' on all targets`);
}

main().catch((e: Error) => deny(`enforce-agent-access: ${e.message}`));