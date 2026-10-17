import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class UploadScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.log = self.root / "connections.log"
        mock = self.root / "ssh"
        mock.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["CONNECTION_TEST_LOG"], "a") as log:
    log.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]]) + "\\n")
if sys.argv[-1].startswith("bash "):
    sys.stdin.read()
if os.path.basename(sys.argv[0]) == os.environ.get("FAIL_TOOL"):
    sys.exit(1)
""")
        mock.chmod(0o700)
        (self.root / "scp").symlink_to(mock)
        self.environment = {
            **os.environ,
            "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
            "CONNECTION_TEST_LOG": str(self.log),
            "VPS_HOST": "vps.example.com",
            "VPS_PORT": "2222",
            "VPS_USER": "deploy",
            "GHCR_USERNAME": "test-user",
            "VPS_SSH_PRIVATE_KEY": "test-only-private-key",
            "VPS_KNOWN_HOSTS": "[vps.example.com]:2222 ssh-ed25519 test-only-key",
            "GHCR_READ_TOKEN": "test-only-registry-token",
            "RUNNER_TEMP": str(self.root),
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def execute(self, **overrides):
        return subprocess.run(
            ["bash", str(Path(__file__).with_name("upload.sh"))],
            env={**self.environment, **overrides},
            capture_output=True, text=True, check=False,
        )

    def test_verified_host_keys_transfer_and_remote_execution(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([call[0] for call in calls], ["ssh", "scp", "ssh"])
        for call in calls:
            self.assertIn("StrictHostKeyChecking=yes", call)
            self.assertIn("BatchMode=yes", call)
        self.assertIn("2222", calls[0])
        self.assertIn("/bbm-release/.env", " ".join(calls[1]))
        self.assertIn("bash '/opt/apps/bbm/releases/", calls[2][-1])
        self.assertEqual((self.root / "bbm-ssh-key").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("test-only-registry-token", self.log.read_text() + result.stdout + result.stderr)

    def test_missing_credentials_invalid_host_and_failed_copy_stop_deployment(self):
        for overrides in [
            {"VPS_SSH_PRIVATE_KEY": ""},
            {"VPS_HOST": "-oProxyCommand=untrusted"},
            {"VPS_USER": "deploy;untrusted"},
            {"VPS_PORT": "0"},
            {"FAIL_TOOL": "scp"},
        ]:
            with self.subTest(overrides=overrides):
                self.log.write_text("")
                result = self.execute(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("bash '/opt/apps/bbm/releases/", self.log.read_text())
