#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path


SKILL_SLUG = "malak-codex-orchestration-setup"
LAUNCHAGENT_LABEL = "com.malak.codex-orchestration.external-access"
STATE_ROOT = Path(
    os.environ.get(
        "MALAK_CODEX_ORCH_BRIDGE_DIR",
        f"{Path.home()}/Workspace/command-center/{SKILL_SLUG}/external-bridge",
    )
).expanduser()
REQUESTS_DIR = STATE_ROOT / "requests"
RESPONSES_DIR = STATE_ROOT / "responses"
LOG_DIR = STATE_ROOT / "logs"
PID_PATH = STATE_ROOT / "daemon.pid"
DEFAULT_SLACK_ENV = Path(
    os.environ.get(
        "MALAK_CODEX_ORCH_SLACK_ENV",
        f"{Path.home()}/Workspace/command-center/secrets/slack-pulse-ai-bot.env",
    )
).expanduser()
DEFAULT_GITHUB_ENV = Path(
    os.environ.get(
        "MALAK_CODEX_ORCH_GITHUB_ENV",
        f"{Path.home()}/Workspace/command-center/secrets/{SKILL_SLUG}/github.env",
    )
).expanduser()
ALLOWED_GITHUB_HOSTS = {"api.github.com", "raw.githubusercontent.com", "github.com"}


def configure_state_root(path: Path) -> None:
    global STATE_ROOT, REQUESTS_DIR, RESPONSES_DIR, LOG_DIR, PID_PATH
    STATE_ROOT = path.expanduser().resolve()
    REQUESTS_DIR = STATE_ROOT / "requests"
    RESPONSES_DIR = STATE_ROOT / "responses"
    LOG_DIR = STATE_ROOT / "logs"
    PID_PATH = STATE_ROOT / "daemon.pid"


def helper_python() -> str:
    return shutil.which("python3") or sys.executable or "/usr/bin/python3"


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_process(argv: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env[key] = value
    return env


def private_env_summary(path: Path, keys: list[str]) -> dict:
    env = load_env(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "keys_present": {key: bool(env.get(key)) for key in keys},
    }


def http_request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, str], str]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", errors="replace")


def launchagent_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHAGENT_LABEL}.plist"


def launchctl_service_name() -> str:
    return f"gui/{os.getuid()}/{LAUNCHAGENT_LABEL}"


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def daemon_status() -> dict:
    if not PID_PATH.exists():
        return {"running": False, "pid": None, "daemon_root": str(STATE_ROOT)}
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return {"running": False, "pid": None, "daemon_root": str(STATE_ROOT)}
    return {"running": pid_is_running(pid), "pid": pid, "daemon_root": str(STATE_ROOT)}


def launchagent_payload() -> dict:
    script_path = Path(__file__).resolve()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "Label": LAUNCHAGENT_LABEL,
        "ProgramArguments": [
            helper_python(),
            str(script_path),
            "daemon",
        ],
        "RunAtLoad": True,
        "KeepAlive": False,
        "EnvironmentVariables": {
            "MALAK_CODEX_ORCH_BRIDGE_DIR": str(STATE_ROOT),
            "MALAK_CODEX_ORCH_SLACK_ENV": str(DEFAULT_SLACK_ENV),
            "MALAK_CODEX_ORCH_GITHUB_ENV": str(DEFAULT_GITHUB_ENV),
        },
        "StandardOutPath": str(LOG_DIR / "launchagent.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchagent.err.log"),
    }


def ensure_launchagent_loaded() -> dict:
    plist_path = launchagent_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = launchagent_payload()
    existing = None
    if plist_path.exists():
        try:
            existing = plistlib.loads(plist_path.read_bytes())
        except Exception:
            existing = None
    if existing != payload:
        plist_path.write_bytes(plistlib.dumps(payload, sort_keys=False))

    service = launchctl_service_name()
    loaded = False
    try:
        run_process(["launchctl", "print", service], timeout=10)
        loaded = True
    except Exception:
        loaded = False
    if not loaded:
        run_process(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], timeout=20)
    run_process(["launchctl", "kickstart", "-k", service], timeout=20)
    return {
        "label": LAUNCHAGENT_LABEL,
        "plist": str(plist_path),
        "daemon_root": str(STATE_ROOT),
        "loaded": True,
    }


