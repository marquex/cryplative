#!/usr/bin/env bun
/**
 * Downloads and caches "Build with Claude Code" docs from code.claude.com.
 * Dynamically discovers all doc pages from llms.txt instead of hardcoding slugs.
 *
 * Usage: bun run update-docs.ts [--force]
 *   --force  Download even if docs are up to date
 */

import { parseArgs } from "node:util";
import {
  existsSync,
  mkdirSync,
  rmSync,
  readdirSync,
  writeFileSync,
  readFileSync,
  renameSync,
} from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = join(__dirname, "..", "docs");
const ORIGINAL_DIR = join(DOCS_DIR, "original");
const TEMP_DIR = join(DOCS_DIR, "temp");
const META_FILE = join(ORIGINAL_DIR, ".last-update");
const LLMS_URL = "https://code.claude.com/docs/llms.txt";
const BASE_DOC_URL = "https://code.claude.com/docs/en";

const SECONDS_PER_MONTH = 30 * 24 * 3600;

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    force: { type: "boolean", default: false },
  },
});

function needsUpdate(): boolean {
  if (values.force) return true;
  if (!existsSync(META_FILE)) return true;

  const last = readFileSync(META_FILE, "utf-8").trim();
  if (!last) return true;

  const lastMs = new Date(last).getTime();
  if (isNaN(lastMs)) return true;

  const elapsed = (Date.now() - lastMs) / 1000;
  return elapsed > SECONDS_PER_MONTH;
}

/** Extract slugs from llms.txt content. Looks for markdown links pointing to .md files. */
function parseSlugs(llmsContent: string): string[] {
  const slugs: string[] = [];
  // Match lines like: - [Title](https://code.claude.com/docs/en/slug.md): description
  const linkRegex = /\]\(https:\/\/code\.claude\.com\/docs\/en\/([^)]+?\.md)\)/g;
  let match: RegExpExecArray | null;
  while ((match = linkRegex.exec(llmsContent)) !== null) {
    // Remove .md extension to get the slug
    const slug = match[1].replace(/\.md$/, "");
    slugs.push(slug);
  }
  return slugs;
}

/** Convert a slug like "agent-sdk/overview" to a flat filename "agent-sdk_overview.md". */
function slugToFilename(slug: string): string {
  return `${slug.replace(/\//g, "_")}.md`;
}

/** Download a single doc and save to temp dir. Returns true on success. */
async function downloadDoc(slug: string): Promise<boolean> {
  const url = `${BASE_DOC_URL}/${slug}.md`;
  const filename = slugToFilename(slug);
  const outputPath = join(TEMP_DIR, filename);

  try {
    const res = await fetch(url);
    if (!res.ok || res.status >= 300) {
      console.log(`  SKIP: ${slug} (HTTP ${res.status})`);
      return false;
    }
    const text = await res.text();
    if (!text.trim()) {
      console.log(`  SKIP: ${slug} (empty)`);
      return false;
    }
    writeFileSync(outputPath, text, "utf-8");
    console.log(`  OK:   ${slug}`);
    return true;
  } catch (err) {
    console.log(`  SKIP: ${slug} (${err})`);
    return false;
  }
}

/** Fix internal links in all downloaded docs.
 *  Replaces (/en/slug) and (/en/slug/sub) with (slug.md) and (slug_sub.md).
 *  Preserves #fragment portions. */
