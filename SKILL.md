---
name: malak-codex-orchestration-setup
description: "Set up a project-local Codex subagent workflow from existing role markdown files and a shared pipeline file without copying those source files. Use when the user wants Codex to create `.codex/agents/*.toml`, render the main initialization prompt, and create or update project `AGENTS.md` for a reusable orchestration setup."
---

# Malak Codex Orchestration Setup

## Skill Development Convention

When modifying this skill, follow `~/Workspace/My-private-obsidian-knowledge/Personal properties/Technical Profile/Skill development - {convention}.md` as the single source of truth for skill naming, architecture, stable commands, authorization, secrets, and output-mode rules.

Use this skill when the user wants to wire a project to Codex subagents while keeping each role description and the shared pipeline in their original locations.

This skill is setup-oriented:
- ask only for the minimum missing inputs;
- keep role markdown files and the pipeline file at their source paths;
- create project-local Codex agent definitions that point at those original files;
- create or update project `AGENTS.md` with orchestration guidance Codex can read automatically;
- render the initialization prompt the user can paste into the main Codex chat;
- configure the main orchestrator for automatic handoffs through the main thread by default;
- keep the main orchestrator in a coordination-only role instead of letting it do agent work itself;
- force user-facing questions from subagents, especially the architect, to be relayed in the main chat;
- avoid copying role or pipeline files into `.codex` or elsewhere in the project.

## External Credentials And Auth Policy

- This skill is local-only and normally requires no external service authorization.
- If a future version of this skill ever needs external auth, verify auth readiness before modifying the target project.
- Never store OAuth credentials, API keys, tokens, or other secrets inside `~/Workspace/My-skills`, `~/.codex/skills`, or any Git-tracked skill repository.
- Store any future secrets outside the skill repository under `~/Workspace/command-center/secrets/<skill-slug>/`.

## Canonical Commands

