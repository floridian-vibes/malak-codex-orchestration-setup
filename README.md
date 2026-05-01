# Usage example

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