def submit_daemon_request(
    argv: list[str],
    timeout: float | None = None,
    *,
    slack_env: Path | None = None,
    github_env: Path | None = None,
) -> dict:
    if not argv:
        raise RuntimeError("No bridge command provided")
    if argv[0] in {"daemon", "via-daemon", "install-launchagent", "start-daemon", "stop-daemon"}:
        raise RuntimeError(f"Refusing to run {argv[0]} through the daemon")
    status = daemon_status()
    launchagent = None
    if not status["running"]:
        launchagent = ensure_launchagent_loaded()
    request_id = uuid.uuid4().hex
    timeout = timeout or 120.0
    request_path = REQUESTS_DIR / f"{request_id}.json"
    response_path = RESPONSES_DIR / f"{request_id}.json"
    request = {
        "id": request_id,
        "created_at": datetime.now().isoformat(),
        "cwd": os.getcwd(),
        "argv": argv,
        "timeout": timeout,
        "env": {
            "MALAK_CODEX_ORCH_BRIDGE_DIR": str(STATE_ROOT),
            "MALAK_CODEX_ORCH_SLACK_ENV": str((slack_env or DEFAULT_SLACK_ENV).expanduser()),
            "MALAK_CODEX_ORCH_GITHUB_ENV": str((github_env or DEFAULT_GITHUB_ENV).expanduser()),
        },
    }
    write_json_atomic(request_path, request)

    deadline = time.monotonic() + timeout + 30.0
    while time.monotonic() <= deadline:
        if response_path.exists():
            response = read_json(response_path)
            response["daemon_status"] = daemon_status()
            if launchagent:
                response["launchagent"] = launchagent
            return response
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for external access daemon response for request {request_id}")


def cmd_install_launchagent(_args: argparse.Namespace) -> int:
    result = ensure_launchagent_loaded()
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


