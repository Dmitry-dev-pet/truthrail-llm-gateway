"""Offline boot contract: credentials are always synthetic; network is not used."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

import yaml


ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"
CLIENT = "c" * 64
GO = "go" + "a" * 62


class SecureEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CPA_RUNTIME_DIR": str(self.root / "runtime"),
            "PORT": "10000",
            "CPA_VALIDATE_ONLY": "1",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def boot(self):
        return subprocess.run(
            ["sh", str(ENTRYPOINT)], env=self.env,
            capture_output=True, text=True, timeout=10, check=False,
        )

    def config(self):
        file = self.root / "runtime" / "config.yaml"
        self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        return yaml.safe_load(file.read_text(encoding="utf-8"))

    def test_no_credentials_produces_sealed_proxy_not_an_open_proxy(self):
        r = self.boot()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gateway=SEALED", r.stdout)
        c = self.config()
        self.assertEqual(c["api-keys"], {})
        self.assertEqual(c["config-version"], 8)
        self.assertEqual(c["server"]["port"], 10000)
        self.assertEqual(c["management"]["secret-key"], "")
        self.assertFalse(c["management"]["allow-remote"])
        self.assertTrue(c["management"]["disable-control-panel"])
        k, = c["access"]["api-keys"]
        self.assertEqual(len(k), 64)
        self.assertNotIn(k, r.stdout + r.stderr)
        self.assertEqual(stat.S_IMODE((self.root / "runtime").stat().st_mode), 0o700)

    def test_sealed_mode_generates_distinct_unpublished_keys(self):
        self.assertEqual(self.boot().returncode, 0)
        old, = self.config()["access"]["api-keys"]
        self.assertEqual(self.boot().returncode, 0)
        new, = self.config()["access"]["api-keys"]
        self.assertNotEqual(old, new)

    def test_live_provider_without_client_key_fails_closed(self):
        self.env["CPA_OPENCODE_GO_API_KEY"] = GO
        r = self.boot()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.root / "runtime" / "config.yaml").exists())
        self.assertNotIn(GO, r.stdout + r.stderr)

    def test_live_provider_exact_model_and_session_header(self):
        self.env.update({
            "CPA_OPENCODE_GO_API_KEY": GO,
            "CPA_CLIENT_API_KEY": CLIENT,
        })
        r = self.boot()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gateway=CONFIGURED", r.stdout)
        c = self.config()
        self.assertEqual(c["access"]["api-keys"], [CLIENT])
        g, = c["api-keys"]["openai-compatibility"]
        self.assertEqual(g["prefix"], "opencode-go")
        self.assertEqual(g["base-url"], "https://opencode.ai/inference/go/openai/v1")
        self.assertEqual(g["request-retry"], 0)
        self.assertEqual(c["routing"]["retry"]["request-retry"], 0)
        self.assertEqual(g["headers"], {
            "X-OpenCode-Session": "$X-OpenCode-Session",
            "User-Agent": "Truthrail-Coding-Agent/1.0",
        })
        self.assertEqual(g["keys"], [{"api-key": GO}])
        self.assertEqual(g["models"], [{"name": "glm-5.3-flash", "alias": "glm-5.3-flash"}])
        self.assertNotIn(GO, r.stdout + r.stderr)
        self.assertNotIn(CLIENT, r.stdout + r.stderr)

    def test_render_generated_base64_key_supported(self):
        self.env["CPA_CLIENT_API_KEY"] = "A" * 43 + "="
        self.assertEqual(self.boot().returncode, 0)
        self.assertEqual(self.config()["access"]["api-keys"], ["A" * 43 + "="])

    def test_example_keys_and_yaml_injection_rejected(self):
        for key in ["EXAMPLE" + "x" * 60, CLIENT + '"\nmanagement:\n  allow-remote: true']:
            with self.subTest(key_kind="synthetic"):
                self.env["CPA_CLIENT_API_KEY"] = key
                r = self.boot()
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.root / "runtime" / "config.yaml").exists())
        self.env.pop("CPA_CLIENT_API_KEY")

    def test_all_legacy_stores_and_remote_management_fail_closed(self):
        for var in ["GITSTORE_GIT_URL", "GITSTORE_GIT_TOKEN", "GITSTORE_GIT_USERNAME",
                    "MANAGEMENT_PASSWORD", "PGSTORE_DSN", "OBJECTSTORE_ENDPOINT"]:
            with self.subTest(var=var):
                self.env[var] = "synthetic-hidden-value"
                r = self.boot()
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn("synthetic-hidden-value", r.stdout + r.stderr)
                self.assertFalse((self.root / "runtime" / "config.yaml").exists())
                self.env.pop(var)

    def test_invalid_port_or_parent_traversal_rejected(self):
        for v in ["foo", "-10", "65536"]:
            with self.subTest(port=v):
                self.env["PORT"] = v
                self.assertNotEqual(self.boot().returncode, 0)
        self.env["PORT"] = "10000"
        self.env["CPA_RUNTIME_DIR"] = str(self.root / ".." / "unsafe")
        self.assertNotEqual(self.boot().returncode, 0)

    def test_invalid_provider_key_does_not_start(self):
        self.env.update({"CPA_CLIENT_API_KEY": CLIENT, "CPA_OPENCODE_GO_API_KEY": "short"})
        r = self.boot()
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("short", r.stdout + r.stderr)
        self.assertFalse((self.root / "runtime" / "config.yaml").exists())


if __name__ == "__main__":
    unittest.main()
