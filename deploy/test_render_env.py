import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from render_env import REQUIRED, render


class RenderEnvTests(unittest.TestCase):
    def setUp(self):
        self.content = "\n".join(f"{key}=configured-value" for key in sorted(REQUIRED))
        self.references = {
            component: f"ghcr.io/mlindaamanimwendwa-ictpack/bbm-{component}@sha256:" + "a" * 64
            for component in ("backend", "frontend")
        }

    def test_exact_digests_and_literal_secrets(self):
        content = self.content.replace(
            "POSTGRES_PASSWORD=configured-value", "POSTGRES_PASSWORD='literal$with#characters'"
        )
        result = render(content, self.references)
        self.assertIn("POSTGRES_PASSWORD='literal$with#characters'", result)
        for component, reference in self.references.items():
            self.assertIn(f"{component.upper()}_IMAGE={reference}\n", result)

    def test_rejects_missing_placeholder_duplicate_and_unsafe_values(self):
        for content in [
            "",
            self.content.replace("POSTGRES_PASSWORD=configured-value", "POSTGRES_PASSWORD=REPLACE_ME"),
            self.content + "\nPOSTGRES_DB=duplicate",
            self.content + "\nBACKEND_IMAGE=untrusted",
            self.content + "\nCOMPOSE_PROJECT_NAME=other-app",
            self.content.replace("POSTGRES_PASSWORD=configured-value", "POSTGRES_PASSWORD=${OTHER_SECRET}"),
            self.content.replace("POSTGRES_PASSWORD=configured-value", "POSTGRES_PASSWORD=''"),
        ]:
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    render(content, self.references)

    def test_rejects_image_tags_and_injection(self):
        for reference in ["ghcr.io/owner/bbm-backend:latest", "not-an-image\nINJECTED=value"]:
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    render(self.content, {**self.references, "backend": reference})

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for interpolation check")
    def test_compose_preserves_quoted_secret_and_resolves_images(self):
        content = self.content.replace(
            "POSTGRES_PASSWORD=configured-value", "POSTGRES_PASSWORD='literal$with#characters'"
        )
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(render(content, self.references))
            result = subprocess.run(
                [
                    "docker", "compose", "--project-directory", directory,
                    "--env-file", str(dotenv),
                    "-f", str(Path(__file__).resolve().parent.parent / "compose.production.yml"),
                    "config", "--format", "json",
                ],
                env={key: value for key, value in os.environ.items() if key not in REQUIRED | {"BACKEND_IMAGE", "FRONTEND_IMAGE"}},
                capture_output=True,
                text=True,
                check=True,
            )
        services = json.loads(result.stdout)["services"]
        # Compose escapes dollars when serializing reusable configuration.
        password = services["db"]["environment"]["POSTGRES_PASSWORD"].replace("$$", "$")
        self.assertEqual(password, "literal$with#characters")
        self.assertEqual(services["backend"]["image"], self.references["backend"])
        self.assertEqual(services["nginx"]["image"], self.references["frontend"])