def cmd_start_daemon(args: argparse.Namespace) -> int:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    status = daemon_status()
    if status["running"]:
        if not args.restart:
            print(json.dumps({"ok": True, **status}, ensure_ascii=False))
            return 0
        try:
            os.kill(int(status["pid"]), 15)
            time.sleep(0.5)
        except Exception:
            pass
    env = os.environ.copy()
    env.update(
        {
            "MALAK_CODEX_ORCH_BRIDGE_DIR": str(STATE_ROOT),
            "MALAK_CODEX_ORCH_SLACK_ENV": str(DEFAULT_SLACK_ENV),
            "MALAK_CODEX_ORCH_GITHUB_ENV": str(DEFAULT_GITHUB_ENV),
        }
    )
    stdout = (LOG_DIR / "interactive.out.log").open("ab")
    stderr = (LOG_DIR / "interactive.err.log").open("ab")
    proc = subprocess.Popen(
        [helper_python(), str(Path(__file__).resolve()), "daemon"],
        cwd=os.getcwd(),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10.0
    while time.monotonic() <= deadline:
        status = daemon_status()
        if status["running"] and status["pid"] == proc.pid:
            print(json.dumps({"ok": True, **status}, ensure_ascii=False))
            return 0
        if proc.poll() is not None:
            raise RuntimeError(f"Daemon exited early with code {proc.returncode}")
        time.sleep(0.2)
    raise RuntimeError("Daemon did not write a running pid file")


def cmd_stop_daemon(_args: argparse.Namespace) -> int:
    status = daemon_status()
    stopped = False
    if status["running"]:
        os.kill(int(status["pid"]), 15)
        stopped = True
        time.sleep(0.5)
    if PID_PATH.exists() and not daemon_status()["running"]:
        PID_PATH.unlink()
    print(json.dumps({"ok": True, "stopped": stopped, **status}, ensure_ascii=False))
    return 0


def cmd_via_daemon(args: argparse.Namespace) -> int:
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    response = submit_daemon_request(
        argv,
        timeout=args.timeout,
        slack_env=args.slack_env,
        github_env=args.github_env,
    )
    stdout = response.get("stdout") or ""
    stderr = response.get("stderr") or ""
    returncode = int(response.get("returncode", 1))
    if stdout:
        print(stdout)
    else:
        print(json.dumps(response, ensure_ascii=False))
    if returncode != 0 and not stdout and stderr:
        print(stderr, file=sys.stderr)
    return returncode


def cmd_daemon(_args: argparse.Namespace) -> int:
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    script_path = Path(__file__).resolve()
    try:
        while True:
            for request_path in sorted(REQUESTS_DIR.glob("*.json")):
                processing_path = request_path.with_suffix(".processing")
                try:
                    request_path.rename(processing_path)
                except OSError:
                    continue
                response = {
                    "id": processing_path.stem,
                    "ok": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "",
                }
                try:
                    request = read_json(processing_path)
                    argv = request.get("argv") or []
                    timeout = float(request.get("timeout") or 120.0)
                    child_env = os.environ.copy()
                    child_env.update(request.get("env") or {})
                    proc = subprocess.run(
                        [helper_python(), str(script_path), *argv],
                        cwd=request.get("cwd") or str(Path.home()),
                        text=True,
                        capture_output=True,
                        timeout=timeout,
                        env=child_env,
                    )
                    response.update(
                        {
                            "id": request.get("id", processing_path.stem),
                            "ok": proc.returncode == 0,
                            "returncode": proc.returncode,
                            "stdout": proc.stdout.strip(),
                            "stderr": proc.stderr.strip(),
                            "argv": argv,
                            "finished_at": datetime.now().isoformat(),
                        }
                    )
                    if response["stdout"]:
                        try:
                            response["parsed_stdout"] = json.loads(response["stdout"])
                        except Exception:
                            pass
                except Exception as exc:
                    response.update(
                        {
                            "ok": False,
                            "returncode": 1,
                            "stderr": str(exc),
                            "finished_at": datetime.now().isoformat(),
                        }
                    )
                finally:
                    response_id = response.get("id", processing_path.stem)
                    write_json_atomic(RESPONSES_DIR / f"{response_id}.json", response)
                    try:
                        processing_path.unlink()
                    except FileNotFoundError:
                        pass
            time.sleep(0.5)
    finally:
        try:
            if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink()
        except Exception:
            pass


def cmd_preflight(args: argparse.Namespace) -> int:
    checks: dict[str, object] = {
        "state_dir": str(STATE_ROOT),
        "state_dir_writable": False,
        "slack_env": private_env_summary(args.slack_env, ["SLACK_BOT_TOKEN"]),
        "github_env": private_env_summary(args.github_env, ["GITHUB_TOKEN", "GH_TOKEN"]),
    }
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        probe = STATE_ROOT / f".write-test-{os.getpid()}-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["state_dir_writable"] = True
    except Exception as exc:
        checks["state_dir_error"] = str(exc)

    for host in ("slack.com", "api.github.com"):
        try:
            socket.getaddrinfo(host, 443)
            checks[f"dns_{host}"] = True
        except Exception as exc:
            checks[f"dns_{host}"] = False
            checks[f"dns_{host}_error"] = str(exc)

    try:
        status, _headers, body = http_request_json(
            "https://slack.com/api/api.test",
            headers={"User-Agent": "malak-codex-orchestration-setup/1.0"},
            timeout=15.0,
        )
        checks["slack_https"] = 200 <= status < 500 and bool(body)
    except Exception as exc:
        checks["slack_https"] = False
        checks["slack_https_error"] = str(exc)

    try:
        headers = github_headers(args.github_env)
        status, _headers, body = http_request_json(
            "https://api.github.com/rate_limit",
            headers=headers,
            timeout=15.0,
        )
        checks["github_https"] = 200 <= status < 500 and bool(body)
    except Exception as exc:
        checks["github_https"] = False
        checks["github_https_error"] = str(exc)

    required = ["state_dir_writable", "dns_slack.com", "dns_api.github.com", "slack_https", "github_https"]
    ok = all(checks.get(key) is True for key in required)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def slack_token(slack_env: Path) -> str:
    env = load_env(slack_env)
    token = env.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(f"Missing SLACK_BOT_TOKEN in {slack_env} or process environment")
    return token


def cmd_slack_post(args: argparse.Namespace) -> int:
    token = slack_token(args.slack_env)
    payload = {
        "channel": args.channel,
        "text": args.text,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if args.thread_ts:
        payload["thread_ts"] = args.thread_ts
    status, _headers, body = http_request_json(
        "https://slack.com/api/chat.postMessage",
        method="POST",
        payload=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "malak-codex-orchestration-setup/1.0",
        },
        timeout=30.0,
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"ok": False, "raw_body": body[:500]}
    if status >= 400 or not parsed.get("ok"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": status,
                    "slack_error": parsed.get("error"),
                    "channel": args.channel,
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "channel": parsed.get("channel"),
                "ts": parsed.get("ts"),
                "message": {"text_length": len(args.text)},
            },
            ensure_ascii=False,
        )
    )
    return 0


