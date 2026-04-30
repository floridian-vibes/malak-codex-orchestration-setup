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


@dataclass
class RoleSpec:
    slug: str
    display_name: str
    path: Path


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


def derive_roles(role_paths: list[Path]) -> tuple[list[RoleSpec], list[str]]:
    roles: list[RoleSpec] = []
    warnings: list[str] = []
    used: dict[str, int] = {}

    for role_path in role_paths:
        base_slug = slugify(role_path.stem)
        count = used.get(base_slug, 0)
        used[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"
        if slug != base_slug:
            warnings.append(
                f"role slug collision for '{base_slug}', created '{slug}' for {role_path}"
            )
        title = markdown_title(role_path) or role_path.stem.replace("-", " ").replace("_", " ").title()
        roles.append(RoleSpec(slug=slug, display_name=title, path=role_path))

    return roles, warnings


def validate_payload(payload: dict[str, Any]) -> tuple[Path, Path, list[RoleSpec], str, int, list[str]]:
    raw_project_root = payload.get("project_root")
    if isinstance(raw_project_root, str) and raw_project_root.strip():
        project_root = resolve_path(raw_project_root, "project_root")
    else:
        project_root = Path.cwd().resolve()
    pipeline_path = resolve_path(payload.get("pipeline_path"), "pipeline_path")
    raw_role_paths = payload.get("role_paths")
    if not isinstance(raw_role_paths, list) or not raw_role_paths:
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

    role_paths: list[Path] = []
    for index, raw_role_path in enumerate(raw_role_paths, start=1):
        role_path = resolve_path(raw_role_path, f"role_paths[{index}]")
        role_paths.append(role_path)

    errors: list[str] = []
    if not project_root.exists():
        errors.append(f"project_root does not exist: {project_root}")
    elif not project_root.is_dir():
        errors.append(f"project_root is not a directory: {project_root}")

    if not pipeline_path.exists():
        errors.append(f"pipeline_path does not exist: {pipeline_path}")
    elif not pipeline_path.is_file():
        errors.append(f"pipeline_path is not a file: {pipeline_path}")

    for role_path in role_paths:
        if not role_path.exists():
            errors.append(f"role path does not exist: {role_path}")
        elif not role_path.is_file():
            errors.append(f"role path is not a file: {role_path}")

    if errors:
        raise ValueError("; ".join(errors))

    roles, warnings = derive_roles(role_paths)
    return project_root, pipeline_path, roles, reasoning_level, max_handoff_turns, warnings


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
    reasoning_level: str,
    max_handoff_turns: int,
) -> str:
    role_names = ", ".join(role.slug for role in roles)
    role_lines = "\n".join(f"- `{role.slug}`: `{role.path}`" for role in roles)
    return f"""Use these configured project subagents: {role_names}.

Core rules:
- You are the main orchestrator only. Never do the substantive work of any child role yourself.
- Default mode: if I give a task, pass it unchanged to the role that should act next under `{pipeline_path}`.
- Exception: only treat my message as an orchestration request when I explicitly ask about routing, handoff, pause/resume, limits, role choice, or fixing the workflow.
- All handoffs go through the main orchestrator thread; child threads must not continue each other directly.
- When a child move advances the pipeline, reread `{pipeline_path}`, detect the latest `HANDOFF: ...` marker when used, and route the next move automatically without waiting for my reminder.
- Pause only for a terminal condition, a safety-cap hit, or a blocking `USER QUESTION:`. Surface blocking user questions in the main chat immediately, especially from the architect.
- Use reasoning `{reasoning_level}` unless I override it. Use a safety cap of `{max_handoff_turns}` unless I override it for this run.

Initialization task:
1. Spawn all configured agents once.
2. Have each agent read its role file and the shared pipeline, then report:
   - mission
   - expected inputs
   - expected outputs
   - any immediate `USER QUESTION:`
3. Return a consolidated readiness report, then wait for my first task.

Configured roles:
{role_lines}

Shared pipeline:
- `{pipeline_path}`
"""


