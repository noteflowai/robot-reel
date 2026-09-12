#!/usr/bin/env python3
"""Launch coding agents in separate Git worktrees and tmux windows."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tomllib

NAMES = ("kiro", "codex", "claude")
# A pane whose foreground is one of these and which has no child process is the
# shell the launcher leaves behind after an agent exits, so it is safe to reuse.
SHELLS = ("bash", "sh", "dash", "zsh", "ksh", "fish")
SANDBOX_MODES = ("configured", "read-only", "workspace-write", "danger-full-access")


class Error(Exception):
    pass


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True)
    if check and result.returncode:
        raise Error(result.stderr.strip() or result.stdout.strip() or shlex.join(args))
    return result


def git(*args, cwd=None):
    return run("git", "-C", str(cwd or Path.cwd()), *args).stdout.strip()


def repository(cwd):
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)).resolve()
    records = []
    record = {}
    # -z preserves spaces, newlines and non-ASCII paths without Git's quoting.
    for field in git("worktree", "list", "--porcelain", "-z", cwd=cwd).split("\0"):
        if not field:
            if record:
                records.append(record)
                record = {}
        else:
            key, _, value = field.partition(" ")
            record[key] = value
    if record:
        records.append(record)
    if not records or "bare" in records[0]:
        raise Error("a non-bare repository with a main checkout is required")
    main = Path(records[0]["worktree"]).resolve()
    if main == Path.home().resolve():
        raise Error("refusing to treat your home directory as a project")
    return common, main, {Path(r["worktree"]).resolve(): r for r in records}


def panes(session):
    result = run("tmux", "list-panes", "-s", "-t", "=" + session,
                 "-F", "#{window_id}\t#{window_name}\t#{pane_id}\t#{pane_pid}\t"
                       "#{pane_current_command}\t#{pane_current_path}",
                 check=False)
    if result.returncode:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 5)
        if len(parts) != 6:
            raise Error("unsupported tmux pane path")
        rows.append(dict(zip(("window", "name", "pane", "pid", "cmd", "path"), parts)))
    return rows


def session_exists(session):
    return run("tmux", "has-session", "-t", "=" + session, check=False).returncode == 0


def owns_session(session, common):
    rows = panes(session)
    if not rows:
        return False
    for row in rows:
        try:
            if repository(Path(row["path"]))[0] != common:
                return False
        except Error:
            return False
    return True


def process_tree(root_pid):
    """Read Linux process metadata, never environment variables or prompts."""
    table = {}
    for path in Path("/proc").glob("[0-9]*"):
        try:
            status = dict(line.split(":", 1) for line in (path / "status").read_text().splitlines()
                          if ":" in line)
            table[int(path.name)] = {
                "pid": int(path.name), "ppid": int(status["PPid"]),
                "uid": int(status["Uid"].split()[0]),
                "name": status["Name"].strip(), "exe": os.readlink(path / "exe"),
            }
        except (OSError, ValueError):
            pass
    ids = {int(root_pid)}
    while True:
        children = {pid for pid, item in table.items() if item["ppid"] in ids}
        if children <= ids:
            return [table[pid] for pid in sorted(ids) if pid in table and pid != int(root_pid)]
        ids |= children


def agent_processes(row):
    return [p for p in process_tree(row["pid"])
            if p["name"] in ("codex", "claude", "kiro-cli", "kiro-cli-chat")]


def sandbox_overrides(common, network, extra_roots=()):
    """Make Codex's workspace-write sandbox usable inside a linked worktree.

    workspace-write confines writes to declared roots. A worktree keeps its Git
    metadata in the main repository, so committing needs that path as well;
    without it `git commit` fails with a read-only filesystem. Preserve any
    additional roots explicitly selected in the user's configuration.
    """
    roots = list(dict.fromkeys([*extra_roots, str(common)]))
    overrides = ["-c", "sandbox_workspace_write.writable_roots="
                       + json.dumps(roots, ensure_ascii=False)]
    # Forward false as well as true: a resumed session must not retain an old
    # network grant after the user explicitly restricted its configuration.
    overrides += ["-c", "sandbox_workspace_write.network_access="+str(network).lower()]
    return overrides


def user_codex_config():
    root = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))).expanduser()
    path = root/"config.toml"
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Error(f"cannot read Codex user configuration {path}: {exc}") from exc


def codex_policy(requested, common, approvals, configuration=None):
    """Forward the user's choice on new and resumed sessions.

    Prompt approval and filesystem access are independent. Detecting a GPU
    never automatically selects a broader sandbox mode.
    """
    if requested not in SANDBOX_MODES:
        raise Error(f"unknown Codex sandbox choice: {requested}")
    config = user_codex_config() if configuration is None else configuration
    if requested == "configured":
        profile = config.get("default_permissions")
        if profile is not None:
            if not isinstance(profile, str) or not profile.strip():
                raise Error("Codex default_permissions must name a permissions profile")
            return {
                "label": f"user permission profile {profile}",
                "args": ["-c", "default_permissions="+json.dumps(profile, ensure_ascii=False), "--add-dir", str(common)],
                "mode": None,
            }
        mode = config.get("sandbox_mode")
        if mode is None:
            return {"label": "Codex configuration/default", "args": ["--add-dir", str(common)], "mode": None}
        if mode not in SANDBOX_MODES[1:]:
            raise Error("unsupported sandbox_mode in Codex user configuration")
        origin = "user configuration"
    else:
        mode, origin = requested, "explicit launcher option"
    args = ["--sandbox", mode]
    if mode == "workspace-write":
        workspace = config.get("sandbox_workspace_write", {})
        if not isinstance(workspace, dict):
            raise Error("sandbox_workspace_write must be a table")
        roots = workspace.get("writable_roots", [])
        network = workspace.get("network_access", approvals == "auto")
        if not isinstance(roots, list) or not all(isinstance(p, str) for p in roots) or type(network) is not bool:
            raise Error("invalid Codex workspace roots or network setting")
        args += sandbox_overrides(common, network=network, extra_roots=roots)
    return {"label": f"{mode} ({origin})", "args": args, "mode": mode}


def gpu_status():
    """Distinguish host GPU evidence from usable devices in this context."""
    models = []
    for path in sorted(Path("/proc/driver/nvidia/gpus").glob("*/information")):
        try:
            fields = dict(line.split(":", 1) for line in path.read_text().splitlines() if ":" in line)
            models.append(fields.get("Model", "NVIDIA GPU").strip())
        except OSError:
            pass
    nodes = {name: Path("/dev", name).exists() for name in ("nvidia0", "nvidiactl", "nvidia-uvm")}
    binary = shutil.which("nvidia-smi")
    result = None
    if binary and all(nodes.values()):
        try:
            result = subprocess.run(
                [binary, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    ready = result is not None and result.returncode == 0 and bool(result.stdout.strip())
    if ready:
        message = "accessible to launcher: " + ", ".join(result.stdout.strip().splitlines())
    elif models:
        missing = ", ".join(name for name, present in nodes.items() if not present)
        message = "host detected: " + ", ".join(models) + "; " + (
            "device nodes missing: " + missing if missing else "driver access check failed"
        )
    else:
        message = "no accessible NVIDIA GPU detected"
    return {"ready": ready, "message": message}


def command(agent, approvals, resume, common, policy=None):
    override = os.environ.get("AGENTS_CMD_" + agent.upper())
    if override:
        # Overrides are argv, not shell programs; quote paths containing spaces.
        argv = shlex.split(override)
        if resume:
            return None  # resume flags cannot be inferred for an explicit override
    else:
        argv = {
            "kiro": ["kiro-cli", "chat"],
            "codex": ["codex"],
            "claude": ["claude"],
        }[agent]
        if resume:
            argv += {"kiro": ["--resume"], "codex": ["resume", "--last"],
                     "claude": ["--continue"]}[agent]
        if approvals == "auto":
            argv += {
                "kiro": ["--trust-all-tools"],
                "codex": ["--ask-for-approval", "never"],
                "claude": ["--permission-mode", "bypassPermissions"],
            }[agent]
        else:
            argv += {
                "kiro": ["--trust-tools="],
                "codex": ["--ask-for-approval", "on-request"],
                "claude": ["--permission-mode", "default"],
            }[agent]
        if agent == "codex":
            argv += (policy or codex_policy("configured", common, approvals))["args"]
    if not argv:
        raise Error(f"empty command for {agent}")
    binary = shutil.which(argv[0])
    if not binary:
        raise Error(f"{agent}: executable not found: {argv[0]}")
    # Preserve the launcher symlink, e.g. Claude's version selector.
    argv[0] = os.path.abspath(binary)
    return argv


def validate_worktree(path, branch, common, records):
    if path not in records:
        if path.exists():
            raise Error(f"existing directory is not a registered worktree: {path}")
        return
    row = records[path]
    if row.get("branch") != "refs/heads/" + branch:
        raise Error(f"{path} is not on expected branch {branch}")
    if "locked" in row or "prunable" in row:
        raise Error(f"worktree is locked or unavailable: {path}")
    if not path.is_dir() or repository(path)[0] != common:
        raise Error(f"worktree belongs to another repository or is missing: {path}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Overrides: AGENTS_SESSION, AGENTS_LIST, AGENTS_BRANCH_PREFIX, "
               "AGENTS_WORKTREE_DIR, AGENTS_APPROVAL_MODE (auto/interactive), "
               "AGENTS_CODEX_SANDBOX, AGENTS_REQUIRE_GPU, "
               "AGENTS_CMD_KIRO/CODEX/CLAUDE (quoted argv, no shell operators). "
               "auto controls prompts; it does not select a Codex sandbox mode. "
               "Codex follows its user configuration unless --codex-sandbox is explicit. "
               "Full access removes enforced filesystem confinement; separate worktrees "
               "still separate working files. GPU detection never changes the selected mode. "
               "Existing active conversations are never killed or sent commands.")
    parser.add_argument("-a", "--agents", default=os.environ.get("AGENTS_LIST", " ".join(NAMES)))
    parser.add_argument("-s", "--session", default=os.environ.get("AGENTS_SESSION"))
    parser.add_argument("--approvals", choices=("auto", "interactive"),
                        default=os.environ.get("AGENTS_APPROVAL_MODE", "auto"))
    parser.add_argument("--codex-sandbox", choices=SANDBOX_MODES,
                        default=os.environ.get("AGENTS_CODEX_SANDBOX", "configured"),
                        help="configured follows the user's Codex mode/profile; applies on the next launch")
    parser.add_argument("--require-gpu", action=argparse.BooleanOptionalAction,
                        default=os.environ.get("AGENTS_REQUIRE_GPU", "0") == "1",
                        help="fail before launching if NVIDIA devices are unavailable to this launcher")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--check", action="store_true", help="read-only installation and live-session audit")
    mode.add_argument("--clean", action="store_true", help="remove clean, inactive worktrees; retain branches")
    mode.add_argument("--dry-run", action="store_true", help="print a plan without creating files or windows")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True,
                        help="resume each worktree's last conversation, falling back to a new one "
                             "(default: --resume; use --no-resume to always start fresh)")
    parser.add_argument("--no-attach", action="store_true", help="prepare windows without switching your terminal")
    args = parser.parse_args()
    if args.approvals not in ("auto", "interactive"):
        raise Error("AGENTS_APPROVAL_MODE must be auto or interactive")
    if os.getuid() == 0:
        raise Error("run agents as your normal login user, not root")
    if Path.home().resolve() != Path(pwd.getpwuid(os.getuid()).pw_dir).resolve():
        raise Error("HOME does not match the current user's account")
    for binary in ("git", "tmux", "bash"):
        if not shutil.which(binary):
            raise Error(f"required executable not found: {binary}")
    selected = args.agents.split()
    if not selected or len(set(selected)) != len(selected) or any(a not in NAMES for a in selected):
        raise Error("choose unique agent names from: kiro codex claude")
    common, main_root, records = repository(Path.cwd())
    prefix = os.environ.get("AGENTS_BRANCH_PREFIX", "agent")
    branches = {a: prefix + "/" + a for a in selected}
    for branch in branches.values():
        git("check-ref-format", "--branch", branch)
    digest = hashlib.sha256(os.fsencode(common)).hexdigest()[:10]
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", main_root.name)[:36] or "repo"
    home = Path.home().resolve()
    # Agent worktrees stay inside the caller's home directory. Locations such as
    # /tmp, /srv or another account's home can be writable by other users, and
    # these agents start with tool approval bypassed.
    override = os.environ.get("AGENTS_WORKTREE_DIR")
    if override:
        worktree_dir = Path(override).expanduser().resolve()
        if home not in worktree_dir.parents:
            raise Error(f"AGENTS_WORKTREE_DIR must be inside {home}: {worktree_dir}")
    else:
        worktree_dir = (main_root.parent / (main_root.name + "-agents")).resolve()
        if home not in worktree_dir.parents:
            worktree_dir = home / ".agents-worktrees" / f"{slug}-{digest}"
            print(f"agents: repository is outside {home}; placing worktrees in {worktree_dir}")
    paths = {a: (worktree_dir / a).resolve() for a in selected}
    if len(set(paths.values())) != len(paths):
        raise Error("agent worktrees must have different paths")
    for agent, path in paths.items():
        # Re-checked per agent: a symlinked entry could otherwise resolve outside home.
        if home not in path.parents:
            raise Error(f"agent worktree must be inside {home}: {path}")
        if path.exists() and path.stat().st_uid != os.getuid():
            raise Error(f"agent worktree is owned by another user: {path}")
        validate_worktree(path, branches[agent], common, records)
        if path == main_root or main_root in path.parents:
            raise Error("agent worktrees must be outside the main checkout")
        if any(p == path or p in path.parents or path in p.parents for p in records if p != path):
            raise Error("worktrees must not be nested in another checkout")
    if worktree_dir.exists() and worktree_dir.stat().st_uid != os.getuid():
        raise Error(f"worktree directory is owned by another user: {worktree_dir}")
    session = args.session or f"agents-{slug}-{digest}"
    # Adopt a legacy session only if every pane belongs to this repository.
    if not args.session and session_exists("agents") and owns_session("agents", common):
        session = "agents"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", session):
        raise Error("session names may contain only letters, numbers, underscores and hyphens")
    exists = session_exists(session)
    rows = panes(session) if exists else []
    if exists and not owns_session(session, common):
        raise Error(f"session {session!r} belongs to another repository; choose another --session")
    print(f"agents: user={pwd.getpwuid(os.getuid()).pw_name} repo={main_root}")
    print(f"agents: session={session} worktrees={worktree_dir} approvals={args.approvals}")
    if args.list:
        for path, record in records.items():
            print(f"  {path}: {record.get('branch', 'detached')}")
        for row in rows:
            print(f"  window {row['name']} {row['pane']}: {row['path']}")
        return 0
    commands = {}
    resume_commands = {}
    if not args.clean:
        policy = None
        if "codex" in selected:
            if os.environ.get("AGENTS_CMD_CODEX"):
                print("agents: Codex policy is controlled by AGENTS_CMD_CODEX")
            else:
                policy = codex_policy(args.codex_sandbox, common, args.approvals)
                print(f"agents: Codex next-launch policy: {policy['label']}")
                if policy["mode"] == "danger-full-access":
                    print("agents: selected Codex mode has full filesystem access; worktrees separate working files.")
        gpu = gpu_status()
        print(f"agents: GPU: {gpu['message']}")
        print("agents: launcher GPU visibility is not a CUDA test inside a running agent; check the new session.")
        if args.require_gpu and not gpu["ready"]:
            raise Error("GPU required but unavailable here; no agents were launched. Run from a GPU-capable host/runner.")
        # All installations are checked before any worktree or window is created.
        for agent in selected:
            commands[agent] = command(agent, args.approvals, False, common, policy)
            if args.resume:
                resuming = command(agent, args.approvals, True, common, policy)
                if resuming is None:
                    print(f"agents: {agent}: AGENTS_CMD override cannot resume; starting a new conversation")
                else:
                    resume_commands[agent] = resuming
    if args.check:
        issues = 0
        for agent, argv in commands.items():
            result = run(argv[0], "--version", check=False)
            version = (result.stdout or result.stderr).strip().splitlines()
            print(f"  {agent}: {argv[0]} | {version[0] if version else 'no version output'}")
            if agent in resume_commands:
                print(f"    next launch: {shlex.join(resume_commands[agent])}")
                print(f"    if nothing to resume: {shlex.join(argv)}")
            else:
                print(f"    next launch: {shlex.join(argv)}")
            issues += bool(result.returncode)
            matching = [r for r in rows if Path(r["path"]).resolve() == paths[agent]]
            processes = [p for row in matching for p in agent_processes(row)]
            if not processes:
                print("    live: no running agent in the expected worktree")
                issues += 1
            for process in processes:
                stale = process["exe"].endswith(" (deleted)")
                wrong_user = process["uid"] != os.getuid()
                issues += stale or wrong_user
                state = "RESTART REQUIRED" if stale else ("WRONG USER" if wrong_user else "running")
                print(f"    live: {state} pid={process['pid']} uid={process['uid']} {process['exe']}")
        print("agents: active sessions retain their startup permissions; next-launch flags do not modify them.")
        return 1 if issues else 0
    # Preflight branches and existing windows for every selected agent.
    by_agent = {}
    for agent, path in paths.items():
        matching = [r for r in rows if r["name"] == agent or Path(r["path"]).resolve() == path]
        if len(matching) > 1:
            raise Error(f"multiple panes match {agent}; keep one agent per window")
        if matching:
            row = matching[0]
            if row["name"] != agent or Path(row["path"]).resolve() != path:
                raise Error(f"existing window {row['name']} has the wrong worktree for {agent}")
            by_agent[agent] = row
        for other_path, record in records.items():
            if record.get("branch") == "refs/heads/" + branches[agent] and other_path != path:
                raise Error(f"branch {branches[agent]} is already checked out at {other_path}")
    if args.dry_run:
        for agent in selected:
            state = "reuse" if paths[agent] in records else "create"
            print(f"  {state} {paths[agent]} ({branches[agent]})")
            if agent in resume_commands:
                print(f"  command: {shlex.join(resume_commands[agent])}")
                print(f"  if nothing to resume: {shlex.join(commands[agent])}")
            else:
                print(f"  command: {shlex.join(commands[agent])}")
        return 0
    if args.clean:
        all_panes = run("tmux", "list-panes", "-a", "-F", "#{pane_current_path}", check=False)
        live_paths = [Path(p).resolve() for p in all_panes.stdout.splitlines()]
        failed = False
        for agent, path in paths.items():
            if path not in records:
                continue
            cwd = Path.cwd().resolve()
            if (cwd == path or path in cwd.parents or
                    any(p == path or path in p.parents for p in live_paths)):
                print(f"agents: kept active worktree {path}")
                failed = True
                continue
            result = run("git", "-C", str(main_root), "worktree", "remove", str(path), check=False)
            if result.returncode:
                print(f"agents: kept {path}: {result.stderr.strip()}")
                failed = True
            else:
                print(f"agents: removed {path}; branch retained")
        return 1 if failed else 0
    git("rev-parse", "--verify", "HEAD", cwd=main_root)
    # A per-repository lock prevents concurrent launches creating duplicate windows.
    lock_path = common / "agents-launch.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if session_exists(session) != exists or panes(session) != rows:
            raise Error("session changed during startup; rerun agents")
        for agent, path in paths.items():
            if path not in records:
                worktree_dir.mkdir(parents=True, exist_ok=True)
                present = run("git", "-C", str(main_root), "show-ref", "--verify", "--quiet",
                              "refs/heads/" + branches[agent], check=False).returncode == 0
                if present:
                    git("worktree", "add", str(path), branches[agent], cwd=main_root)
                else:
                    git("worktree", "add", "-b", branches[agent], str(path), "HEAD", cwd=main_root)
        shell = shutil.which("bash")
        for agent, argv in commands.items():
            # tmux receives one deliberately quoted shell command; no send-keys.
            first = resume_commands.get(agent, argv)
            launch = (f"export PATH={shlex.quote(os.environ.get('PATH', ''))}; "
                      "agent_started=$(date +%s); "
                      f"{shlex.join(first)}; agent_status=$?; ")
            if agent in resume_commands:
                # A missing conversation fails within a second, while a resumed
                # session lasts longer, so only an immediate failure starts fresh.
                # This avoids depending on each CLI's private session storage.
                launch += ("if [ \"$agent_status\" -ne 0 ] && "
                           "[ $(( $(date +%s) - agent_started )) -lt 5 ]; then "
                           "printf '\\nNo conversation to resume; starting a new one.\\n'; "
                           f"{shlex.join(argv)}; agent_status=$?; fi; ")
            launch += ("printf '\\nAgent exited (status %s). Shell retained.\\n' \"$agent_status\"; "
                       f"exec {shlex.quote(shell)} --noprofile --norc -i")
            if agent in by_agent:
                row = by_agent[agent]
                if agent_processes(row):
                    # Never type into or kill a running assistant.
                    print(f"agents: existing {agent} window retained with its startup permissions")
                    if any(p["exe"].endswith(" (deleted)") for p in agent_processes(row)):
                        print(f"  {agent} is running a removed installation; exit it and resume from the new binary.")
                    if args.resume:
                        print(f"  exit the active CLI, then run here: {shlex.join(first)}")
                    continue
                if row["cmd"] not in SHELLS or process_tree(row["pid"]):
                    # Something else occupies the window; leave the user's work alone.
                    print(f"agents: existing {agent} window is busy running {row['cmd']}; left alone")
                    print(f"  run here when it finishes: {shlex.join(first)}")
                    continue
                # The agent exited earlier and left the retained shell behind, so
                # the window looks present while nothing is running in it.
                run("tmux", "respawn-pane", "-k", "-t", row["pane"],
                    "-c", str(paths[agent]), launch)
                print(f"agents: restarted {agent} in its idle window: {shlex.join(first)}")
                continue
            if not session_exists(session):
                run("tmux", "new-session", "-d", "-s", session, "-n", agent,
                    "-c", str(paths[agent]), launch)
            else:
                run("tmux", "new-window", "-t", "=" + session, "-n", agent,
                    "-c", str(paths[agent]), launch)
            print(f"agents: started {agent}: {shlex.join(first)}")
    if args.no_attach or not sys.stdout.isatty():
        print(f"agents: attach with: tmux attach -t ={session}")
    elif os.environ.get("TMUX"):
        os.execvp("tmux", ["tmux", "switch-client", "-t", "=" + session])
    else:
        os.execvp("tmux", ["tmux", "attach", "-t", "=" + session])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Error, OSError, ValueError) as exc:
        print(f"agents: {exc}", file=sys.stderr)
        sys.exit(1)
