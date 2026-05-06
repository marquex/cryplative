# Cryplative Specifications Directory Structure

This document describes the reorganized specifications directory structure that supports inter-team communication with proper access controls.

## Directory Structure

```
.agentic/specs/
├── managers/        # Cross-team manager communication (CEO, CTO, Head of Research)
├── engineering/     # Engineering team specifications (CTO, claude-developer)
└── research/        # Research team specifications (Head of Research, research team members)
```

## Access Permissions

### `/managers/` - Cross-Team Manager Communication
**Who can access:** CEO, CTO, Head of Research
**Purpose:** High-level strategic coordination between team leaders
**Permissions:** read, write, delete

### `/engineering/` - Engineering Team Specifications  
**Who can access:** CTO, claude-developer
**Purpose:** Technical specifications, architecture decisions, implementation plans
**Permissions:** read, write, delete

**Current contents:**
- `000-platform-bootstrap.md` - Initial platform setup and architecture
- `001-progress.md` - Development progress tracking
- `001-researcher-ready-platform.md` - Platform requirements for research team
- `architecture-overview.md` - System architecture documentation
- `003-specs-folder-structure.md` - This document

### `/research/` - Research Team Specifications
**Who can access:** Head of Research, research team members
**Purpose:** Research methodologies, strategy specifications, data requirements
**Permissions:** read, write, delete

## Agent Access Configuration

The access permissions are enforced through agent configurations in `.claude/agents/`:

- **CEO:** Access to `.agentic/specs/managers/**` only
- **CTO:** Access to `.agentic/specs/managers/**` and `.agentic/specs/engineering/**`
- **Head of Research:** Access to `.agentic/specs/managers/**` and `.agentic/specs/research/**`
- **claude-developer:** Access to `.agentic/specs/engineering/**` only

## Implementation Details

### Changes Made
1. Created three subfolders: `managers/`, `engineering/`, and `research/`
2. Moved all existing specification files from root to `engineering/`
3. Updated agent access configurations to enforce folder-level restrictions

### Access Control Enforcement
The `enforce-agent-access.ts` hook script validates all file operations to ensure agents only access appropriate directories based on their configured access rules.

## Usage Guidelines

1. **Manager Communication:** Use `/managers/` for cross-team coordination and strategic decisions
2. **Technical Specs:** Use `/engineering/` for architecture, implementation details, and technical decisions
3. **Research Specs:** Use `/research/` for trading strategies, research methodologies, and data analysis

This structure ensures that:
- Sensitive information is only shared with appropriate teams
- Each team has clear ownership of their specifications
- Cross-team communication happens through designated channels
- Access controls are enforced automatically