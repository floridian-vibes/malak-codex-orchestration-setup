# Usage example

This skill also installs reusable project guidance for scheduled Codex automation.
When the scheduled runtime needs Slack or GitHub access, route those calls through:

```bash
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge request <command>
```

Set up the user-session bridge once from an interactive run:

```bash
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge install-launchagent
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge request preflight
```

Do not run `install-launchagent` from scheduled automation. Scheduled automation should use `request <command>`. The LaunchAgent is demand-start only: `RunAtLoad = false`, `KeepAlive = false`, and no work happens while the Codex automation is paused.

Prompt to answer the skill's invitation:
```
Project root: /Users/username/Projects/<Project name>

Pipeline: <local root>/processes/development-pipeline.md

Role path:
- Architect: `<local root>/agents/architect.md`
- backend-developer: `<local root>/agents/developer.md`
- frontend-developer: `<local root>/agents/developer.md`
- ios-developer: `<local root>/agents/ios-macos-developer.md`
- Code reviewer: `<local root>/agents/code-reviewer.md` role extension: `<local root>/agents/ios-macos-code-reviewer.md` 
- Scenario Tester: `<local root>/agents/scenario-tester.md`
- Security Auditor: `<local root>/agents/security-auditor.md`

Pipeline id: development-pipeline

Backend: threads

Prompt mode: execute

Reasoning: high

Max handoff turns: 15
```

Use `Backend: subagents` for ephemeral Codex subagents. Use `Backend: threads` when each role should live in its own durable Codex app thread. In thread mode, reuse is keyed by `role_id`, not by role file path, so `backend-developer` and `frontend-developer` can both point at the same `developer.md` file while keeping separate durable threads. Every created role thread is titled with the stable prefix `agent:`, for example `agent:backend-developer` or `agent:scenario-tester`. Shared role thread IDs are written to `.codex/orchestration/role-threads.json`; pipeline-specific references are written to `.codex/orchestration/pipelines/<pipeline_id>/threads.json`.
