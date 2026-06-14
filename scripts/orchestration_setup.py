#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANAGED_BEGIN = "<!-- BEGIN MALAK CODEX ORCHESTRATION SETUP -->"
MANAGED_END = "<!-- END MALAK CODEX ORCHESTRATION SETUP -->"
DEFAULT_SAFETY_CAP = 12
DEFAULT_REASONING_LEVEL = "medium"
ALLOWED_REASONING_LEVELS = ("none", "low", "medium", "high", "xhigh")
ALLOWED_BACKENDS = ("subagents", "threads")
ALLOWED_PROMPT_MODES = ("initialize", "execute")
LEGACY_PROMPT_MODES = (
    "initialize subagents",
    "execute subagents",
    "initialize threads",
    "execute threads",
)
EXTERNAL_ACCESS_BRIDGE = (
    "/Users/master/Workspace/My-skills/malak-codex-orchestration-setup/scripts/external_access_bridge.py"
)


@dataclass
class RoleSpec:
    role_id: str
    display_name: str
    path: Path

    @property
    def slug(self) -> str:
        return self.role_id


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "agent"


def read_payload_from_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("stdin payload is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def resolve_path(raw_path: str, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{label} must be a non-empty string")
    path = Path(raw_path).expanduser()
    try:
        path = path.resolve()
    except FileNotFoundError:
        path = path.absolute()
    return path