def github_headers(github_env: Path) -> dict[str, str]:
    env = load_env(github_env)
    token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "malak-codex-orchestration-setup/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def normalize_github_url(api_path: str | None, url: str | None) -> str:
    if api_path:
        path = api_path if api_path.startswith("/") else f"/{api_path}"
        return f"https://api.github.com{path}"
    if not url:
        raise RuntimeError("Either --api-path or --url is required")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_GITHUB_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_GITHUB_HOSTS))
        raise RuntimeError(f"Only https GitHub URLs are allowed; allowed hosts: {allowed}")
    return url


def cmd_github_get(args: argparse.Namespace) -> int:
    url = normalize_github_url(args.api_path, args.url)
    status, headers, body = http_request_json(
        url,
        headers=github_headers(args.github_env),
        timeout=args.timeout,
    )
    result = {
        "ok": 200 <= status < 300,
        "status": status,
        "url": url,
        "rate_limit_remaining": headers.get("x-ratelimit-remaining"),
        "bytes": len(body.encode("utf-8")),
    }
    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
        result["output"] = str(output_path)
    else:
        result["body"] = body[: args.max_inline_bytes]
        result["truncated"] = len(body.encode("utf-8")) > args.max_inline_bytes
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex orchestration external access bridge")
    parser.add_argument("--bridge-dir", type=Path, default=STATE_ROOT)
    parser.add_argument("--slack-env", type=Path, default=DEFAULT_SLACK_ENV)
    parser.add_argument("--github-env", type=Path, default=DEFAULT_GITHUB_ENV)
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight")
    preflight.set_defaults(func=cmd_preflight)

    install_agent = sub.add_parser("install-launchagent")
    install_agent.set_defaults(func=cmd_install_launchagent)

    start_daemon = sub.add_parser("start-daemon")
    start_daemon.add_argument("--restart", action="store_true")
    start_daemon.set_defaults(func=cmd_start_daemon)

    stop_daemon = sub.add_parser("stop-daemon")
    stop_daemon.set_defaults(func=cmd_stop_daemon)

    via_daemon = sub.add_parser("via-daemon")
    via_daemon.add_argument("--timeout", type=float)
    via_daemon.add_argument("argv", nargs=argparse.REMAINDER)
    via_daemon.set_defaults(func=cmd_via_daemon)

    daemon = sub.add_parser("daemon")
    daemon.set_defaults(func=cmd_daemon)

    slack_post = sub.add_parser("slack-post")
    slack_post.add_argument("--channel", required=True)
    slack_post.add_argument("--text", required=True)
    slack_post.add_argument("--thread-ts")
    slack_post.set_defaults(func=cmd_slack_post)

    github_get = sub.add_parser("github-get")
    github_get.add_argument("--api-path")
    github_get.add_argument("--url")
    github_get.add_argument("--output", type=Path)
    github_get.add_argument("--timeout", type=float, default=30.0)
    github_get.add_argument("--max-inline-bytes", type=int, default=4000)
    github_get.set_defaults(func=cmd_github_get)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        configure_state_root(args.bridge_dir)
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
