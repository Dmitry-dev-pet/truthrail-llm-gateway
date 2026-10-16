"""Offline fail-closed dual-model CLIProxyAPI configuration contracts.

No provider network, real secrets, Render deployment or privileged process.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

import yaml

ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"
CLIENT = "c" * 64
PROVIDER = "g" * 64
MODEL_GLM = "glm-5.3-flash"
MODEL_LUNA = "gpt-6-luna"


class LunaOptInTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "protected"
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CPA_RUNTIME_DIR": str(self.root),
            "CPA_VALIDATE_ONLY": "1",
            "PORT": "10000",
            "CPA_CLIENT_API_KEY": CLIENT,
            "CPA_OPENCODE_GO_API_KEY": PROVIDER,
        }

    def boot(self):
        return subprocess.run(["sh", str(ENTRYPOINT)], env=self.env,
                              capture_output=True, text=True, check=False, timeout=10)

    def yaml(self):
        path = self.root / "config.yaml"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_off_by_default_preserves_sole_existing_glm_route(self):
        response = self.boot()
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("gateway=CONFIGURED provider_count=1 model=opencode-go/glm-5.3-flash",
                      response.stdout)
        cfg = self.yaml()
        self.assertEqual(set(cfg), {
            "config-version", "server", "management", "access",
            "oauth", "routing", "api-keys",
        })
        self.assertEqual(cfg["api-keys"].keys(), {"openai-compatibility"})
        glm, = cfg["api-keys"]["openai-compatibility"]
        self.assertEqual(glm["name"], "opencode-go-coding")
        self.assertEqual(glm["prefix"], "opencode-go")
        self.assertEqual(glm["request-retry"], 0)
        self.assertEqual(glm["base-url"],
                         "https://opencode.ai/inference/go/openai/v1")
        self.assertEqual(glm["headers"], {
            "X-OpenCode-Session": "$X-OpenCode-Session",
            "User-Agent": "Truthrail-Coding-Agent/1.0",
        })
        self.assertEqual(glm["keys"], [{"api-key": PROVIDER}])
        self.assertEqual(glm["models"],
                         [{"name": MODEL_GLM, "alias": MODEL_GLM}])
        self.assertNotIn("multimedia", cfg)
        self.assertEqual(cfg["access"]["api-keys"], [CLIENT])
        self.assertEqual(cfg["routing"]["retry"]["request-retry"], 0)
        self.assertFalse(cfg["management"]["allow-remote"])
        self.assertTrue(cfg["management"]["disable-control-panel"])
        self.assertNotIn(CLIENT, response.stdout + response.stderr)
        self.assertNotIn(PROVIDER, response.stdout + response.stderr)

    def test_explicit_zero_matches_previous_default(self):
        first = self.boot()
        self.assertEqual(first.returncode, 0)
        before = self.yaml()
        self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = "0"
        second = self.boot()
        self.assertEqual(second.returncode, 0)
        self.assertEqual(before, self.yaml())
        self.assertEqual(first.stdout, second.stdout)

    def test_luna_optin_preserves_glm_and_adds_only_responses(self):
        self.assertEqual(self.boot().returncode, 0)
        glm_before = self.yaml()["api-keys"]["openai-compatibility"]
        self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = "1"
        run = self.boot()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("provider_count=2", run.stdout)
        self.assertIn("opencode-go/gpt-6-luna", run.stdout)
        self.assertNotIn(CLIENT, run.stdout + run.stderr)
        self.assertNotIn(PROVIDER, run.stdout + run.stderr)
        cfg = self.yaml()
        self.assertEqual(set(cfg["api-keys"]), {"openai-compatibility", "codex"})
        self.assertEqual(cfg["api-keys"]["openai-compatibility"], glm_before)
        self.assertEqual(cfg["multimedia"], {
            "disable-image-generation": "passthrough",
        })
        codex, = cfg["api-keys"]["codex"]
        self.assertEqual(codex["name"], "opencode-go-luna-coding")
        self.assertEqual(codex["prefix"], "opencode-go")
        self.assertEqual(codex["base-url"],
                         "https://opencode.ai/inference/go/openai/v1")
        self.assertEqual(codex["request-retry"], 0)
        self.assertEqual(codex["headers"], {
            "X-OpenCode-Session": "$X-OpenCode-Session",
            "User-Agent": "Truthrail-Coding-Agent/1.0",
        })
        self.assertEqual(codex["keys"], [{
            "api-key": PROVIDER, "disable-codex-cloaking": True,
        }])
        self.assertEqual(codex["models"], [{
            "name": MODEL_LUNA, "alias": MODEL_LUNA,
        }])
        self.assertNotIn("openai-compatibility", str(codex))
        self.assertEqual(cfg["management"]["secret-key"], "")
        self.assertFalse(cfg["management"]["allow-remote"])
        self.assertTrue(cfg["management"]["disable-control-panel"])
        self.assertEqual(cfg["routing"]["retry"]["request-retry"], 0)

    def test_missing_provider_cannot_enable_luna_even_in_sealed_mode(self):
        self.env.pop("CPA_OPENCODE_GO_API_KEY")
        self.env.pop("CPA_CLIENT_API_KEY")
        self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = "1"
        run = self.boot()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("luna_requires_existing_upstream_key", run.stderr)
        self.assertFalse((self.root / "config.yaml").exists())

    def test_missing_downstream_key_denied_when_provider_present(self):
        self.env.pop("CPA_CLIENT_API_KEY")
        self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = "1"
        run = self.boot()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("client_key_required_for_upstream", run.stderr)
        self.assertFalse((self.root / "config.yaml").exists())

    def test_invalid_luna_flags_fail_before_config(self):
        for value in ("", "yes", "on", "true", "TRUE", "2", "-1",
                      "gpt-6-luna", "0,1", "1\nmanagement:\n  allow-remote: true"):
            with self.subTest(flag=value):
                self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = value
                run = self.boot()
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("invalid_luna_opt_in", run.stderr)
                self.assertFalse((self.root / "config.yaml").exists())
                self.assertNotIn(CLIENT, run.stdout + run.stderr)
                self.assertNotIn(PROVIDER, run.stdout + run.stderr)
                self.env.pop("CPA_OPENCODE_GO_LUNA_ENABLED")

    def test_reject_dynamic_protocol_model_lists_in_both_modes(self):
        for env_name in ("CPA_OPENCODE_GO_RESPONSES_MODELS",
                         "CPA_OPENCODE_GO_MESSAGES_MODELS"):
            for enabled in ("0", "1"):
                with self.subTest(name=env_name, enabled=enabled):
                    self.env["CPA_OPENCODE_GO_LUNA_ENABLED"] = enabled
                    self.env[env_name] = "gpt-5.6-luna"
                    run = self.boot()
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn("dynamic_protocol_model_selection_not_reviewed",
                                  run.stderr)
                    self.assertFalse((self.root / "config.yaml").exists())
                    self.env.pop(env_name)

    def test_no_secret_or_subscription_auth_and_one_binary(self):
        code = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertEqual(code.count("exec /CLIProxyAPI/CLIProxyAPI"), 1)
        self.assertNotIn("AGY_OAUTH_TOKEN", code)
        self.assertNotIn("GITSTORE_GIT_TOKEN\" \"$CPA_OPENCODE_GO_API_KEY", code)
        self.assertEqual(code.count("disable-image-generation: passthrough"), 1)
        self.assertEqual(code.count("disable-codex-cloaking: true"), 1)
        self.assertIn("CPA_OPENCODE_GO_LUNA_ENABLED-0", code)

    def test_shell_syntax_remains_valid(self):
        r = subprocess.run(["sh", "-n", str(ENTRYPOINT)], capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
