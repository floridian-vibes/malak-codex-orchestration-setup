# Usage example

This skill also installs reusable project guidance for scheduled Codex automation.
When the scheduled runtime needs Slack or GitHub access, route those calls through:

```bash
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge via-daemon <command>
```

Set up the user-session bridge once from an interactive run:

```bash
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge install-launchagent
python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge via-daemon preflight
```

Prompt to answer the skill's invitation:
```
Project root: /Users/username/Projects/<Project name>

Pipeline: <local root>/processes/development-pipeline.md

Role path:
- Architect: `<local root>/agents/architect.md`
- Developer: `<local root>/agents/developer.md`, role extension: `<local root>/agents/ios-macos-developer.md`
- Code reviewer: `<local root>/agents/code-reviewer.md` role extension: `<local root>/agents/ios-macos-code-reviewer.md` 
- Scenario Tester: `<local root>/agents/scenario-tester.md`
- Security Auditor: `<local root>/agents/security-auditor.md`

Reasoning: high

Max handoff turns: 15
```
