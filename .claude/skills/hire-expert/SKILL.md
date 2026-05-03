---
name: hire-expert
description: "Create a new expert agent for the project. Use when you need to hire (create) a new specialized AI agent with a specific role, domain access, and optional delegation capabilities."
argument-hint: "<expert-description>"
---

# Hire Expert

Use this skill to create a new expert agent for the project. The skill guides you through gathering all required information and creating the agent file following the expert agent template.

## Agent Hierarchy

Agents are organized in a delegation hierarchy. Delegation always flows downward — from a manager to its subordinates. This creates a clear tree structure with no circular dependencies.

- Every agent can have a **manager** (an agent that delegates to it).
- Every agent can have **subordinates** (agents it delegates to).
- An agent at the top of the hierarchy has no manager.
- A leaf agent has no subordinates.
- The hierarchy can have many levels.

## Required Information

Before creating the agent, you need to gather the following:

1. **Name** — a kebab-case identifier (e.g., `code-reviewer`, `data-analyst`). Used as the agent file name and expertise folder name.
2. **Role description** — a clear description of the agent's purpose, what domain it specializes in, and when to use it. This becomes the `description` field in the frontmatter and the core of the system prompt.
3. **Folder access** — the folders the agent needs to access (read-only or read-write). These become `access` rules. The agent's own expertise folder (`.claude/expertise/{name}/**`) is always included with read/write/delete.
4. **Manager** — which existing agent is this agent's manager. If specified, the manager agent will be updated to include this new agent as a subordinate. If not specified, this agent is a top-level agent.
5. **Subordinates** — which existing agents this agent can delegate to. If specified, the `delegate` skill is included and the agent's system prompt lists its subordinates. If not specified, this is a leaf agent that cannot delegate.
6. **Model** (optional) — the model for the agent. Defaults to `sonnet` if not specified.

## Steps

Follow these steps in order:

### Step 1: Parse the user's description

The user provides a description of the expert they want to hire. Extract from it as much of the required information as possible.

### Step 2: Ask follow-up questions for missing information

If any required information is missing from the description, ask the user follow-up questions to gather it. Be specific about what you need. Group related questions together to minimize back-and-forth.

Information that can be inferred or defaulted does not need to be asked:
- If no model is specified, default to `sonnet`.
- If the role description is clear enough, derive the folder access from it (e.g., a `code-reviewer` likely needs access to source files, a `data-analyst` needs access to data files). However, if it's ambiguous, ask.

For manager and subordinates:
- If neither manager nor subordinates are mentioned, ask about both: "Who is this agent's manager? And who are its subordinates (if any)?"
- If a manager is mentioned but no subordinates, ask: "What agents can {name} delegate to? Or is it a leaf agent with no subordinates?"
- If subordinates are mentioned but no manager, ask: "Who is {name}'s manager? Which agent delegates to it?"
- If both are mentioned, no need to ask further about the hierarchy.
- You can also suggest a hierarchy position based on the role description (e.g., a "CEO" agent should be at the top, a "code-reviewer" likely reports to a "tech-lead" or "project-manager").

### Step 3: Confirm with the user

Before creating the agent, present a summary of the agent configuration to the user for confirmation:
- Name
- Description
- Folder access rules (with permissions)
- Manager (or "top-level agent" if none)
- Subordinates (or "leaf agent" if none)
- Model

Wait for the user to confirm or request changes.

### Step 4: Create the agent file

Create the agent file at `.claude/agents/{name}.md` following this template:

```md
---
name: {name}
description: {description — concise, explains domain, purpose, and when to use it}
tools: Read, Grep, Glob
model: {model — defaults to sonnet}
skills:
  - agent-expertise
{if has subordinates:  - delegate}
subordinates: {list of subordinate agent names, or omit if none}
access:
  - path: .claude/expertise/{name}/**
    permissions: [read, write, delete]
  - path: {folder}/**
    permissions: [read]
  {additional access rules as needed}
hooks:
  PreToolUse:
    - matcher: "Read|Write|Edit|MultiEdit|Bash"
      hooks:
        - type: command
          command: "bun .claude/scripts/enforce-agent-access.ts"
---

{System prompt — sets the agent's direction and goals. Should NOT include specific step-by-step instructions. Instead, describe the agent's purpose, what it should aim to achieve, and let the agent learn how to achieve it through its expertise.}

{if has subordinates, add a "## Delegation" section:}

## Delegation

You can delegate tasks to the following subordinate agents:

<!-- SUBORDINATES -->

Use the delegate skill to assign tasks: `bun .claude/skills/delegate/scripts/delegate.ts <agent-name> "<task>"`

{if has a manager, add:}

Your manager is `{manager-name}` — you receive delegated tasks from it.

## Restricted domain

You have access to the following folders:

<!-- ACCESS_RULES -->

This restriction is to keep you focused on your domain and avoid distractions. DO NOT TRY TO BYPASS THESE RESTRICTIONS — if a task requires access to files outside of these folders, fail the task and explain that you don't have access to those files.
```

Key rules for the agent file:
- The system prompt should be directional, not prescriptive. Let the agent build expertise on how to achieve its goals.
- Always include the `agent-expertise` skill — it teaches the agent how to manage its long-term memory.
- Only include `Write` and `Edit` in the `tools` list if the agent needs to write to files outside its expertise folder. Most expert agents only need read access to their domain files.
- Only include the `delegate` skill if the agent has subordinates.
- Always include the `PreToolUse` hook for `enforce-agent-access.ts`.
- Always include the `<!-- ACCESS_RULES -->` placeholder — the PostToolUse hook `inject-agent-markers.ts` replaces it with the actual access rules list from the frontmatter when the file is written.
- Always include the `<!-- SUBORDINATES -->` placeholder (only if the agent has subordinates) — the PostToolUse hook `inject-agent-markers.ts` replaces it with the formatted list of subordinates with their descriptions. To get the descriptions, the hook reads each subordinate's agent file `description` field.
- To get the description of a subordinate agent for the Delegation section, read its agent file at `.claude/agents/{subordinate-name}.md` and use its `description` field.

### Step 5: Update the manager agent (if a manager was specified)

If the new agent has a manager, you must update the manager's agent file to include the new agent as a subordinate:

1. Read the manager's agent file at `.claude/agents/{manager-name}.md`.
2. In the YAML frontmatter:
   - Add the new agent to the `subordinates` list (create the list if it doesn't exist).
   - Add the `delegate` skill to the `skills` list (if not already present).
3. In the system prompt:
   - If there is already a `## Delegation` section, add the new subordinate to the list. Include a brief description from the new agent's `description` field.
   - If there is no `## Delegation` section, add one before the `## Restricted domain` section with the full list of subordinates (read each subordinate's agent file to get descriptions).
4. Write the updated manager file.

### Step 6: Update the subordinates' manager reference (if subordinates were specified)

If the new agent has subordinates, you should check each subordinate agent's file to see if it references its manager. If a subordinate's system prompt mentions its old manager (or no manager), update it to reference the new agent as its manager. This keeps the hierarchy documentation consistent across all agent files.

### Step 7: Create the expertise folder

Create the expertise folder and index file at `.claude/expertise/{name}/{name}-index.yaml` with this initial content:

```yaml
# {Name} Expertise Index
# Agent: {name}
# Domain: {brief domain description}

hierarchy:
  manager: {manager name, or "none — top-level agent"}
  subordinates: [{list of subordinate names, or "none — leaf agent"}]

expertise_status: "New agent — no expertise accumulated yet. Start building expertise from the first session."
```

### Step 8: Validate

After creating the agent and updating any related agents:
1. Read back all modified files to confirm the content is correct and well-formed.
2. Verify the YAML frontmatter is valid in each modified agent file.
3. Verify the hierarchy is consistent — if A is B's manager, then B should appear in A's subordinates list, and A should be mentioned as B's manager.
