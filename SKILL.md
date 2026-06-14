---
name: malak-codex-orchestration-setup
description: "Set up a project-local Codex orchestration workflow from existing role markdown files and a shared pipeline file without copying those source files. Use when the user wants Codex to create either ephemeral project subagents or durable role threads, render the main orchestration prompt, create or update project `AGENTS.md`, and configure scheduled automation guidance that routes Slack/GitHub external access through a LaunchAgent bridge instead of the restricted automation runtime."
---

# Malak Codex Orchestration Setup

## Skill Development Convention

When modifying this skill, follow `~/Workspace/My-private-obsidian-knowledge/Personal properties/Technical Profile/Skill development - {convention}.md` as the single source of truth for skill naming, architecture, stable commands, authorization, secrets, and output-mode rules.

Use this skill when the user wants to wire a project to Codex role orchestration while keeping each role description and the shared pipeline in their original locations.

This skill is setup-oriented:
- ask only for the minimum missing inputs;
- keep role markdown files and the pipeline file at their source paths;
- create project-local Codex agent definitions for ephemeral subagent mode, or durable Codex app role threads for thread mode, that point at those original files;
- create or update project `AGENTS.md` with orchestration guidance Codex can read automatically;
- render the orchestration prompt the user can paste into the main Codex chat;
- generate scheduled Codex automation guidance that sends Slack/GitHub external calls through a user-session LaunchAgent bridge when the scheduled runtime has restricted DNS or network access;
- configure the main orchestrator for automatic handoffs through the main thread by default;
- keep the main orchestrator in a coordination-only role instead of letting it do agent work itself;
- force all child agents or durable role threads to run strictly sequentially, including validation roles;
- force user-facing questions from subagents or durable role threads, especially the architect, to be relayed in the main chat;
- when using durable thread mode, title every role thread with the exact prefix `agent:` using the form `agent:<role_id>`, where `role_id` is the explicit role identity;
- when using durable thread mode, reuse existing project role threads by `role_id` from `.codex/orchestration/role-threads.json`; do not use `role_path` as identity because multiple distinct roles can share the same role file;
- avoid copying role or pipeline files into `.codex` or elsewhere in the project.

## External Credentials And Auth Policy

