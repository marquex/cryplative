# Expert agents

Expert agents are custom AI agents that are specialized on one specific domain. These agents are designed to learn from what the have done and build up expertise in a specific area.

There are 2 main features that make expert agents different from regular agents:

* They have a long-term memory that allows them to remember what they have done and learn from it. This memory is persisted across sessions, so the agent can build up expertise over time and every time it is used it can leverage that expertise to perform better and be more efficient.
* They have restricted access to tools and files, so they can only read or write to specific files that are relevant to their domain. This allows them to focus on their area of expertise and avoid distractions from irrelevant information.


## Structure of an expert agent

They are created in the `.claude/agents/` as any other agent. If their file name is `expert-agent.md` we can say that {AGENT_NAME} is `expert-agent`. E.g if the file name is `code-expert.md` we can say that {AGENT_NAME} is `code-expert`.

Every expert agent has a folder to let them store their mental model and their long-term memory. This folder is located in `.claude/expertise/{AGENT_NAME}/` and we should grant the agent read, write and delete access to this folder, so they own those files. We should avoid editing those files directly, we should let the agent manage them the best they can.

The expertise folder should always have an index file for the mental model `.claude/expertise/{AGENT_NAME}/{AGENT_NAME}-index.yaml`. The agent must always read this file at the beginning of every session to load its mental model, and work based on their expertise. 

At the end of the session, the agent should update their expertise with any new thing they have learned.


### Agent Hierarchy

Agents are organized in a delegation hierarchy. Delegation always flows downward — from a manager to its subordinates. This creates a tree structure with no circular dependencies.

- Every agent can have a **manager** (an agent that delegates to it). Documented in the system prompt.
- Every agent can have **subordinates** (agents it delegates to). Declared in the `subordinates` frontmatter field and documented in the system prompt.
- An agent at the top has no manager. A leaf agent has no subordinates.
- The hierarchy can have many levels.

Use the `hire-expert` skill to create new agents with proper hierarchy integration. When an agent is created, its manager's file is automatically updated to include it as a subordinate, and its subordinates' files are updated to reference it as their manager.

### Agent File Template

The basic structure of the expert agent file follows the template below:

```md
---
name: expert-agent
description: A brief description of the expert agent's domain, purpose and when to use it
tools: Read, Grep, Glob
skills:
  - agent-expertise
subordinates: []  # list of agent names this agent can delegate to (omit if none)
access:
  - path: .claude/expertise/expert-agent/**
    permissions: [read, write, delete]
  - path: src/**
    permissions: [read]
hooks:
  PreToolUse:
    - matcher: "Read|Write|Edit|MultiEdit|Bash"
      hooks:
        - type: command
          command: "bun .claude/scripts/enforce-agent-access.ts"
---

[System prompt for the expert agent, its purposes and goals. It shouldn't include specific instructions, instead it needs to set the agent direction and the agent should learn how to achieve that goal by itself. Remark that the agent should build expertise on every session]

{If this agent has subordinates, include a Delegation section:}

## Delegation

You can delegate tasks to the following subordinate agents:

<!-- SUBORDINATES -->

Use the delegate skill: `bun .claude/skills/delegate/scripts/delegate.ts <agent-name> "<task>"`

{If this agent has a manager, mention it:}

Your manager is `manager-name` — you receive delegated tasks from it.

## Restricted domain

You have only access to the following folders:

<!-- ACCESS_RULES -->

This restriction is to keep you focused on your domain and avoid distractions. DO NOT TRY TO BYPASS THESE RESTRICTIONS, if your task requires access to files outside of these folders, fail the task and explain that you don't have access to those files.

```

The frontmatter of an expert agent has some specific content:
- The `agent-expertise` skill teach the agent how to build expertise and how to use its long-term memory on every session.
- The `delegate` skill is only included if the agent has subordinates (i.e., the `subordinates` list is non-empty).
- The `subordinates` field is a list of agent names that this agent can delegate to. Omit if the agent is a leaf agent with no delegation capability.
- The `access` section grants the agent permissions to read, write and delete files. It should include at least the path to the agent's expertise folder with read, write and delete permissions, and it can also include other paths with read permissions if needed.
- The `hooks` section includes a PreToolUse hook that runs `enforce-agent-access.ts` before using any tool. This script enforces the access restrictions AND enforces the delegation hierarchy — it denies delegation commands (`delegate.ts`) that target agents not listed in the `subordinates` frontmatter field.
- The `<!-- ACCESS_RULES -->` placeholder in the system prompt is replaced by the PostToolUse hook `inject-agent-markers.ts` with the formatted list of access rules from the frontmatter. The replacement happens automatically when the agent file is written.
- The `<!-- SUBORDINATES -->` placeholder (only for agents with subordinates) is replaced by the same PostToolUse hook with the formatted list of subordinate agents and their descriptions. The hook reads each subordinate's agent file to get the `description` field.


## Types of expert agents

Every AI agent is better by turning it into an expert agent, but the ones that benefit the most of this approach are the ones that are not developers. AI agents tends to explore the code and try to update it when they need to perform a task, but a project-manager agent or a CEO agent doesn't need to even know the code, they just need to have clear goals and build expertise on how to achieve them and can delegate the tasks that require code access to other developer agents.

Said so, for developer agents, building expertise and restricting their access to a certain area, makes them specialists that work better and faster on that area.

Ideally all agents that we create should be expert agents.

