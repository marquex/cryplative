# Skills conventions

Usually skills have 2 parts:

* The prompt file that explains the new capability that the agent will learn, and how to use it. That's the `SKILL.md` file.
* The implementation of that capability in the form of a script, tool, or any other type of implementation. This part is optional, but providing scripts to the skills makes the agent use the new capability in a efficient and consistent way.

When the skill has no scripts usually describe a flow that the agent can follow to perform a task in a consistent way. This flow is defined as a list of steps that can be completed one by one to perform the task. When a task can be described as a list of steps, and it's performed often, it's always good to create a skill for it.

When the skill has scripts, the agent learn how to use a new tool, so the agent has more independence and can decide when and how to use that tool. The skill just give the agent a new capability, and the agent can use it in any way it wants to perform the task.

## Creating scripts for skills

* The scripts should be located in the `scripts/` folder of the skills and need to be implemented in typescript.
* The runtime for the scripts needs to be `bun` and the file extension needs to be `.ts`.
* If there is need to install dependencies, they should be added to the `package.json` of the `.claude` folder
* In the skill folder there should be a `reference.md` file that explains how to use the scripts and what options the have. The `SKILL.md` file should include a link to the `reference.md` to know how to use the scripts and all their features.


