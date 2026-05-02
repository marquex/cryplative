# How to develop for claude code

You have now access to the official claude code documentation, but we don't want to use all claude code features in an uncontrolled way. Always follow the instructions above to develop for claude code in a consistent and efficient way:

* If you will create or update a skill, read the [skills conventions](./skills-conventions.md) to follow the best practices and make sure your skill is as useful as possible.
* If you are creating or maintaining an agent, consider making it an expert agent to make it more efficient and focused. Read the [expert agents doc](./expert-agents.md) to learn how to create expert agents and what are their benefits.
* Always try to avoid MCP, research if there is a CLI tool that provides the same functionality and use it from a skill instead.
* We must only have one CLAUDE.md at the root of the project. That file shouldn't be used as memory, as the expert agents will manage their own memory. Instead, the CLAUDE.md should act as an overview to the project, describing what's the project about so all agents can work with that common knowledge.