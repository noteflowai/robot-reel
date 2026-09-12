import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import agents
from scripts.install_agents import digest, install


class AgentLauncherTests(unittest.TestCase):
    def test_configured_full_access_is_forwarded_on_new_and_resumed_sessions(self):
        common = Path("/work/project with spaces/.git")
        policy = agents.codex_policy("configured", common, "auto", {"sandbox_mode": "danger-full-access"})
        with patch.dict(os.environ, {}, clear=True), patch("scripts.agents.shutil.which", return_value="/bin/codex"):
            for resume in (False, True):
                argv = agents.command("codex", "auto", resume, common, policy)
                self.assertEqual(argv[argv.index("--sandbox")+1], "danger-full-access")
                self.assertEqual(argv[argv.index("--ask-for-approval")+1], "never")
                self.assertEqual("--last" in argv, resume)
                self.assertFalse(any("sandbox_workspace_write" in item for item in argv))

    def test_explicit_workspace_preserves_user_roots_and_network_restriction(self):
        common = Path("/work/中文 project/.git")
        config = {
            "sandbox_mode": "danger-full-access",
            "sandbox_workspace_write": {"writable_roots": ["/work/assets", str(common)], "network_access": False},
        }
        policy = agents.codex_policy("workspace-write", common, "auto", config)
        self.assertEqual(policy["mode"], "workspace-write")
        roots = next(a.split("=", 1)[1] for a in policy["args"] if "writable_roots=" in a)
        self.assertEqual(json.loads(roots), ["/work/assets", str(common)])
        self.assertNotIn("sandbox_workspace_write.network_access=true", policy["args"])

    def test_missing_config_and_named_profiles_do_not_invent_full_access(self):
        common = Path("/work/repo/.git")
        default = agents.codex_policy("configured", common, "auto", {})
        self.assertEqual(default["args"], ["--add-dir", str(common)])
        named = agents.codex_policy("configured", common, "auto", {"default_permissions": "gpu-workspace"})
        self.assertEqual(named["args"], ["-c", 'default_permissions="gpu-workspace"', "--add-dir", str(common)])
        for bad in ({ "sandbox_mode": "typo"}, {"default_permissions": True}):
            with self.assertRaises(agents.Error):
                agents.codex_policy("configured", common, "auto", bad)

    def test_custom_commands_and_other_agents_retain_their_own_flags(self):
        common = Path("/work/repo/.git")
        with patch.dict(os.environ, {}, clear=True), patch("scripts.agents.shutil.which", side_effect=lambda name: "/bin/"+name):
            self.assertEqual(agents.command("kiro", "auto", True, common), ["/bin/kiro-cli", "chat", "--resume", "--trust-all-tools"])
            self.assertEqual(agents.command("claude", "auto", True, common), ["/bin/claude", "--continue", "--permission-mode", "bypassPermissions"])
            with patch.dict(os.environ, {"AGENTS_CMD_CODEX": "codex --profile custom"}):
                self.assertEqual(agents.command("codex", "auto", False, common), ["/bin/codex", "--profile", "custom"])
                self.assertIsNone(agents.command("codex", "auto", True, common))

    def test_required_gpu_failure_starts_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main = root/"repo"
            main.mkdir()
            home = root
            common = main/".git"
            with (
                patch("sys.argv", ["agents", "-a", "codex", "--require-gpu", "--no-attach"]),
                patch("scripts.agents.Path.home", return_value=home),
                patch("scripts.agents.pwd.getpwuid") as user,
                patch("scripts.agents.shutil.which", side_effect=lambda name: "/bin/"+name),
                patch("scripts.agents.repository", return_value=(common, main, {main: {"branch": "refs/heads/main"}})),
                patch("scripts.agents.git", return_value=""),
                patch("scripts.agents.session_exists", return_value=False),
                patch("scripts.agents.codex_policy", return_value={"label": "test config", "args": [], "mode": None}),
                patch("scripts.agents.gpu_status", return_value={"ready": False, "message": "device nodes absent"}),
                patch("scripts.agents.run") as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                user.return_value.pw_dir = str(home)
                user.return_value.pw_name = "testuser"
                with self.assertRaisesRegex(agents.Error, "no agents were launched"):
                    agents.main()
                run.assert_not_called()
                self.assertFalse((root/"repo-agents").exists())

    def test_installation_preserves_original_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root/"new.py", root/"bin/agents"
            target.parent.mkdir()
            source.write_text("print('new')\n")
            old = b"print('old')\n"
            target.write_bytes(old)
            backup = install(source, target, digest(old))
            self.assertEqual(backup.read_bytes(), old)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertIsNone(install(source, target, digest(old)))

    def test_installer_retains_external_changes_and_rejects_symlink_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root/"new.py", root/"agents"
            source.write_text("print('new')\n")
            target.write_text("print('external update')\n")
            with self.assertRaisesRegex(ValueError, "changed since review"):
                install(source, target, digest(b"print('old')\n"))
            self.assertEqual(target.read_text(), "print('external update')\n")
            alias = root/"alias"
            alias.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                install(source, alias)
            self.assertEqual(target.read_text(), "print('external update')\n")
