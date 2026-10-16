import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class DeploymentScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "app"
        self.release = self.app / "releases" / ("a" * 40 + "-123-1")
        self.release.mkdir(parents=True)
        self.dotenv = (
            "POSTGRES_DB=bbm\nPOSTGRES_USER=bbm\n"
            "POSTGRES_PASSWORD='test-only'\nDATABASE_URL=postgres://test-only\n"
        )
        (self.release / ".env").write_text(self.dotenv)
        (self.release / "docker-compose.yml").write_text("new-compose")
        self.log = self.root / "docker.log"
        mock = self.root / "docker"
        mock.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
arguments = sys.argv[1:]
with open(os.environ["DOCKER_TEST_LOG"], "a") as log:
    log.write(json.dumps(arguments) + "\\n")
command = " ".join(arguments)
if arguments[0] == "login":
    sys.stdin.read()
    pathlib.Path(os.environ["DOCKER_CONFIG"], "config.json").write_text("temporary-auth")
if os.environ.get("FAIL_PATTERN") and os.environ["FAIL_PATTERN"] in command:
    sys.exit(1)
if arguments[:2] == ["volume", "inspect"]:
    sys.exit(0 if os.environ.get("EXISTING_VOLUME") else 1)
if "pg_dump" in command or "tar -C /app -czf" in command:
    print("backup-bytes")
""")
        mock.chmod(0o700)
        self.environment = {
            **os.environ,
            "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
            "DOCKER_TEST_LOG": str(self.log),
        }
        source = Path(__file__).with_name("deploy.sh").read_text()
        # Isolate the script's fixed VPS paths; never touch /opt/apps/bbm in tests.
        source = source.replace("app=/opt/apps/bbm", f"app={self.app}")
        source = source.replace("^/opt/apps/bbm/releases/", f"^{self.app}/releases/")
        self.script = self.root / "deploy.sh"
        self.script.write_text(source)

    def execute(self, **overrides):
        return subprocess.run(
            ["bash", str(self.script), str(self.release), "test-user"],
            env={**self.environment, **overrides},
            input="test-token",
            capture_output=True,
            text=True,
            check=False,
        )

    def commands(self):
        return [" ".join(json.loads(line)) for line in self.log.read_text().splitlines()]

    def existing_installation(self):
        (self.app / ".env").write_text(self.dotenv)
        (self.app / "docker-compose.yml").write_text("old-compose")

    def test_first_install_and_secret_cleanup(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        self.assertLess(
            next(i for i, line in enumerate(commands) if "volume inspect" in line),
            next(i for i, line in enumerate(commands) if "manage.py check" in line),
        )
        self.assertTrue(any("manage.py migrate --noinput" in line for line in commands))
        self.assertIn("up -d --wait --wait-timeout 180", commands[-2])
        self.assertEqual((self.app / ".env").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.release / ".env").exists())
        self.assertFalse((self.release / "docker-auth").exists())
        self.assertNotIn("test-token", result.stdout + result.stderr + self.log.read_text())

    def test_update_backs_up_before_migrations(self):
        self.existing_installation()
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        positions = [
            next(i for i, line in enumerate(commands) if part in line)
            for part in ("config --quiet", " pull", "manage.py check", "stop nginx backend", "pg_dump", "tar -C", "manage.py migrate", "manage.py collectstatic")
        ]
        self.assertEqual(positions, sorted(positions))
        backup = self.app / "backups" / self.release.name
        self.assertGreater((backup / "database.dump").stat().st_size, 0)
        self.assertGreater((backup / "uploads.tar.gz").stat().st_size, 0)
        self.assertEqual((backup / ".env").stat().st_mode & 0o777, 0o600)
        self.assertEqual((backup / "docker-compose.yml").read_text(), "old-compose")

    def test_failures_stop_release_and_clean_credentials(self):
        for pattern in ("config --quiet", " pull", "manage.py check", "pg_dump", "manage.py migrate", "manage.py collectstatic"):
            with self.subTest(pattern=pattern):
                self.existing_installation()
                (self.release / ".env").write_text(self.dotenv)
                self.log.write_text("")
                result = self.execute(FAIL_PATTERN=pattern)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("deployment completed", result.stdout)
                self.assertIn("Deployment failed", result.stderr)
                self.assertFalse(any("up -d --wait --wait-timeout 180" in line for line in self.commands()))
                self.assertFalse((self.release / "docker-auth").exists())
                self.assertFalse((self.release / ".env").exists())

    def test_rejects_unknown_data_and_database_password_changes(self):
        result = self.execute(EXISTING_VOLUME="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manual recovery required", result.stderr)
        self.assertFalse(any("manage.py migrate" in line for line in self.commands()))
        self.existing_installation()
        (self.release / ".env").write_text(self.dotenv.replace("test-only", "changed"))
        self.log.write_text("")
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing automatic change", result.stderr)
        self.assertFalse(any("stop nginx backend" in line for line in self.commands()))

    def test_host_lock_prevents_concurrent_deployment(self):
        with (self.app / ".deploy.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another BBM deployment", result.stderr)
        self.assertFalse(self.log.exists())