function fixLinks(dir: string): void {
  const files = readdirSync(dir).filter((f) => f.endsWith(".md"));

  // Match (/en/...) or (/en/...#fragment) — captures the slug and optional fragment
  const linkPattern = /\(\/en\/([^)#\s]+?)(#[^)\s]*)?\)/g;

  for (const file of files) {
    const filePath = join(dir, file);
    let content = readFileSync(filePath, "utf-8");
    let changed = false;

    content = content.replace(linkPattern, (_match, slug: string, fragment: string | undefined) => {
      changed = true;
      const filename = slugToFilename(slug);
      return `(${filename}${fragment ?? ""})`;
    });

    // Also fix full URLs: https://code.claude.com/docs/en/slug → local file
    const fullUrlPattern = /\(https:\/\/code\.claude\.com\/docs\/en\/([^)#\s]+?)(#[^)\s]*)?\)/g;
    content = content.replace(fullUrlPattern, (_match, slug: string, fragment: string | undefined) => {
      changed = true;
      const filename = slugToFilename(slug);
      return `(${filename}${fragment ?? ""})`;
    });

    if (changed) {
      writeFileSync(filePath, content, "utf-8");
    }
  }
}

async function main(): Promise<void> {
  console.log("=== Claude Code Docs Updater ===\n");

  if (!needsUpdate()) {
    const lastUpdate = readFileSync(META_FILE, "utf-8").trim();
    console.log(`Docs are up to date (last updated: ${lastUpdate})`);
    console.log("Use --force to update anyway.");
    return;
  }

  // Step 1: Download llms.txt
  console.log("Fetching doc index from llms.txt...");
  let llmsContent: string;
  try {
    const res = await fetch(LLMS_URL);
    if (!res.ok) {
      console.error(`Failed to fetch llms.txt (HTTP ${res.status})`);
      process.exit(1);
    }
    llmsContent = await res.text();
  } catch (err) {
    console.error(`Failed to fetch llms.txt: ${err}`);
    process.exit(1);
  }

  // Step 2: Parse slugs
  const slugs = parseSlugs(llmsContent);
  if (slugs.length === 0) {
    console.error("No doc links found in llms.txt");
    process.exit(1);
  }
  console.log(`Found ${slugs.length} docs to download.\n`);

  // Step 3: Create temp dir, save llms.txt, and download all docs
  mkdirSync(TEMP_DIR, { recursive: true });
  writeFileSync(join(TEMP_DIR, "llms.txt"), llmsContent, "utf-8");

  let ok = 0;
  let skip = 0;
  for (const slug of slugs) {
    const success = await downloadDoc(slug);
    if (success) ok++;
    else skip++;
  }

  console.log(`\nDownloaded: ${ok}, Skipped: ${skip}\n`);

  if (ok === 0) {
    console.error("No docs were downloaded successfully. Aborting.");
    rmSync(TEMP_DIR, { recursive: true, force: true });
    process.exit(1);
  }

  // Step 4: Fix links in downloaded files
  console.log("Fixing internal links...");
  fixLinks(TEMP_DIR);

  // Step 5: Replace original docs with new ones
  console.log("Replacing original docs...");
  // Delete all files in original dir (but keep the directory itself)
  if (existsSync(ORIGINAL_DIR)) {
    for (const file of readdirSync(ORIGINAL_DIR)) {
      rmSync(join(ORIGINAL_DIR, file), { force: true });
    }
  } else {
    mkdirSync(ORIGINAL_DIR, { recursive: true });
  }

  // Move all files from temp to original
  for (const file of readdirSync(TEMP_DIR)) {
    renameSync(join(TEMP_DIR, file), join(ORIGINAL_DIR, file));
  }

  // Step 6: Delete temp dir
  rmSync(TEMP_DIR, { recursive: true, force: true });

  // Step 7: Write timestamp
  const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, "").replace("T", " ");
  writeFileSync(META_FILE, timestamp, "utf-8");

  const totalFiles = readdirSync(ORIGINAL_DIR).filter((f) => f.endsWith(".md")).length;
  console.log(`\nDone! ${totalFiles} docs cached.`);
  console.log(`Updated: ${timestamp}`);
}

main().catch((err) => {
  console.error(`Fatal error: ${err}`);
  // Clean up temp dir on failure
  if (existsSync(TEMP_DIR)) {
    rmSync(TEMP_DIR, { recursive: true, force: true });
  }
  process.exit(1);
});
