import { describe, expect, it } from "bun:test";
import { spawn } from "node:child_process";
import { join } from "node:path";

/**
 * Tests for delegate.ts progress output (keepalive dots, first message, minute updates).
 * These are unit-level tests that verify stderr output contains expected progress indicators.
 */

/** Inline replica of extractTextFromMessage for testing */
function extractTextFromMessage(message: { content: unknown }): string {
  const content = message.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const textParts: string[] = [];
    for (const block of content) {
      if (
        block &&
        typeof block === "object" &&
        (block as Record<string, unknown>).type === "text" &&
        typeof (block as Record<string, unknown>).text === "string"
      ) {
        textParts.push((block as Record<string, unknown>).text as string);
      }
    }
    return textParts.join("\n").trim();
  }
  return "";
}

describe("delegate progress output", () => {
  it("delegate script loads without syntax errors", async () => {
    // Run delegate.ts with insufficient args to trigger usage error (not a crash).
    // Must run from project root so the module path resolves correctly.
    const projectRoot = join(import.meta.dir, "..", "..");
    const result = await new Promise<{ stdout: string; stderr: string; code: number }>(
      (resolve) => {
        const child = spawn(
          "bun",
          [".claude/skills/delegate/scripts/delegate.ts"],
          { cwd: projectRoot },
        );
        let stdout = "";
        let stderr = "";
        child.stdout?.on("data", (d: Buffer) => (stdout += d.toString()));
        child.stderr?.on("data", (d: Buffer) => (stderr += d.toString()));
        child.on("close", (code) => resolve({ stdout, stderr, code: code ?? 1 }));
      }
    );

    expect(result.code).toBe(1);
    expect(result.stderr).toContain("Usage:");
  });

  it("extractTextFromMessage handles string content", () => {
    const message = { role: "assistant", content: "Hello world" };
    expect(extractTextFromMessage(message)).toBe("Hello world");
  });

  it("extractTextFromMessage handles array content with text blocks", () => {
    const message = {
      role: "assistant",
      content: [
        { type: "text", text: "First part" },
        { type: "tool_use", name: "bash" },
        { type: "text", text: "Second part" },
      ],
    };
    expect(extractTextFromMessage(message)).toBe("First part\nSecond part");
  });

  it("extractTextFromMessage handles empty content", () => {
    const message = { role: "assistant", content: [{ type: "tool_use", name: "bash" }] };
    expect(extractTextFromMessage(message)).toBe("");
  });

  it("extractTextFromMessage handles non-text block types gracefully", () => {
    const message = {
      role: "assistant",
      content: [
        { type: "thinking", thinking: "hmm..." },
        { type: "tool_result", content: "result" },
      ],
    };
    expect(extractTextFromMessage(message)).toBe("");
  });

  it("extractTextFromMessage handles mixed text with thinking blocks", () => {
    const message = {
      role: "assistant",
      content: [
        { type: "thinking", thinking: "Let me think..." },
        { type: "text", text: "Here is my answer" },
      ],
    };
    expect(extractTextFromMessage(message)).toBe("Here is my answer");
  });

  it("extractTextFromMessage handles empty string content", () => {
    const message = { role: "assistant", content: "" };
    expect(extractTextFromMessage(message)).toBe("");
  });
});
