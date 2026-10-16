"""Offline tests for the existing GLM plus opt-in Luna gateway mock."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import yaml

from mock_dual_llm_upstream import (
    CLIENT_KEY, UPSTREAM_KEY, MODEL_GLM, MODEL_LUNA,
    expected_stats, glm_response, luna_response,
)
from run_dual_gateway_smoke import (
    DOCKERFILE, ENTRYPOINT, FAKE_BASE, IMAGE, PINNED_DIGEST,
    STUB, UPSTREAM_BASE, generate_config, verify_fixed_image,
)

ROOT = Path(__file__).resolve().parents[1]


class DualGatewaySmokeContracts(unittest.TestCase):
    def test_digest_is_pinned(self):
        verify_fixed_image()
        self.assertIn(PINNED_DIGEST, DOCKERFILE.read_text())
        self.assertNotIn(":latest", DOCKERFILE.read_text())
        self.assertEqual(IMAGE, "truthrail-gateway:ci")

    def test_original_entrypoint_produces_exact_two_model_stub(self):
        with tempfile.TemporaryDirectory() as folder:
            config = generate_config(Path(folder))
            text = config.read_text()
            doc = yaml.safe_load(text)
            self.assertEqual(text.count(FAKE_BASE), 2)
            self.assertNotIn(UPSTREAM_BASE, text)
            self.assertEqual(doc["server"]["port"], 8317)
            self.assertEqual(set(doc["api-keys"]), {"openai-compatibility", "codex"})
            self.assertEqual(doc["access"]["api-keys"], [CLIENT_KEY])
            self.assertEqual(doc["api-keys"]["openai-compatibility"][0]["models"],
                             [{"name": MODEL_GLM, "alias": MODEL_GLM}])
            self.assertEqual(doc["api-keys"]["codex"][0]["models"],
                             [{"name": MODEL_LUNA, "alias": MODEL_LUNA}])
            self.assertEqual(doc["multimedia"]["disable-image-generation"], "passthrough")
            self.assertEqual(doc["api-keys"]["codex"][0]["keys"], [{
                "api-key": UPSTREAM_KEY, "disable-codex-cloaking": True,
            }])
            self.assertEqual(doc["api-keys"]["openai-compatibility"][0]["keys"],
                             [{"api-key": UPSTREAM_KEY}])
            self.assertEqual(doc["routing"]["retry"]["request-retry"], 0)

    def test_exact_stub_responses_and_counts(self):
        self.assertTrue(STUB.is_file())
        self.assertEqual(expected_stats()["total"], 2)
        self.assertEqual(expected_stats()["glm"], 1)
        self.assertEqual(expected_stats()["luna"], 1)
        self.assertEqual(glm_response()["choices"][0]["message"]["content"], "PASS")
        self.assertEqual(luna_response()["output"][0]["content"][0]["text"], "PASS")

    def test_docker_isolation_no_provider_key_or_host_port(self):
        source = (ROOT / "tests/run_dual_gateway_smoke.py").read_text()
        self.assertIn('"--internal"', source)
        self.assertIn('"--network", bridge', source)
        self.assertIn('"--cap-drop", "ALL"', source)
        self.assertIn('"--read-only"', source)
        self.assertIn('"--user", str(os.getuid())', source)
        self.assertNotIn('"--privileged"', source)
        self.assertNotIn('"--network", "host"', source)
        self.assertNotIn('"--publish"', source)
        self.assertNotIn('"--env-file"', source)
        self.assertNotIn("AGY_OAUTH", source)
        self.assertEqual(source.count('"CPA_OPENCODE_GO_API_KEY": UPSTREAM_KEY'), 1)
        self.assertNotIn("docker.sock", source)

    def test_real_entrypoint_keeps_single_binary(self):
        source = ENTRYPOINT.read_text()
        self.assertEqual(source.count("exec /CLIProxyAPI/CLIProxyAPI"), 1)
        self.assertEqual(source.count("disable-image-generation: passthrough"), 1)
        self.assertEqual(source.count("disable-codex-cloaking: true"), 1)


if __name__ == "__main__":
    unittest.main()