- Canonical helper prefix:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py`
- Canonical helper invocations:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py doctor --stdin`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py setup --stdin`
- Canonical plugin or tool actions:
  `functions.exec_command`
  `functions.write_stdin`
- Canonical git commands:
  none for the normal workflow

## Required Inputs

Collect inputs in this order. Ask only for the next missing item, but prefer one bundled question when several inputs are missing.

1. `pipeline_path`
2. `role_paths`
3. `reasoning_level`
4. `max_handoff_turns`
5. `project_root` only when the current workspace should not be used

Input rules:

- `pipeline_path` must point to the shared file that describes sequencing, handoffs, or collaboration rules for the agents.
- `role_paths` must be a list of markdown files, one per agent role.
- `reasoning_level` must be one of `none`, `low`, `medium`, `high`, or `xhigh`.
- `max_handoff_turns` must be a positive integer.
- `project_root` must be the project where Codex should create `.codex/agents/*.toml`, `.codex/prompts/subagent-init.md`, and `AGENTS.md`.
- Role and pipeline files should stay in their original locations. This skill must not copy them into the target project.

Default assumptions:

- If `project_root` is missing, use the current workspace path by default.
- If `reasoning_level` is missing, use `medium` by default.
- If `max_handoff_turns` is missing, use `12` by default.
- If the user provides role paths as a newline-separated list or bullets, normalize them to an array without asking for reformatting.
- If a role filename already maps cleanly to a slug, use that slug for the project-local Codex agent name.
- If multiple role files normalize to the same slug, append a numeric suffix and report the final names.
- Always write `AGENTS.md` with uppercase because that is the Codex-recognized filename, even if the user says `agents.md`.

## Canonical First Question

When the user did not yet provide the pipeline path and role paths, ask them to fill this markdown block exactly:

```md
Project root: <root folder>

Pipeline:
- <path-to-your-pipeline>

Role path:
- <path-to-agent-role-1>
- <path-to-agent-role-2>

Reasoning: <none | low | medium (default) | high | xhigh>

Max handoff turns: <integer, default 12>
```

Question rules:

- Return the markdown block as-is and ask the user to replace the placeholder paths.
- If the current workspace should be used, the user may leave `Project root` blank and the skill should resolve it to the current workspace.
- If the user wants a different target project than the current workspace, ask one short follow-up question for `project_root` after they return the markdown.
- If they already provided either the pipeline path or some role paths, reuse what they gave and ask only for the missing items.
- If they omit `Reasoning`, use `medium`.
- If they omit `Max handoff turns`, use `12`.
- Reasoning options should be interpreted as:
  - `none`: minimum deliberate reasoning
  - `low`: light reasoning, lower latency
  - `medium`: balanced default
  - `high`: deeper reasoning
  - `xhigh`: deepest reasoning, highest latency and cost

## Approval Rules

- Ask for approval only when the canonical helper prefix needs it or the platform raises a new prompt.
- Do not replace the helper with shell pipelines, heredocs, temp files, or one-off scripts.
- Keep terminal commands on the canonical absolute helper path so future approvals can be reused.
- The helper writes only to the target project path supplied by the user.

Approve forever once when the platform asks:

- `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py`

No canonical git prefix is required for the normal workflow.

## Workflow

1. If `pipeline_path` or `role_paths` are missing, send the canonical markdown block from `Canonical First Question`.
2. Resolve `project_root` to the current workspace by default, unless the user explicitly wants another project.
3. Resolve `reasoning_level` to `medium` by default when the user leaves it blank.
4. Resolve `max_handoff_turns` to `12` by default when the user leaves it blank.
5. Collect the final `project_root`, `pipeline_path`, `role_paths`, `reasoning_level`, and `max_handoff_turns`.
6. Start the helper with:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py doctor --stdin`
7. Send this JSON payload through stdin:

```json
{
  "project_root": "/absolute/path/to/project",
  "pipeline_path": "/absolute/path/to/pipeline.md",
  "role_paths": [
    "/absolute/path/to/researcher.md",
    "/absolute/path/to/planner.md",
    "/absolute/path/to/implementer.md",
    "/absolute/path/to/reviewer.md"
  ],
  "reasoning_level": "medium",
  "max_handoff_turns": 12
}
```

8. If `doctor` reports blockers, explain them plainly and stop.
9. If `doctor` is clean, run:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py setup --stdin`
10. Send the same JSON payload through stdin.
11. The helper will:
   - create `.codex/agents/*.toml` in the target project;
   - create `.codex/prompts/subagent-init.md`;
   - create or update `AGENTS.md` using a managed block;
   - embed `Auto-Handoff Mode` rules for the main orchestrator;
   - embed `User Question Relay` rules so architect questions are surfaced in the main chat;
   - write the selected `model_reasoning_effort` into each generated subagent TOML;
   - write the selected max handoff cap into the generated orchestration docs;
   - keep role and pipeline source files at their original paths;
   - return the rendered initialization prompt and the written file paths.
12. Return the initialization prompt in the final answer, plus the key file paths that were written.
13. On reruns for an already configured project, render the same initialization prompt from the current inputs instead of switching to a shortened, delta-only, or repair-only prompt.

## Auto-Handoff Mode

The generated orchestration documents must define automatic handoff as the default behavior for the main orchestrator.

Required behavior:

- When the user asks to start or continue the configured workflow, the main orchestrator must run automatic handoff by default.
- The main orchestrator must not perform the substantive work assigned to child roles; it may only orchestrate, route, summarize, and relay according to the pipeline.
- Ordinary user tasks must be passed to the next role per pipeline in the form the user wrote them, unless the user is explicitly asking an orchestration question or issuing an orchestration command.
- After each child agent finishes one move, the main orchestrator must:
  - read the full shared pipeline file from its original path;
  - detect the latest `HANDOFF: ...` marker when the pipeline uses that convention;
  - route the next move to the addressed project subagent from the main orchestrator thread;
  - repeat until a terminal condition is reached, the user stops the workflow, or the configured max-turn limit is hit.
- Child agents must not directly continue each other's threads. All handoffs go through the main orchestrator.
- If the user does not specify a limit, use a default safety cap of `12` handoff turns, report when it is reached, and ask whether to continue.
- If the user configures a project-specific max handoff cap during setup, generated project docs should use that configured value as the workflow default until explicitly overridden.
- The generated `AGENTS.md` and `.codex/prompts/subagent-init.md` should both carry these rules so the behavior survives reuse across future tasks.
- The generated prompt should state this compactly so the orchestration intent is clear without unnecessary extra text.

## User Question Relay

The generated orchestration documents must also define a strict relay rule for user-facing questions.

Required behavior:

- If a subagent needs clarification from the user without which it cannot proceed or finalize safely, the main orchestrator must relay that question in the main chat immediately.
- This rule is especially important for the architect: if the architect asks a question at the beginning or end of its move, that question must be surfaced to the user and must not remain only in the architect subagent thread.
- When a user-facing question is surfaced, the orchestrator must pause the auto-handoff loop until the user answers.
- Generated subagent instructions should ask the child agent to mark such cases explicitly with a `USER QUESTION:` section so the orchestrator can relay them reliably.

## File Outputs

The helper writes these project files:

- `<project_root>/.codex/agents/<role>.toml`
- `<project_root>/.codex/prompts/subagent-init.md`
- `<project_root>/AGENTS.md`

Write rules:

- Do not copy the source role markdown files.
- Do not copy the source pipeline file.
- Reference the original absolute paths inside the generated TOML, prompt, and `AGENTS.md`.
- If `AGENTS.md` already exists, update only the managed orchestration block and preserve the rest of the file.

## Output Contract

This skill is currently configured for `Default output`.

Return:

- a short confirmation that the orchestration setup was written
- the target project path
- the reasoning level that was applied
- the max handoff turns that were applied
- the final agent names that were created
- the paths to `AGENTS.md` and `.codex/prompts/subagent-init.md`
- the initialization prompt text ready to paste into the main Codex chat
- on reruns, the same full initialization prompt shape as on the first run
- any warnings, such as slug collisions or pre-existing managed blocks that were refreshed

If the helper reports an error, return a short error explanation and the blocker.

## Modes

- Interactive mode:
  ask first with the canonical markdown block for project root, pipeline, role paths, reasoning, and max handoff turns, infer `project_root` from the current workspace when safe, then run `doctor`, then `setup`
- Automation mode:
  rely only on the preapproved helper prefix; if approval is missing or the target project is not writable, stop and report the blocker

## Example Invocations

- `Use $malak-codex-orchestration-setup to configure this project from these role markdown files and this pipeline without copying them.`
- `Set up Codex subagents for /path/to/repo using these role files and this shared pipeline.`
- `Wire this project to a reusable Codex subagent workflow and generate the init prompt I should paste into the main chat.`