- This skill is local-only and normally requires no external service authorization.
- The generated orchestration setup may need external Slack or GitHub access at runtime. Scheduled Codex automation must not call Slack or GitHub directly from the restricted automation runtime when DNS/network access is unreliable.
- Use the LaunchAgent-backed external access bridge for scheduled automation Slack/GitHub calls:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir <project-root>/.codex/external-access-bridge request <command>`
- Use a project-local `--bridge-dir` for scheduled automations so the restricted automation runtime can write request and response files under its own project workspace.
- Scheduled automation must never call `install-launchagent`. Install or refresh the demand-start LaunchAgent only from an interactive user session.
- The bridge supports bounded external operations only: `preflight`, `slack-post`, and `github-get`. Do not use it as a generic shell runner.
- For Slack delivery, the default bot-token env file is:
  `~/Workspace/command-center/secrets/slack-pulse-ai-bot.env`
- Override Slack credentials with `MALAK_CODEX_ORCH_SLACK_ENV` or the bridge `--slack-env` option when needed.
- For GitHub API access, use `GITHUB_TOKEN` or `GH_TOKEN` from process env or:
  `~/Workspace/command-center/secrets/malak-codex-orchestration-setup/github.env`
- Override GitHub credentials with `MALAK_CODEX_ORCH_GITHUB_ENV` or the bridge `--github-env` option when needed.
- Never store OAuth credentials, API keys, tokens, or other secrets inside `~/Workspace/My-skills`, `~/.codex/skills`, or any Git-tracked skill repository.
- Store secrets outside the skill repository under `~/Workspace/command-center/secrets/...`.
- Default non-sensitive bridge state lives under:
  `~/Workspace/command-center/malak-codex-orchestration-setup/external-bridge/`
- Scheduled automations should pass a project-local `--bridge-dir <project-root>/.codex/external-access-bridge` so the restricted runtime can write request and response files inside its own workspace.

## Canonical Commands

- Canonical helper prefix:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py`
- Canonical external access bridge prefix:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py`
- Canonical helper invocations:
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py doctor --stdin`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py setup --stdin`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py register-threads --stdin`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge install-launchagent`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge request preflight`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge request slack-post --channel C123 --text "message"`
  `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir /absolute/project/.codex/external-access-bridge request github-get --api-path /repos/owner/repo --output /absolute/path/output.json`
- Canonical plugin or tool actions:
  `functions.exec_command`
  `functions.write_stdin`
  `codex_app.create_thread`
  `codex_app.set_thread_title`
  `codex_app.send_message_to_thread`
  `codex_app.list_threads`
- Canonical git commands:
  none for the normal workflow

## Required Inputs

Collect inputs in this order. In interactive mode, if the current user message does not already include `pipeline_path`, `role_paths`, and `prompt_mode`, return the full canonical first question and stop. Do not infer missing setup inputs from existing project files, previous runs, or conversation context.

1. `pipeline_path`
2. `role_paths`
3. `pipeline_id`
4. `orchestration_backend`
5. `prompt_mode`
6. `reasoning_level`
7. `max_handoff_turns`
8. `project_root` only when the current workspace should not be used

Input rules:

- `pipeline_path` must point to the shared file that describes sequencing, handoffs, or collaboration rules for the agents.
- `role_paths` must be a list of markdown role definitions, one per agent role. Each entry may be a plain role file path, a string in the form `<role_id>: <path>`, or an object with `role_id` and `path`.
- `role_id` is the stable identity for reuse in durable thread mode. It is not the same as `role_path`; different role IDs may point to the same role file.
- `pipeline_id` is optional. If omitted, the helper derives it from the pipeline filename. Use an explicit `pipeline_id` when one project has several pipelines with similar filenames or when you want a stable custom registry path.
- `orchestration_backend` must be one of `subagents` or `threads`.
- `prompt_mode` must be one of `initialize` or `execute`.
- For backward compatibility, accept legacy prompt modes `initialize subagents`, `execute subagents`, `initialize threads`, and `execute threads`; normalize them to `orchestration_backend` plus `prompt_mode`.
- `reasoning_level` must be one of `none`, `low`, `medium`, `high`, or `xhigh`.
- `max_handoff_turns` must be a positive integer.
- In subagent mode, `project_root` must be the project where Codex should create `.codex/agents/*.toml`, `.codex/prompts/subagent-init.md`, and `AGENTS.md`.
- In durable thread mode, `project_root` must be the project where Codex should create `.codex/orchestration/role-threads.json`, `.codex/orchestration/pipelines/<pipeline_id>/threads.json`, `.codex/prompts/thread-orchestration.md`, `.codex/prompts/thread-roles/*.md`, and `AGENTS.md`.
- Role and pipeline files should stay in their original locations. This skill must not copy them into the target project.

Default assumptions:

- If `project_root` is missing, use the current workspace path by default.
- If `pipeline_id` is missing, derive it from the pipeline filename.
- If `orchestration_backend` is missing, use `subagents` by default unless the user asks for separate, persistent, durable, or long-lived role threads.
- If `prompt_mode` is missing, ask for it. There is no default prompt mode.
- If `reasoning_level` is missing, use `medium` by default.
- If `max_handoff_turns` is missing, use `12` by default.
- If the user provides role paths as a newline-separated list or bullets, normalize them to an array without asking for reformatting.
- If a role entry has an explicit `role_id`, use that as the project-local Codex agent name or durable role thread identity.
- If a role entry is only a path, derive `role_id` from the role filename.
- If multiple role entries normalize to the same `role_id`, append a numeric suffix and report the final names.
- Always write `AGENTS.md` with uppercase because that is the Codex-recognized filename, even if the user says `agents.md`.
- In durable thread mode, every thread created for a role must be titled `agent:<role_id>`, for example `agent:backend-developer`.

## Canonical First Question

When the current user message does not include `pipeline_path`, `role_paths`, and `prompt_mode`, ask them to fill this markdown block exactly:

```md
Project root: <root folder>

Pipeline:
- <path-to-your-pipeline>

Role path:
- <role_id-1>: <path-to-agent-role-1>
- <role_id-2>: <path-to-agent-role-2>

Pipeline id: <stable-pipeline-id, optional>

Backend: <subagents (default) | threads>

Prompt mode: <initialize | execute>

Reasoning: <none | low | medium (default) | high | xhigh>

Max handoff turns: <integer, default 12>
```

Question rules:

- Return the markdown block as-is and ask the user to replace the placeholder paths.
- If the current workspace should be used, the user may leave `Project root` blank and the skill should resolve it to the current workspace.
- If the user wants a different target project than the current workspace, ask one short follow-up question for `project_root` after they return the markdown.
- If any of `Pipeline`, `Role path`, or `Prompt mode` is missing, show the full canonical block again instead of asking a single-field question.
- If `Pipeline id` is missing, derive it from the pipeline filename.
- If `Backend` is missing, use `subagents` by default unless the user explicitly asked for separate, persistent, durable, or long-lived role threads.
- Role path entries should use explicit `role_id` when role identity matters, especially when multiple roles share the same role file:
  - `backend-developer: /path/to/developer.md`
  - `frontend-developer: /path/to/developer.md`
- Prompt mode options should be interpreted as:
  - `initialize`: only initialize configured child agents or role threads and collect readiness reports: mission, expected inputs, expected outputs, immediate blockers
  - `execute`: make the orchestrator drive configured child agents or role threads to perform their roles for the user task or run context, including collecting data and producing the role-specific outputs required by the pipeline
- Backend options should be interpreted as:
  - `subagents`: create project-local `.codex/agents/*.toml` definitions and use Codex subagents as ephemeral child workers
  - `threads`: create separate durable Codex app role threads, save reusable role thread IDs in `.codex/orchestration/role-threads.json`, save pipeline-specific role references in `.codex/orchestration/pipelines/<pipeline_id>/threads.json`, and route future handoffs to those existing threads
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
- `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py`

No canonical git prefix is required for the normal workflow.

## Workflow

1. If the current user message does not include `pipeline_path`, `role_paths`, and `prompt_mode`, send the full canonical markdown block from `Canonical First Question` and stop. Do not run `doctor` or `setup`.
2. Resolve `project_root` to the current workspace by default, unless the user explicitly wants another project.
3. Collect `orchestration_backend`; if it is missing, use `subagents` unless the user asked for separate, persistent, durable, or long-lived role threads.
4. Collect `prompt_mode` from the user; if it is missing, ask for it. Do not use a default prompt mode.
5. Resolve `reasoning_level` to `medium` by default when the user leaves it blank.
6. Resolve `max_handoff_turns` to `12` by default when the user leaves it blank.
7. Collect the final `project_root`, `pipeline_path`, `pipeline_id`, `role_paths`, `orchestration_backend`, `prompt_mode`, `reasoning_level`, and `max_handoff_turns`.
8. Start the helper with:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py doctor --stdin`
9. Send this JSON payload through stdin:

```json
{
  "project_root": "/absolute/path/to/project",
  "pipeline_path": "/absolute/path/to/pipeline.md",
  "pipeline_id": "development-pipeline",
  "role_paths": [
    { "role_id": "researcher", "path": "/absolute/path/to/researcher.md" },
    { "role_id": "planner", "path": "/absolute/path/to/planner.md" },
    { "role_id": "backend-developer", "path": "/absolute/path/to/developer.md" },
    { "role_id": "frontend-developer", "path": "/absolute/path/to/developer.md" },
    { "role_id": "reviewer", "path": "/absolute/path/to/reviewer.md" }
  ],
  "orchestration_backend": "threads",
  "prompt_mode": "execute",
  "reasoning_level": "medium",
  "max_handoff_turns": 12
}
```

10. If `doctor` reports blockers, explain them plainly and stop.
11. If `doctor` is clean, run:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py setup --stdin`
12. Send the same JSON payload through stdin.
13. In subagent mode, the helper will:
   - create `.codex/agents/*.toml` in the target project;
   - create `.codex/prompts/subagent-init.md`;
   - create or update `AGENTS.md` using a managed block;
   - embed `Auto-Handoff Mode` rules for the main orchestrator;
   - embed `Sequential Execution` rules that forbid parallel child-agent runs, including parallel validation;
   - embed `User Question Relay` rules so architect questions are surfaced in the main chat;
   - write the selected `model_reasoning_effort` into each generated subagent TOML;
   - write the selected max handoff cap into the generated orchestration docs;
   - write the selected prompt mode into the generated orchestration docs;
   - keep role and pipeline source files at their original paths;
   - embed scheduled automation external access rules that require Slack/GitHub calls to use the LaunchAgent-backed external access bridge instead of direct scheduled-runtime network calls;
   - return the rendered orchestration prompt and the written file paths.
14. In durable thread mode, the helper will:
   - read `.codex/orchestration/role-threads.json` when it exists;
   - reuse existing durable role threads by `role_id`;
   - create or update `.codex/orchestration/role-threads.json`;
   - create `.codex/orchestration/pipelines/<pipeline_id>/threads.json` with existing `thread_id` fields for reused roles and empty `thread_id` fields for new roles;
   - create `.codex/prompts/thread-orchestration.md`;
   - create one `.codex/prompts/thread-roles/<role_id>.md` initial prompt per new role that does not already have a registered thread;
   - create or update `AGENTS.md` using a managed durable-thread block;
   - return `reused_role_threads` for existing role IDs;
   - return `thread_creation_requests` only for missing role IDs, each with `role_id`, `thread_title`, `prompt_path`, and `prompt`.
15. In durable thread mode, create one Codex app thread per `thread_creation_requests` entry by calling `codex_app.create_thread` with:
   - `target.type = "project"`
   - `target.projectId = <project_root>`
   - `target.environment.type = "local"`
   - `prompt = <thread_creation_request.prompt>`
   - `thinking = <reasoning_level>` when it is one of `low`, `medium`, `high`, or `xhigh`; omit for `none`
16. After each durable role thread is created, call `codex_app.set_thread_title` and set its title exactly to `agent:<role_id>` from `thread_creation_request.thread_title`, for example `agent:backend-developer`.
17. Do not pin durable role threads automatically. The `agent:` title prefix is the discovery mechanism.
18. Collect the returned thread IDs into a JSON object keyed by `role_id` and run:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/orchestration_setup.py register-threads --stdin`
19. Send the same setup JSON payload plus the `thread_ids` object through stdin. It may include only newly created role IDs; the helper will merge them with existing entries from `.codex/orchestration/role-threads.json`:

```json
{
  "project_root": "/absolute/path/to/project",
  "pipeline_path": "/absolute/path/to/pipeline.md",
  "pipeline_id": "development-pipeline",
  "role_paths": [
    { "role_id": "researcher", "path": "/absolute/path/to/researcher.md" },
    { "role_id": "planner", "path": "/absolute/path/to/planner.md" },
    { "role_id": "backend-developer", "path": "/absolute/path/to/developer.md" },
    { "role_id": "frontend-developer", "path": "/absolute/path/to/developer.md" },
    { "role_id": "reviewer", "path": "/absolute/path/to/reviewer.md" }
  ],
  "orchestration_backend": "threads",
  "prompt_mode": "execute",
  "reasoning_level": "medium",
  "max_handoff_turns": 12,
  "thread_ids": {
    "researcher": "<thread-id>",
    "planner": "<thread-id>",
    "backend-developer": "<thread-id>",
    "frontend-developer": "<thread-id>",
    "reviewer": "<thread-id>"
  }
}
```

20. In durable thread mode, include one `::created-thread{threadId="..."}` directive per created role thread in the final answer, because Codex app thread creation requires that directive for user visibility.
21. If the user is creating or repairing a scheduled automation that will post to Slack, read from GitHub, or otherwise needs external Slack/GitHub access, install or refresh the bridge from the interactive run:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir <project-root>/.codex/external-access-bridge install-launchagent`
22. Then preflight the scheduled-runtime request path:
   `python3 /Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py --bridge-dir <project-root>/.codex/external-access-bridge request preflight`
23. Do not put Slack/GitHub tokens in the automation prompt. The automation prompt should call the bridge with `request` for Slack/GitHub operations and read secrets from `~/Workspace/command-center/secrets/...`.
24. Return the orchestration prompt in the final answer, plus the key file paths that were written.
25. On reruns for an already configured project, render the same orchestration prompt from the current inputs instead of switching to a shortened, delta-only, or repair-only prompt.

## Scheduled Automation External Access Bridge

Use this section when the configured orchestration workflow will be run by Codex scheduled automation and may need Slack or GitHub access.

Problem:

- normal Codex chat may have connector/network access that scheduled automation does not have;
- scheduled automation can fail with DNS or external network errors;
- Slack/GitHub delivery must still happen from the user's machine without sending messages from the user's Slack identity.

Required architecture:

1. Scheduled automation remains the orchestration and analysis layer.
2. Scheduled automation writes local artifacts and decides what external call is needed.
3. Scheduled automation calls the bridge helper with `request <command>`.
4. The bridge writes a request under the project-local `--bridge-dir`.
5. The bridge kickstarts the already-installed LaunchAgent.
6. The LaunchAgent runs once, processes pending request JSON files, writes responses, and exits.
7. The bridge returns a JSON result to the scheduled automation.
8. The automation records the Slack timestamp, GitHub output path, or delivery blocker in the final run output.

The LaunchAgent is not a scheduler. It must be installed with `RunAtLoad = false` and `KeepAlive = false`; it only runs when Codex scheduled automation creates a request and kickstarts it. If the Codex automation is paused, no request is created, the LaunchAgent is not kickstarted, and no Slack/GitHub work happens.

Scheduled automation must not run `install-launchagent`, `start-daemon`, or any long-running daemon bootstrap. If the LaunchAgent is not already installed or loaded, the scheduled run must fail with a clear blocker that says the bridge needs interactive setup.

Do not use the bridge for arbitrary shell execution. It only exposes bounded subcommands:

- `preflight`
- `slack-post`
- `github-get`

For Slack:

- use `slack-post`;
- send only through bot token credentials;
- never use the Codex Slack connector from scheduled automation for bot delivery;
- never post as the user's Slack identity.

For GitHub:

- use `github-get` for GitHub API paths or allowed GitHub HTTPS URLs;
- write large responses to an output file with `--output`;
- do not print tokens or embed them in URLs.

If bridge preflight fails during automation setup, report the blocker and do not create a misleading automation that will later fail silently.

## Auto-Handoff Mode

The generated orchestration documents must define automatic handoff as the default behavior for the main orchestrator.

Required behavior:

- When the user asks to start or continue the configured workflow, the main orchestrator must run automatic handoff by default.
- The main orchestrator must not perform the substantive work assigned to child roles; it may only orchestrate, route, summarize, and relay according to the pipeline.
- Ordinary user tasks must be passed to the next role per pipeline in the form the user wrote them, unless the user is explicitly asking an orchestration question or issuing an orchestration command.
- The main orchestrator must run exactly one child agent or durable role thread at a time.
- Parallel child-agent or role-thread execution is forbidden.
- Validation roles must also run one after another. Do not start or message Code Reviewer, Scenario Tester, Security Auditor, or any other validation role in parallel; wait for one validation role to finish before starting or messaging the next required validation role.
- After each child agent or role thread finishes one move, the main orchestrator must:
  - read the full shared pipeline file from its original path;
  - detect the latest `HANDOFF: ...` marker when the pipeline uses that convention;
  - route the next move to the addressed project subagent or durable role thread from the main orchestrator thread;
  - repeat until a terminal condition is reached, the user stops the workflow, or the configured max-turn limit is hit.
- Child agents or durable role threads must not directly continue each other's threads. All handoffs go through the main orchestrator.
- If the user does not specify a limit, use a default safety cap of `12` handoff turns, report when it is reached, and ask whether to continue.
- If the user configures a project-specific max handoff cap during setup, generated project docs should use that configured value as the workflow default until explicitly overridden.
- In subagent mode, the generated `AGENTS.md` and `.codex/prompts/subagent-init.md` should both carry these rules so the behavior survives reuse across future tasks.
- In durable thread mode, the generated `AGENTS.md`, `.codex/prompts/thread-orchestration.md`, `.codex/prompts/thread-roles/*.md`, `.codex/orchestration/role-threads.json`, and `.codex/orchestration/pipelines/<pipeline_id>/threads.json` should carry enough information for the orchestrator to reuse existing role threads.
- The generated orchestration docs should also carry scheduled automation external access rules so Slack/GitHub calls route through the LaunchAgent bridge when needed.
- The generated prompt should state this compactly so the orchestration intent is clear without unnecessary extra text.
- In `initialize` prompt mode, the generated prompt should initialize configured child agents or role threads and collect readiness reports.
- In `execute` prompt mode, the generated prompt must explicitly forbid readiness-only initialization and require child agents or role threads to perform their roles for the current task or run context.
- Missing local artifact or output directories are not blockers before preflight. Generated docs must tell the main orchestrator to create them before the first child handoff, and to block only if creation fails.
- In durable thread mode, generated docs must state that each created role thread title must start with `agent:` and should be exactly `agent:<role_id>`, where `role_id` is the explicit role identity.
- In durable thread mode, generated docs must state that reuse is keyed by `project_root + role_id`, not by `role_path`.

## User Question Relay

The generated orchestration documents must also define a strict relay rule for user-facing questions.

Required behavior:

- If a subagent or durable role thread needs clarification from the user without which it cannot proceed or finalize safely, the main orchestrator must relay that question in the main chat immediately.
- This rule is especially important for the architect: if the architect asks a question at the beginning or end of its move, that question must be surfaced to the user and must not remain only in the architect subagent or durable role thread.
- When a user-facing question is surfaced, the orchestrator must pause the auto-handoff loop until the user answers.
- Generated child instructions should ask the child agent or durable role thread to mark such cases explicitly with a `USER QUESTION:` section so the orchestrator can relay them reliably.

## File Outputs

The helper writes these project files in subagent mode:

- `<project_root>/.codex/agents/<role>.toml`
- `<project_root>/.codex/prompts/subagent-init.md`
- `<project_root>/AGENTS.md`

The helper writes these project files in durable thread mode:

- `<project_root>/.codex/orchestration/role-threads.json`
- `<project_root>/.codex/orchestration/pipelines/<pipeline_id>/threads.json`
- `<project_root>/.codex/prompts/thread-orchestration.md`
- `<project_root>/.codex/prompts/thread-roles/<role_id>.md`
- `<project_root>/AGENTS.md`

Write rules:

- Do not copy the source role markdown files.
- Do not copy the source pipeline file.
- Reference the original absolute paths inside generated TOML, JSON, prompts, and `AGENTS.md`.
- If `AGENTS.md` already exists, update only the managed orchestration block and preserve the rest of the file.
- In durable thread mode, write new thread IDs only through `register-threads --stdin` after `codex_app.create_thread` returns actual IDs. Existing role IDs may be reused from `.codex/orchestration/role-threads.json` without creating new threads.

## Output Contract

This skill is currently configured for `Default output`.

Return:

- a short confirmation that the orchestration setup was written
- the target project path
- the pipeline id that was applied
- the orchestration backend that was applied
- the prompt mode that was applied
- the reasoning level that was applied
- the max handoff turns that were applied
- the final agent names that were created or role thread names that were configured
- the paths to `AGENTS.md` and the generated orchestration prompt
- in durable thread mode, the path to `.codex/orchestration/role-threads.json`, the path to `.codex/orchestration/pipelines/<pipeline_id>/threads.json`, reused role threads, newly created role thread IDs, role thread titles, and one `::created-thread{threadId="..."}` directive per newly created thread
- the orchestration prompt text ready to paste into the main Codex chat
- on reruns, the same full orchestration prompt shape as on the first run
- any warnings, such as slug collisions or pre-existing managed blocks that were refreshed

If the helper reports an error, return a short error explanation and the blocker.

## Modes

- Interactive mode:
  ask first with the canonical markdown block for project root, pipeline, role paths, backend, prompt mode, reasoning, and max handoff turns, infer `project_root` from the current workspace when safe, then run `doctor`, then `setup`; in durable thread mode, create role threads and run `register-threads`
- Automation mode:
  rely only on the preapproved helper prefix; if approval is missing or the target project is not writable, stop and report the blocker

## Example Invocations

- `Use $malak-codex-orchestration-setup to configure this project from these role markdown files and this pipeline without copying them.`
- `Set up Codex subagents for /path/to/repo using these role files and this shared pipeline.`
- `Set up durable Codex role threads for /path/to/repo using these role files and this shared pipeline.`
- `Create separate persistent agent threads for each role and title them agent:<role_id>.`
- `Wire this project to a reusable Codex subagent workflow and generate the init prompt I should paste into the main chat.`