def markdown_title(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def clean_markdown_value(value: str) -> str:
    value = value.strip()
    value = value.strip("`")
    return value.strip()


def parse_role_entry(raw_entry: Any, index: int) -> tuple[str | None, Path, str | None]:
    if isinstance(raw_entry, str):
        entry = raw_entry.strip()
        if not entry:
            raise ValueError(f"role_paths[{index}] must not be empty")
        explicit_role_id: str | None = None
        raw_path = entry
        if ":" in entry:
            possible_role_id, possible_path = entry.split(":", 1)
            if possible_role_id.strip() and possible_path.strip():
                explicit_role_id = slugify(possible_role_id)
                raw_path = possible_path.strip()
        raw_path = clean_markdown_value(raw_path)
        return explicit_role_id, resolve_path(raw_path, f"role_paths[{index}]"), None

    if isinstance(raw_entry, dict):
        raw_role_id = (
            raw_entry.get("role_id")
            or raw_entry.get("id")
            or raw_entry.get("slug")
            or raw_entry.get("name")
        )
        explicit_role_id = slugify(str(raw_role_id)) if raw_role_id not in (None, "") else None
        raw_path = raw_entry.get("path") or raw_entry.get("role_path")
        role_path = resolve_path(raw_path, f"role_paths[{index}].path")
        raw_display_name = raw_entry.get("display_name")
        display_name = str(raw_display_name).strip() if raw_display_name not in (None, "") else None
        return explicit_role_id, role_path, display_name

    raise ValueError(
        f"role_paths[{index}] must be a path string, '<role_id>: <path>' string, or object"
    )


def derive_roles(raw_role_entries: list[Any]) -> tuple[list[RoleSpec], list[str]]:
    roles: list[RoleSpec] = []
    warnings: list[str] = []
    used: dict[str, int] = {}

    for index, raw_entry in enumerate(raw_role_entries, start=1):
        explicit_role_id, role_path, explicit_display_name = parse_role_entry(raw_entry, index)
        base_role_id = explicit_role_id or slugify(role_path.stem)
        count = used.get(base_role_id, 0)
        used[base_role_id] = count + 1
        role_id = base_role_id if count == 0 else f"{base_role_id}-{count + 1}"
        if role_id != base_role_id:
            warnings.append(
                f"role_id collision for '{base_role_id}', created '{role_id}' for {role_path}"
            )
        title = (
            explicit_display_name
            or markdown_title(role_path)
            or role_id.replace("-", " ").replace("_", " ").title()
        )
        roles.append(RoleSpec(role_id=role_id, display_name=title, path=role_path))

    return roles, warnings


def role_registry_path(project_root: Path) -> Path:
    return project_root / ".codex" / "orchestration" / "role-threads.json"


def pipeline_registry_path(project_root: Path, pipeline_id: str) -> Path:
    return project_root / ".codex" / "orchestration" / "pipelines" / pipeline_id / "threads.json"


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def existing_role_threads_by_id(project_root: Path) -> dict[str, dict[str, Any]]:
    registry = load_json_file(role_registry_path(project_root))
    raw_roles = registry.get("roles", [])
    if not isinstance(raw_roles, list):
        raise ValueError(f"{role_registry_path(project_root)} roles must be an array")
    result: dict[str, dict[str, Any]] = {}
    for item in raw_roles:
        if not isinstance(item, dict):
            continue
        role_id = item.get("role_id") or item.get("slug")
        if isinstance(role_id, str) and role_id.strip():
            result[role_id.strip()] = item
    return result


def normalize_backend_and_prompt_mode(payload: dict[str, Any]) -> tuple[str, str]:
    raw_backend = payload.get("orchestration_backend", payload.get("backend"))
    if raw_backend in (None, ""):
        backend: str | None = None
    elif isinstance(raw_backend, str):
        backend = raw_backend.strip().lower()
    else:
        raise ValueError("orchestration_backend must be a string")
    if backend is not None and backend not in ALLOWED_BACKENDS:
        allowed = ", ".join(ALLOWED_BACKENDS)
        raise ValueError(f"orchestration_backend must be one of: {allowed}")

    raw_prompt_mode = payload.get("prompt_mode")
    if not isinstance(raw_prompt_mode, str) or not raw_prompt_mode.strip():
        allowed = ", ".join(ALLOWED_PROMPT_MODES + LEGACY_PROMPT_MODES)
        raise ValueError(f"prompt_mode is required and must be one of: {allowed}")
    prompt_mode = re.sub(r"\s+", " ", raw_prompt_mode.strip().lower())

    if prompt_mode in LEGACY_PROMPT_MODES:
        mode, legacy_backend = prompt_mode.split(" ", 1)
        if backend is not None and backend != legacy_backend:
            raise ValueError(
                "prompt_mode backend conflicts with orchestration_backend "
                f"({prompt_mode!r} vs {backend!r})"
            )
        return legacy_backend, mode

    if prompt_mode not in ALLOWED_PROMPT_MODES:
        allowed = ", ".join(ALLOWED_PROMPT_MODES + LEGACY_PROMPT_MODES)
        raise ValueError(f"prompt_mode must be one of: {allowed}")
    return backend or "subagents", prompt_mode


def validate_payload(
    payload: dict[str, Any],
) -> tuple[Path, Path, str, list[RoleSpec], str, int, str, str, list[str]]:
    raw_project_root = payload.get("project_root")
    if isinstance(raw_project_root, str) and raw_project_root.strip():
        project_root = resolve_path(raw_project_root, "project_root")
    else:
        project_root = Path.cwd().resolve()
    pipeline_path = resolve_path(payload.get("pipeline_path"), "pipeline_path")
    raw_pipeline_id = payload.get("pipeline_id")
    if raw_pipeline_id in (None, ""):
        pipeline_id = slugify(pipeline_path.stem)
    elif isinstance(raw_pipeline_id, str):
        pipeline_id = slugify(raw_pipeline_id)
    else:
        raise ValueError("pipeline_id must be a string")
    raw_role_entries = payload.get("role_paths")
    if not isinstance(raw_role_entries, list) or not raw_role_entries:
        raise ValueError("role_paths must be a non-empty array")
    raw_reasoning_level = payload.get("reasoning_level")
    if raw_reasoning_level in (None, ""):
        reasoning_level = DEFAULT_REASONING_LEVEL
    elif isinstance(raw_reasoning_level, str):
        reasoning_level = raw_reasoning_level.strip().lower()
    else:
        raise ValueError("reasoning_level must be a string")
    if reasoning_level not in ALLOWED_REASONING_LEVELS:
        allowed = ", ".join(ALLOWED_REASONING_LEVELS)
        raise ValueError(f"reasoning_level must be one of: {allowed}")
    raw_max_handoff_turns = payload.get("max_handoff_turns")
    if raw_max_handoff_turns in (None, ""):
        max_handoff_turns = DEFAULT_SAFETY_CAP
    elif isinstance(raw_max_handoff_turns, int):
        max_handoff_turns = raw_max_handoff_turns
    elif isinstance(raw_max_handoff_turns, str) and raw_max_handoff_turns.strip():
        try:
            max_handoff_turns = int(raw_max_handoff_turns.strip())
        except ValueError as exc:
            raise ValueError("max_handoff_turns must be an integer") from exc
    else:
        raise ValueError("max_handoff_turns must be an integer")
    if max_handoff_turns <= 0:
        raise ValueError("max_handoff_turns must be greater than 0")
    orchestration_backend, prompt_mode = normalize_backend_and_prompt_mode(payload)

    roles, warnings = derive_roles(raw_role_entries)

    errors: list[str] = []
    if not project_root.exists():
        errors.append(f"project_root does not exist: {project_root}")
    elif not project_root.is_dir():
        errors.append(f"project_root is not a directory: {project_root}")

    if not pipeline_path.exists():
        errors.append(f"pipeline_path does not exist: {pipeline_path}")
    elif not pipeline_path.is_file():
        errors.append(f"pipeline_path is not a file: {pipeline_path}")

    for role in roles:
        if not role.path.exists():
            errors.append(f"role path does not exist: {role.path}")
        elif not role.path.is_file():
            errors.append(f"role path is not a file: {role.path}")

    if errors:
        raise ValueError("; ".join(errors))

    return (
        project_root,
        pipeline_path,
        pipeline_id,
        roles,
        reasoning_level,
        max_handoff_turns,
        prompt_mode,
        orchestration_backend,
        warnings,
    )


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_agent_toml(role: RoleSpec, pipeline_path: Path, reasoning_level: str) -> str:
    description = (
        f"Project subagent that loads role instructions from {role.path} "
        f"and follows the shared pipeline at {pipeline_path}."
    )
    instructions = f"""Before doing any work:
1. Read the role file at `{role.path}`.
2. Read the shared pipeline file at `{pipeline_path}`.
3. Use the role file as the source of truth for your responsibilities, constraints, and output format.
4. Use the pipeline file as the source of truth for sequencing, dependencies, and handoff expectations.
5. Do not copy, rewrite, or relocate the role or pipeline files unless the user explicitly asks.
6. Return concise handoff updates to the main orchestrator thread, including:
   - status
   - summary
   - outputs for the next stage
   - open questions or blockers
7. If you need clarification or a decision from the user before continuing or finalizing, include:
   - USER QUESTION: <the exact user-facing question>
   - WHY IT BLOCKS: <why the workflow cannot continue safely without that answer>
8. In scheduled Codex automation, do not call Slack, GitHub, or other external network integrations directly from the restricted automation runtime. Ask the main orchestrator to use the LaunchAgent-backed external access bridge at `{EXTERNAL_ACCESS_BRIDGE}`.
"""

    return (
        f'name = "{toml_escape(role.slug)}"\n'
        f'description = "{toml_escape(description)}"\n'
        f'model_reasoning_effort = "{toml_escape(reasoning_level)}"\n'
        f'developer_instructions = """\n{instructions}"""\n'
    )


def build_prompt_text(
    roles: list[RoleSpec],
    pipeline_path: Path,
    pipeline_id: str,
    project_root: Path,
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    orchestration_backend: str,
) -> str:
    role_names = ", ".join(role.slug for role in roles)
    role_lines = "\n".join(f"- `{role.slug}`: `{role.path}`" for role in roles)
    bridge_dir = project_root / ".codex" / "external-access-bridge"
    if prompt_mode == "initialize":
        subagent_task_block = """Initialization task:
1. Initialize the configured agents sequentially, one at a time.
2. For each agent, have it read its role file and the shared pipeline, then report:
   - mission
   - expected inputs
   - expected outputs
   - any immediate `USER QUESTION:`
3. Do not start the next initialization agent until the current one has finished.
4. Return a consolidated readiness report, then wait for my first task."""
        thread_task_block = """Initialization task:
1. Verify that every configured durable role thread exists in the pipeline registry under `.codex/orchestration/pipelines/<pipeline_id>/threads.json` and has a non-empty `thread_id`.
2. Send one readiness request at a time to each role thread through Codex app thread messaging.
3. For each role thread, ask it to read its role file and the shared pipeline, then report:
   - mission
   - expected inputs
   - expected outputs
   - any immediate `USER QUESTION:`
4. Do not message the next role thread until the current role thread has replied.
5. Return a consolidated readiness report, then wait for my first task."""
    else:
        subagent_task_block = """Execution task:
1. Do not run a readiness-only initialization pass.
2. Run the configured agents sequentially, one at a time, according to the shared pipeline and the task or run context I provide.
3. For each agent, have it read its role file and the shared pipeline, then perform its role for the current workflow.
4. Before the first child handoff, create any required local artifact root or output directories from the pipeline.
5. Give each child agent the current task or run context, the artifact or output requirements from the pipeline, and an explicit instruction to save or return the role-specific output expected by its role and the pipeline.
6. If a required run context, source, artifact root, or output target is missing, ask a blocking `USER QUESTION:` in the main chat instead of silently downgrading to role description.
7. Do not start the next agent until the current one has returned its artifact path, role output, blocker, or explicit no-op/no-finding result.
8. After all required role outputs are complete, continue to the pipeline's synthesis, validation, or terminal step automatically."""
        thread_task_block = """Execution task:
1. Do not run a readiness-only initialization pass.
2. Use the configured durable role threads sequentially, one at a time, according to the shared pipeline and the task or run context I provide.
3. For each role, send the current move to the matching existing thread from the pipeline registry under `.codex/orchestration/pipelines/<pipeline_id>/threads.json`; do not spawn Codex subagents for these configured roles.
4. Before the first role-thread handoff, create any required local artifact root or output directories from the pipeline.
5. Give each role thread the current task or run context, the artifact or output requirements from the pipeline, and an explicit instruction to save or return the role-specific output expected by its role and the pipeline.
6. If a required run context, source, artifact root, output target, or role thread id is missing, ask a blocking `USER QUESTION:` in the main chat instead of silently downgrading to role description.
7. Do not message the next role thread until the current role thread has returned its artifact path, role output, blocker, or explicit no-op/no-finding result.
8. After all required role outputs are complete, continue to the pipeline's synthesis, validation, or terminal step automatically."""

    if orchestration_backend == "threads":
        registry_path = pipeline_registry_path(project_root, pipeline_id)
        role_registry = role_registry_path(project_root)
        role_thread_lines = "\n".join(
            f"- `{role.role_id}`: title `agent:{role.role_id}`, role file `{role.path}`" for role in roles
        )
        return f"""Use durable project role threads registered at `{registry_path}`: {role_names}.

Core rules:
- You are the main orchestrator only. Never do the substantive work of any role thread yourself.
- Do not spawn Codex subagents for the configured roles. Use the existing durable role threads from `{registry_path}`.
- Reuse project-level durable role threads from `{role_registry}` by `role_id`. If a role is already registered there, route to that existing thread instead of creating a duplicate.
- Every durable role thread created or repaired for this workflow must have a title beginning with `agent:` and should use the exact title `agent:<role_id>`, where `<role_id>` is the configured role identity. Example: `agent:backend-developer`.
- Default mode: if I give a task, pass it unchanged to the role thread that should act next under `{pipeline_path}`.
- Exception: only treat my message as an orchestration request when I explicitly ask about routing, handoff, pause/resume, limits, role choice, or fixing the workflow.
- All handoffs go through the main orchestrator thread; role threads must not message or continue each other directly.
- Run exactly one role thread at a time. Parallel role-thread execution is forbidden, including validation roles.
- If multiple validation roles are required, message them sequentially and wait for each validation role to finish before contacting the next one.
- When a role-thread move advances the pipeline, reread `{pipeline_path}`, detect the latest `HANDOFF: ...` marker when used, and route the next move automatically without waiting for my reminder.
- Pause only for a terminal condition, a safety-cap hit, a missing role thread id, or a blocking `USER QUESTION:`. Surface blocking user questions in the main chat immediately, especially from the architect.
- Before the first role-thread handoff, create required local artifact or output directories. Treat directory setup as a blocker only if this preflight creation fails.
- In scheduled Codex automation, do not call Slack or GitHub directly from the restricted automation runtime. Use the LaunchAgent-backed external access bridge at `{EXTERNAL_ACCESS_BRIDGE}` for Slack/GitHub operations.
- Use reasoning `{reasoning_level}` unless I override it. Use a safety cap of `{max_handoff_turns}` unless I override it for this run.
- Prompt mode: `{prompt_mode}`.
- Orchestration backend: `threads`.
- Pipeline id: `{pipeline_id}`.

{thread_task_block}

Configured durable role threads:
{role_thread_lines}

Shared pipeline:
- `{pipeline_path}`

Scheduled automation external access:
- Bridge helper: `{EXTERNAL_ACCESS_BRIDGE}`
- Project-local bridge dir: `{bridge_dir}`
- Setup/preflight from an interactive Codex or Terminal session:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} install-launchagent`
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request preflight`
- Slack delivery from automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request slack-post --channel <CHANNEL_ID> --text <MESSAGE>`
- GitHub API/read access from automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request github-get --api-path /repos/<owner>/<repo> --output <path>`
"""

    return f"""Use these configured project subagents: {role_names}.

Core rules:
- You are the main orchestrator only. Never do the substantive work of any child role yourself.
- Default mode: if I give a task, pass it unchanged to the role that should act next under `{pipeline_path}`.
- Exception: only treat my message as an orchestration request when I explicitly ask about routing, handoff, pause/resume, limits, role choice, or fixing the workflow.
- All handoffs go through the main orchestrator thread; child threads must not continue each other directly.
- Run exactly one child agent at a time. Parallel child-agent execution is forbidden, including validation roles.
- If multiple validation roles are required, run them sequentially and wait for each validation role to finish before starting the next one.
- When a child move advances the pipeline, reread `{pipeline_path}`, detect the latest `HANDOFF: ...` marker when used, and route the next move automatically without waiting for my reminder.
- Pause only for a terminal condition, a safety-cap hit, or a blocking `USER QUESTION:`. Surface blocking user questions in the main chat immediately, especially from the architect.
- Before the first child handoff, create required local artifact or output directories. Treat directory setup as a blocker only if this preflight creation fails.
- In scheduled Codex automation, do not call Slack or GitHub directly from the restricted automation runtime. Use the LaunchAgent-backed external access bridge at `{EXTERNAL_ACCESS_BRIDGE}` for Slack/GitHub operations.
- Use reasoning `{reasoning_level}` unless I override it. Use a safety cap of `{max_handoff_turns}` unless I override it for this run.
- Prompt mode: `{prompt_mode}`.
- Orchestration backend: `subagents`.

{subagent_task_block}

Configured roles:
{role_lines}

Shared pipeline:
- `{pipeline_path}`

Scheduled automation external access:
- Bridge helper: `{EXTERNAL_ACCESS_BRIDGE}`
- Project-local bridge dir: `{bridge_dir}`
- Setup/preflight from an interactive Codex or Terminal session:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} install-launchagent`
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request preflight`
- Slack delivery from automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request slack-post --channel <CHANNEL_ID> --text <MESSAGE>`
- GitHub API/read access from automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request github-get --api-path /repos/<owner>/<repo> --output <path>`
"""


def build_thread_role_prompt(
    role: RoleSpec,
    pipeline_path: Path,
    pipeline_id: str,
    project_root: Path,
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
) -> str:
    registry_path = pipeline_registry_path(project_root, pipeline_id)
    shared_registry_path = role_registry_path(project_root)
    return f"""You are the durable `{role.role_id}` role thread for this Codex orchestration project.

Thread title rule:
- Your thread title must be `agent:{role.role_id}`.
- If your title does not start with `agent:`, ask the orchestrator to rename it before continuing.

Role identity:
- Your stable `role_id` is `{role.role_id}`.
- Reuse is keyed by `role_id`, not by role file path. Different role IDs may use the same role file.

Project root:
- `{project_root}`

Role source:
- `{role.path}`

Shared pipeline:
- `{pipeline_path}`

Thread registry:
- `{registry_path}`

Project role registry:
- `{shared_registry_path}`

Operating rules:
1. Before every move, read the role file and shared pipeline from their original absolute paths.
2. Work only as the `{role.role_id}` role. Do not take over orchestration or another role's responsibilities.
3. Keep continuity inside this durable thread across future messages from the main orchestrator.
4. Return concise handoff updates to the main orchestrator, including status, summary, outputs for the next stage, open questions, and blockers.
5. If you need clarification or a decision from the user before continuing or finalizing, include:
   - USER QUESTION: <the exact user-facing question>
   - WHY IT BLOCKS: <why the workflow cannot continue safely without that answer>
6. Do not directly message or continue other role threads. All handoffs go through the main orchestrator.
7. In scheduled Codex automation, do not call Slack, GitHub, or other external network integrations directly from the restricted automation runtime. Ask the main orchestrator to use the LaunchAgent-backed external access bridge at `{EXTERNAL_ACCESS_BRIDGE}`.
8. Use reasoning `{reasoning_level}` unless the main orchestrator overrides it. The default handoff safety cap for the workflow is `{max_handoff_turns}`.
9. Prompt mode for this setup is `{prompt_mode}`.

Initial response:
- Confirm your role name, the role file, the shared pipeline, and whether you have any immediate `USER QUESTION:`.
"""


def build_threads_registry(
    roles: list[RoleSpec],
    pipeline_path: Path,
    pipeline_id: str,
    project_root: Path,
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    thread_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    thread_ids = thread_ids or {}
    return {
        "backend": "threads",
        "project_root": str(project_root),
        "pipeline_path": str(pipeline_path),
        "pipeline_id": pipeline_id,
        "project_role_registry_path": str(role_registry_path(project_root)),
        "prompt_mode": prompt_mode,
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "title_rule": "agent:<role_id>",
        "roles": [
            {
                "slug": role.slug,
                "role_id": role.role_id,
                "display_name": role.display_name,
                "role_path": str(role.path),
                "thread_title": f"agent:{role.role_id}",
                "thread_id": thread_ids.get(role.slug),
            }
            for role in roles
        ],
    }


def build_project_role_threads_registry(
    project_root: Path,
    roles: list[RoleSpec],
    thread_ids: dict[str, str | None],
    existing_roles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_roles = existing_roles or existing_role_threads_by_id(project_root)
    merged = dict(existing_roles)
    for role in roles:
        previous = merged.get(role.role_id, {})
        existing_thread_id = previous.get("thread_id")
        new_thread_id = thread_ids.get(role.role_id)
        merged[role.role_id] = {
            "role_id": role.role_id,
            "display_name": role.display_name,
            "role_path": str(role.path),
            "thread_title": f"agent:{role.role_id}",
            "thread_id": new_thread_id or existing_thread_id,
        }

    ordered_roles = [merged[key] for key in sorted(merged)]
    return {
        "backend": "threads",
        "project_root": str(project_root),
        "reuse_key": "project_root + role_id",
        "title_rule": "agent:<role_id>",
        "roles": ordered_roles,
    }


def extract_thread_ids(
    payload: dict[str, Any],
    roles: list[RoleSpec],
    existing_thread_ids: dict[str, str] | None = None,
) -> dict[str, str]:
    existing_thread_ids = existing_thread_ids or {}
    raw_thread_ids = payload.get("thread_ids")
    if raw_thread_ids is None:
        raw_role_threads = payload.get("role_threads")
        if isinstance(raw_role_threads, list):
            raw_thread_ids = {
                (item.get("role_id") or item.get("slug")): item.get("thread_id")
                for item in raw_role_threads
                if isinstance(item, dict)
            }
    if raw_thread_ids is None:
        raw_thread_ids = {}
    if not isinstance(raw_thread_ids, dict):
        raise ValueError("thread_ids must be an object mapping role_id to thread id")

    expected_slugs = {role.slug for role in roles}
    thread_ids: dict[str, str] = {}
    missing: list[str] = []
    for slug in sorted(expected_slugs):
        value = raw_thread_ids.get(slug) or existing_thread_ids.get(slug)
        if not isinstance(value, str) or not value.strip():
            missing.append(slug)
        else:
            thread_ids[slug] = value.strip()
    if missing:
        raise ValueError("missing thread_ids for role_id(s): " + ", ".join(missing))
    return thread_ids


def build_agents_md_block(
    roles: list[RoleSpec],
    pipeline_path: Path,
    pipeline_id: str,
    project_root: Path,
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    orchestration_backend: str,
) -> str:
    role_lines = "\n".join(f"- `{role.slug}`: `{role.path}`" for role in roles)
    bridge_dir = project_root / ".codex" / "external-access-bridge"
    if orchestration_backend == "threads":
        registry_path = pipeline_registry_path(project_root, pipeline_id)
        shared_registry_path = role_registry_path(project_root)
        prompt_path = project_root / ".codex" / "prompts" / "thread-orchestration.md"
        role_thread_lines = "\n".join(
            f"- `{role.role_id}`: title `agent:{role.role_id}`, role file `{role.path}`"
            for role in roles
        )
        return f"""{MANAGED_BEGIN}
## Codex Durable Role Thread Workflow

This project uses durable Codex app threads for each configured role. The role markdown files and the shared pipeline remain at their original source paths and must not be copied into the project.

### Source Of Truth

- Shared pipeline: `{pipeline_path}`
- Pipeline id: `{pipeline_id}`
- Pipeline thread registry: `{registry_path}`
- Project role thread registry: `{shared_registry_path}`
- Standard orchestration prompt: `{prompt_path}`
- Default reasoning level: `{reasoning_level}`
- Default max handoff turns: `{max_handoff_turns}`
- Configured prompt mode: `{prompt_mode}`
- Orchestration backend: `threads`

### Durable Role Threads

{role_thread_lines}

### Thread Naming Rule

- Every role thread created or repaired by the orchestrator must have a title that starts with `agent:`.
- Use the exact title `agent:<role_id>`, where `<role_id>` is the configured role identity. Example: `agent:backend-developer`.
- Reuse is keyed by `project_root + role_id`, not by role file path. Two different role IDs may use the same role file and must remain separate threads.
- The orchestrator must record each shared role thread id in `{shared_registry_path}` and each pipeline's selected role references in `{registry_path}`.

### Orchestration Rules

- Use durable role threads from `{registry_path}` when the user asks for the configured workflow.
- Reuse existing project role threads from `{shared_registry_path}` by `role_id`; do not create duplicates for role IDs already registered there.
- Do not spawn Codex subagents for the configured roles.
- The main chat is the orchestrator. Role threads report back to the main thread for handoff.
- The main orchestrator must not perform the substantive work of the configured role threads; it may only orchestrate, route, summarize, and relay according to the pipeline.
- Ordinary user tasks must be passed to the next role per pipeline in the form the user wrote them, unless the user is explicitly asking an orchestration question or issuing an orchestration command.
- The main orchestrator must message exactly one role thread at a time.
- Parallel role-thread execution is forbidden, including validation roles.
- If multiple validation roles are required, the orchestrator must message them sequentially and wait for each validation role to finish before messaging the next one.
- Follow the shared pipeline file for sequencing, dependencies, and handoff expectations.
- If a source role file or the pipeline changes, reread it from the original path instead of duplicating it.
- Missing local artifact or output directories are not blockers before preflight. The main orchestrator must create them before the first role-thread handoff; block only if creation fails.
- Missing role thread IDs in `{registry_path}` or `{shared_registry_path}` are blockers. The orchestrator must ask the user to create or repair the missing durable role threads.

### Scheduled Automation External Access

Scheduled Codex automation may have restricted DNS or external network access. If this workflow needs Slack delivery, GitHub API reads, GitHub raw file reads, or similar external integration during a scheduled run, the orchestrator must not call those services directly from the automation runtime.

Use the LaunchAgent-backed external access bridge instead:

- Bridge helper: `{EXTERNAL_ACCESS_BRIDGE}`
- Project-local bridge dir: `{bridge_dir}`
- Install or refresh the user-session LaunchAgent from an interactive Codex or Terminal session:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} install-launchagent`
- Preflight the request bridge through LaunchAgent:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request preflight`
- Send Slack messages from scheduled automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request slack-post --channel <CHANNEL_ID> --text <MESSAGE>`
- Read GitHub API or allowed GitHub HTTPS URLs from scheduled automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request github-get --api-path /repos/<owner>/<repo> --output <path>`

The bridge must use secrets only from `~/Workspace/command-center/secrets/...` or environment overrides. Never put tokens in role files, pipeline files, `AGENTS.md`, generated prompts, or automation prompts.

The scheduled automation run must never call `install-launchagent`. `install-launchagent` is setup-only and registers a demand-start LaunchAgent with `RunAtLoad = false` and `KeepAlive = false`. Scheduled automation uses `request ...`: the helper writes a request JSON, kickstarts the already-installed LaunchAgent, waits for a response, and then the LaunchAgent exits. If the LaunchAgent is not already installed or loaded, record a blocker with owner and next action.

If the bridge preflight fails, record the blocker, owner, next action, and the artifact that still needs delivery. Do not silently fall back to direct scheduled-runtime Slack or GitHub calls.

### Auto-Handoff Mode

- When the user asks to start or continue the configured workflow, the main orchestrator must run automatic handoff by default.
- After each role thread finishes one move, the main orchestrator must:
  1. Read the full shared pipeline file at `{pipeline_path}`.
  2. Detect the latest `HANDOFF: ...` marker when the pipeline uses that convention.
  3. Route the next move to the addressed durable role thread from the main orchestrator thread.
  4. Repeat until a terminal condition is reached, the user stops the workflow, or the max-turn limit is hit.
- Role threads must not directly continue each other. All handoffs go through the main orchestrator.
- If a role-thread move advances the pipeline and no blocker is present, the orchestrator must continue the next handoff automatically without waiting for user reminder.
- Unless the user explicitly overrides it for a run, use a safety cap of `{max_handoff_turns}` handoff turns, report when it is reached, and ask whether to continue.
- If a role thread asks a blocking user-facing question, stop the auto-handoff loop and relay that question in the main chat before continuing.

### User Question Relay

- If a role thread needs clarification or a decision from the user without which it cannot continue or finalize safely, the orchestrator must surface that question in the main chat immediately.
- This rule is especially strict for the architect role: if the architect asks a question at the beginning or end of its move, the orchestrator must relay it to the user and must not leave it only in the architect role thread.
- When a role thread emits a `USER QUESTION:` section, the orchestrator must copy the question into the main chat, explain that the workflow is paused on user input, and wait for the answer.

{MANAGED_END}
"""

    return f"""{MANAGED_BEGIN}
## Codex Subagent Workflow

This project uses project-local Codex subagents defined under `.codex/agents/`.
The role markdown files and the shared pipeline remain at their original source paths and must not be copied into the project.

### Source Of Truth

- Shared pipeline: `{pipeline_path}`
- Default reasoning level: `{reasoning_level}`
- Default max handoff turns: `{max_handoff_turns}`
- Configured prompt mode: `{prompt_mode}`
- Orchestration backend: `subagents`

### Role Files

{role_lines}

### Orchestration Rules

- Use the project-local agent definitions under `.codex/agents/` when the user asks for the configured workflow.
- The main chat is the orchestrator. Child agents report back to the main thread for handoff.
- The main orchestrator must not perform the substantive work of the configured child roles; it may only orchestrate, route, summarize, and relay according to the pipeline.
- Ordinary user tasks must be passed to the next role per pipeline in the form the user wrote them, unless the user is explicitly asking an orchestration question or issuing an orchestration command.
- The main orchestrator must run exactly one child agent at a time.
- Parallel child-agent execution is forbidden, including validation roles.
- If multiple validation roles are required, the orchestrator must run them sequentially and wait for each validation role to finish before starting the next one.
- Keep separate agent threads so the user can intervene manually in a specific role thread.
- Follow the shared pipeline file for sequencing, dependencies, and handoff expectations.
- If a source role file or the pipeline changes, reread it from the original path instead of duplicating it.
- The standard orchestration prompt lives at `.codex/prompts/subagent-init.md`.
- In `initialize` prompt mode, use the prompt only to initialize child agents and collect readiness reports.
- In `execute` prompt mode, use the prompt to make child agents perform their roles for the current task or run context and produce the role-specific outputs required by the pipeline.
- Missing local artifact or output directories are not blockers before preflight. The main orchestrator must create them before the first child handoff; block only if creation fails.

### Scheduled Automation External Access

Scheduled Codex automation may have restricted DNS or external network access. If this workflow needs Slack delivery, GitHub API reads, GitHub raw file reads, or similar external integration during a scheduled run, the orchestrator must not call those services directly from the automation runtime.

Use the LaunchAgent-backed external access bridge instead:

- Bridge helper: `{EXTERNAL_ACCESS_BRIDGE}`
- Project-local bridge dir: `{bridge_dir}`
- Install or refresh the user-session LaunchAgent from an interactive Codex or Terminal session:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} install-launchagent`
- Preflight the request bridge through LaunchAgent:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request preflight`
- Send Slack messages from scheduled automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request slack-post --channel <CHANNEL_ID> --text <MESSAGE>`
- Read GitHub API or allowed GitHub HTTPS URLs from scheduled automation:
  `python3 {EXTERNAL_ACCESS_BRIDGE} --bridge-dir {bridge_dir} request github-get --api-path /repos/<owner>/<repo> --output <path>`

The bridge must use secrets only from `~/Workspace/command-center/secrets/...` or environment overrides. Never put tokens in role files, pipeline files, `AGENTS.md`, generated prompts, or automation prompts.

The scheduled automation run must never call `install-launchagent`. `install-launchagent` is setup-only and registers a demand-start LaunchAgent with `RunAtLoad = false` and `KeepAlive = false`. Scheduled automation uses `request ...`: the helper writes a request JSON, kickstarts the already-installed LaunchAgent, waits for a response, and then the LaunchAgent exits. If the LaunchAgent is not already installed or loaded, record a blocker with owner and next action.

If the bridge preflight fails, record the blocker, owner, next action, and the artifact that still needs delivery. Do not silently fall back to direct scheduled-runtime Slack or GitHub calls.

### Auto-Handoff Mode

- When the user asks to start or continue the configured workflow, the main orchestrator must run automatic handoff by default.
- After each child agent finishes one move, the main orchestrator must:
  1. Read the full shared pipeline file at `{pipeline_path}`.
  2. Detect the latest `HANDOFF: ...` marker when the pipeline uses that convention.
  3. Route the next move to the addressed project subagent from the main orchestrator thread.
  4. Repeat until a terminal condition is reached, the user stops the workflow, or the max-turn limit is hit.
- Child agents must not directly continue each other's threads. All handoffs go through the main orchestrator.
- If a child move advances the pipeline and no blocker is present, the orchestrator must continue the next handoff automatically without waiting for user reminder.
- Unless the user explicitly overrides it for a run, use a safety cap of `{max_handoff_turns}` handoff turns, report when it is reached, and ask whether to continue.
- If a child agent asks a blocking user-facing question, stop the auto-handoff loop and relay that question in the main chat before continuing.

### User Question Relay

- If a subagent needs clarification or a decision from the user without which it cannot continue or finalize safely, the orchestrator must surface that question in the main chat immediately.
- This rule is especially strict for the architect role: if the architect asks a question at the beginning or end of its move, the orchestrator must relay it to the user and must not leave it only in the architect subagent thread.
- When a child agent emits a `USER QUESTION:` section, the orchestrator must copy the question into the main chat, explain that the workflow is paused on user input, and wait for the answer.

{MANAGED_END}
"""


def update_agents_md(path: Path, block: str) -> tuple[str, bool]:
    if path.exists():
        original = path.read_text(encoding="utf-8")
        pattern = re.compile(
            rf"{re.escape(MANAGED_BEGIN)}.*?{re.escape(MANAGED_END)}\n?",
            re.DOTALL,
        )
        if pattern.search(original):
            updated = pattern.sub(block.rstrip() + "\n", original)
            return updated, True
        prefix = original.rstrip()
        if prefix:
            updated = prefix + "\n\n" + block.rstrip() + "\n"
        else:
            updated = block.rstrip() + "\n"
        return updated, False

    fresh = "# Project Instructions\n\n" + block.rstrip() + "\n"
    return fresh, False


def write_setup(
    project_root: Path,
    pipeline_path: Path,
    pipeline_id: str,
    roles: list[RoleSpec],
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    orchestration_backend: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    written_paths: list[str] = []

    agents_dir = project_root / ".codex" / "agents"
    orchestration_dir = project_root / ".codex" / "orchestration"
    prompts_dir = project_root / ".codex" / "prompts"
    agents_md_path = project_root / "AGENTS.md"
    prompt_name = "subagent-init.md" if orchestration_backend == "subagents" else "thread-orchestration.md"
    prompt_path = prompts_dir / prompt_name

    prompts_dir.mkdir(parents=True, exist_ok=True)

    thread_creation_requests: list[dict[str, str]] = []
    registry_path: Path | None = None
    shared_registry_path: Path | None = None
    reused_role_threads: list[dict[str, str]] = []
    if orchestration_backend == "subagents":
        agents_dir.mkdir(parents=True, exist_ok=True)
        for role in roles:
            agent_path = agents_dir / f"{role.slug}.toml"
            agent_path.write_text(
                build_agent_toml(role, pipeline_path, reasoning_level),
                encoding="utf-8",
            )
            written_paths.append(str(agent_path))
    else:
        orchestration_dir.mkdir(parents=True, exist_ok=True)
        role_prompts_dir = prompts_dir / "thread-roles"
        role_prompts_dir.mkdir(parents=True, exist_ok=True)
        existing_role_threads = existing_role_threads_by_id(project_root)
        existing_thread_ids: dict[str, str] = {}
        for role in roles:
            existing = existing_role_threads.get(role.role_id, {})
            thread_id = existing.get("thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                existing_thread_ids[role.role_id] = thread_id.strip()
                reused_role_threads.append(
                    {
                        "role_id": role.role_id,
                        "display_name": role.display_name,
                        "thread_title": f"agent:{role.role_id}",
                        "thread_id": thread_id.strip(),
                    }
                )

        registry_path = pipeline_registry_path(project_root, pipeline_id)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        shared_registry_path = role_registry_path(project_root)
        registry = build_threads_registry(
            roles,
            pipeline_path,
            pipeline_id,
            project_root,
            reasoning_level,
            max_handoff_turns,
            prompt_mode,
            existing_thread_ids,
        )
        registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        written_paths.append(str(registry_path))
        shared_registry = build_project_role_threads_registry(
            project_root,
            roles,
            existing_thread_ids,
            existing_role_threads,
        )
        shared_registry_path.write_text(json.dumps(shared_registry, indent=2) + "\n", encoding="utf-8")
        written_paths.append(str(shared_registry_path))

        for role in roles:
            if role.role_id in existing_thread_ids:
                continue
            role_prompt = build_thread_role_prompt(
                role,
                pipeline_path,
                pipeline_id,
                project_root,
                reasoning_level,
                max_handoff_turns,
                prompt_mode,
            )
            role_prompt_path = role_prompts_dir / f"{role.slug}.md"
            role_prompt_path.write_text(role_prompt, encoding="utf-8")
            written_paths.append(str(role_prompt_path))
            thread_creation_requests.append(
                {
                    "slug": role.slug,
                    "role_id": role.role_id,
                    "display_name": role.display_name,
                    "thread_title": f"agent:{role.role_id}",
                    "prompt_path": str(role_prompt_path),
                    "prompt": role_prompt,
                }
            )

    prompt_text = build_prompt_text(
        roles,
        pipeline_path,
        pipeline_id,
        project_root,
        reasoning_level,
        max_handoff_turns,
        prompt_mode,
        orchestration_backend,
    )
    prompt_path.write_text(prompt_text, encoding="utf-8")
    written_paths.append(str(prompt_path))

    agents_md_block = build_agents_md_block(
        roles,
        pipeline_path,
        pipeline_id,
        project_root,
        reasoning_level,
        max_handoff_turns,
        prompt_mode,
        orchestration_backend,
    )
    agents_md_content, replaced_managed_block = update_agents_md(agents_md_path, agents_md_block)
    agents_md_path.write_text(agents_md_content, encoding="utf-8")
    written_paths.append(str(agents_md_path))

    if replaced_managed_block:
        warnings.append("refreshed an existing managed orchestration block in AGENTS.md")

    return {
        "ok": True,
        "project_root": str(project_root),
        "pipeline_path": str(pipeline_path),
        "pipeline_id": pipeline_id,
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "prompt_mode": prompt_mode,
        "orchestration_backend": orchestration_backend,
        "agent_names": [role.slug for role in roles],
        "roles": [
            {
                "slug": role.slug,
                "role_id": role.role_id,
                "display_name": role.display_name,
                "path": str(role.path),
                "thread_title": f"agent:{role.role_id}",
            }
            for role in roles
        ],
        "agents_md_path": str(agents_md_path),
        "prompt_path": str(prompt_path),
        "prompt_text": prompt_text,
        "threads_registry_path": str(registry_path) if registry_path else None,
        "role_threads_registry_path": str(shared_registry_path) if shared_registry_path else None,
        "reused_role_threads": reused_role_threads,
        "thread_creation_requests": thread_creation_requests,
        "written_paths": written_paths,
        "warnings": warnings,
    }


def register_threads(
    project_root: Path,
    pipeline_path: Path,
    pipeline_id: str,
    roles: list[RoleSpec],
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing_role_threads = existing_role_threads_by_id(project_root)
    existing_thread_ids = {
        role_id: item["thread_id"].strip()
        for role_id, item in existing_role_threads.items()
        if isinstance(item.get("thread_id"), str) and item["thread_id"].strip()
    }
    thread_ids = extract_thread_ids(payload, roles, existing_thread_ids)
    orchestration_dir = project_root / ".codex" / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)
    registry_path = pipeline_registry_path(project_root, pipeline_id)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    shared_registry_path = role_registry_path(project_root)
    registry = build_threads_registry(
        roles,
        pipeline_path,
        pipeline_id,
        project_root,
        reasoning_level,
        max_handoff_turns,
        prompt_mode,
        thread_ids,
    )
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    shared_registry = build_project_role_threads_registry(
        project_root,
        roles,
        thread_ids,
        existing_role_threads,
    )
    shared_registry_path.write_text(json.dumps(shared_registry, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "project_root": str(project_root),
        "pipeline_path": str(pipeline_path),
        "pipeline_id": pipeline_id,
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "prompt_mode": prompt_mode,
        "orchestration_backend": "threads",
        "threads_registry_path": str(registry_path),
        "role_threads_registry_path": str(shared_registry_path),
        "role_threads": [
            {
                "slug": role.slug,
                "role_id": role.role_id,
                "display_name": role.display_name,
                "thread_title": f"agent:{role.role_id}",
                "thread_id": thread_ids[role.slug],
            }
            for role in roles
        ],
        "written_paths": [str(registry_path), str(shared_registry_path)],
        "warnings": [],
    }


def doctor(
    project_root: Path,
    pipeline_path: Path,
    pipeline_id: str,
    roles: list[RoleSpec],
    reasoning_level: str,
    max_handoff_turns: int,
    prompt_mode: str,
    orchestration_backend: str,
    warnings: list[str],
) -> dict[str, Any]:
    if orchestration_backend == "subagents":
        planned_paths = [
            str(project_root / ".codex" / "prompts" / "subagent-init.md"),
            str(project_root / "AGENTS.md"),
        ]
        planned_paths.extend(str(project_root / ".codex" / "agents" / f"{role.slug}.toml") for role in roles)
    else:
        planned_paths = [
            str(role_registry_path(project_root)),
            str(pipeline_registry_path(project_root, pipeline_id)),
            str(project_root / ".codex" / "prompts" / "thread-orchestration.md"),
            str(project_root / "AGENTS.md"),
        ]
        planned_paths.extend(
            str(project_root / ".codex" / "prompts" / "thread-roles" / f"{role.slug}.md")
            for role in roles
        )

    return {
        "ok": True,
        "project_root": str(project_root),
        "pipeline_path": str(pipeline_path),
        "pipeline_id": pipeline_id,
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "prompt_mode": prompt_mode,
        "orchestration_backend": orchestration_backend,
        "agent_names": [role.slug for role in roles],
        "roles": [
            {
                "slug": role.slug,
                "role_id": role.role_id,
                "display_name": role.display_name,
                "path": str(role.path),
                "thread_title": f"agent:{role.role_id}",
            }
            for role in roles
        ],
        "planned_paths": planned_paths,
        "thread_title_rule": "agent:<role_id>",
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Codex project orchestration files.")
    parser.add_argument("command", choices=("doctor", "setup", "register-threads"))
    parser.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin.")
    args = parser.parse_args()

    try:
        if not args.stdin:
            raise ValueError("use --stdin and pass a JSON payload through stdin")
        payload = read_payload_from_stdin()
        (
            project_root,
            pipeline_path,
            pipeline_id,
            roles,
            reasoning_level,
            max_handoff_turns,
            prompt_mode,
            orchestration_backend,
            warnings,
        ) = validate_payload(payload)
        if args.command == "doctor":
            result = doctor(
                project_root,
                pipeline_path,
                pipeline_id,
                roles,
                reasoning_level,
                max_handoff_turns,
                prompt_mode,
                orchestration_backend,
                warnings,
            )
        elif args.command == "register-threads":
            if orchestration_backend != "threads":
                raise ValueError("register-threads requires orchestration_backend='threads'")
            result = register_threads(
                project_root,
                pipeline_path,
                pipeline_id,
                roles,
                reasoning_level,
                max_handoff_turns,
                prompt_mode,
                payload,
            )
            result["warnings"] = warnings + result.get("warnings", [])
        else:
            result = write_setup(
                project_root,
                pipeline_path,
                pipeline_id,
                roles,
                reasoning_level,
                max_handoff_turns,
                prompt_mode,
                orchestration_backend,
            )
            result["warnings"] = warnings + result.get("warnings", [])
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