def build_agents_md_block(
    roles: list[RoleSpec],
    pipeline_path: Path,
    reasoning_level: str,
    max_handoff_turns: int,
) -> str:
    role_lines = "\n".join(f"- `{role.slug}`: `{role.path}`" for role in roles)
    return f"""{MANAGED_BEGIN}
## Codex Subagent Workflow

This project uses project-local Codex subagents defined under `.codex/agents/`.
The role markdown files and the shared pipeline remain at their original source paths and must not be copied into the project.

### Source Of Truth

- Shared pipeline: `{pipeline_path}`
- Default reasoning level: `{reasoning_level}`
- Default max handoff turns: `{max_handoff_turns}`

### Role Files

{role_lines}

### Orchestration Rules

- Use the project-local agent definitions under `.codex/agents/` when the user asks for the configured workflow.
- The main chat is the orchestrator. Child agents report back to the main thread for handoff.
- The main orchestrator must not perform the substantive work of the configured child roles; it may only orchestrate, route, summarize, and relay according to the pipeline.
- Ordinary user tasks must be passed to the next role per pipeline in the form the user wrote them, unless the user is explicitly asking an orchestration question or issuing an orchestration command.
- Keep separate agent threads so the user can intervene manually in a specific role thread.
- Follow the shared pipeline file for sequencing, dependencies, and handoff expectations.
- If a source role file or the pipeline changes, reread it from the original path instead of duplicating it.
- The standard initialization prompt lives at `.codex/prompts/subagent-init.md`.

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
    roles: list[RoleSpec],
    reasoning_level: str,
    max_handoff_turns: int,
) -> dict[str, Any]:
    warnings: list[str] = []
    written_paths: list[str] = []

    agents_dir = project_root / ".codex" / "agents"
    prompts_dir = project_root / ".codex" / "prompts"
    agents_md_path = project_root / "AGENTS.md"
    prompt_path = prompts_dir / "subagent-init.md"

    agents_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    for role in roles:
        agent_path = agents_dir / f"{role.slug}.toml"
        agent_path.write_text(
            build_agent_toml(role, pipeline_path, reasoning_level),
            encoding="utf-8",
        )
        written_paths.append(str(agent_path))

    prompt_text = build_prompt_text(roles, pipeline_path, reasoning_level, max_handoff_turns)
    prompt_path.write_text(prompt_text, encoding="utf-8")
    written_paths.append(str(prompt_path))

    agents_md_block = build_agents_md_block(
        roles,
        pipeline_path,
        reasoning_level,
        max_handoff_turns,
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
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "agent_names": [role.slug for role in roles],
        "roles": [
            {
                "slug": role.slug,
                "display_name": role.display_name,
                "path": str(role.path),
            }
            for role in roles
        ],
        "agents_md_path": str(agents_md_path),
        "prompt_path": str(prompt_path),
        "prompt_text": prompt_text,
        "written_paths": written_paths,
        "warnings": warnings,
    }


def doctor(
    project_root: Path,
    pipeline_path: Path,
    roles: list[RoleSpec],
    reasoning_level: str,
    max_handoff_turns: int,
    warnings: list[str],
) -> dict[str, Any]:
    planned_paths = [
        str(project_root / ".codex" / "prompts" / "subagent-init.md"),
        str(project_root / "AGENTS.md"),
    ]
    planned_paths.extend(str(project_root / ".codex" / "agents" / f"{role.slug}.toml") for role in roles)

    return {
        "ok": True,
        "project_root": str(project_root),
        "pipeline_path": str(pipeline_path),
        "reasoning_level": reasoning_level,
        "max_handoff_turns": max_handoff_turns,
        "agent_names": [role.slug for role in roles],
        "roles": [
            {
                "slug": role.slug,
                "display_name": role.display_name,
                "path": str(role.path),
            }
            for role in roles
        ],
        "planned_paths": planned_paths,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Codex project orchestration files.")
    parser.add_argument("command", choices=("doctor", "setup"))
    parser.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin.")
    args = parser.parse_args()

    try:
        if not args.stdin:
            raise ValueError("use --stdin and pass a JSON payload through stdin")
        payload = read_payload_from_stdin()
        (
            project_root,
            pipeline_path,
            roles,
            reasoning_level,
            max_handoff_turns,
            warnings,
        ) = validate_payload(payload)
        if args.command == "doctor":
            result = doctor(
                project_root,
                pipeline_path,
                roles,
                reasoning_level,
                max_handoff_turns,
                warnings,
            )
        else:
            result = write_setup(
                project_root,
                pipeline_path,
                roles,
                reasoning_level,
                max_handoff_turns,
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
