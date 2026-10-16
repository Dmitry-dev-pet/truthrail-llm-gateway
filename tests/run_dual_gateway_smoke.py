#!/usr/bin/env python3
"""Exercise the pinned public gateway with local-only GLM and Luna mock routes.

All client/upstream credentials are synthetic. The production gateway image
is built by the owning CI, not fetched from a floating deployment. Docker
images may be pulled before network isolation; no model or provider HTTP
traffic is ever sent outside the internal bridge.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "entrypoint.sh"
DOCKERFILE = ROOT / "Dockerfile"
STUB = Path(__file__).with_name("mock_dual_llm_upstream.py")
IMAGE = "truthrail-gateway:ci"
STUB_IMAGE = "python:3.12-slim-bookworm"
UPSTREAM_BASE = "https://opencode.ai/inference/go/openai/v1"
FAKE_BASE = "http://fake-upstream:8766/v1"
CLIENT_KEY = "c" * 64
UPSTREAM_KEY = "g" * 64
PINNED_DIGEST = (
    "docker.io/eceasy/cli-proxy-api@sha256:"
    "5d5a9836ebe7743e021ec88b16db59318f10f9814a3f36557fd729ae7c5539a1"
)


class ContractError(RuntimeError):
    pass


def command(*args: str, timeout=120, allow_failure=False, env=None):
    minimal_env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    if env is not None:
        minimal_env.update(env)
    try:
        out = subprocess.run(args, check=False, capture_output=True, text=True,
                             timeout=timeout, env=minimal_env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError("command_unavailable_or_timeout") from exc
    if out.returncode and not allow_failure:
        raise ContractError("command_failed")
    return out


def verify_fixed_image() -> None:
    doc = DOCKERFILE.read_text(encoding="utf-8")
    values = re.findall(r"^FROM (docker\.io/eceasy/cli-proxy-api@sha256:[a-f0-9]{64})",
                        doc, flags=re.MULTILINE)
    if values != [PINNED_DIGEST]:
        raise ContractError("image_digest_changed")


def generate_config(folder: Path) -> Path:
    """Exercise the REAL source-controlled entrypoint using dummy secrets only."""
    env = {
        "CPA_RUNTIME_DIR": str(folder / "runtime"),
        "CPA_VALIDATE_ONLY": "1",
        "CPA_CLIENT_API_KEY": CLIENT_KEY,
        "CPA_OPENCODE_GO_API_KEY": UPSTREAM_KEY,
        "CPA_OPENCODE_GO_LUNA_ENABLED": "1",
        "PORT": "8317",
    }
    result = command("sh", str(ENTRYPOINT), timeout=15, env=env)
    if "gateway=CONFIGURED provider_count=2" not in result.stdout:
        raise ContractError("two_models_not_configured")
    config = folder / "runtime" / "config.yaml"
    if not config.is_file() or config.is_symlink():
        raise ContractError("mock_config_missing")
    if (config.stat().st_mode & 0o777) != 0o600:
        raise ContractError("mock_config_not_private")
    raw = config.read_text(encoding="utf-8")
    if raw.count(UPSTREAM_BASE) != 2:
        raise ContractError("unexpected_provider_host_count")
    if raw.count('disable-codex-cloaking: true') != 1:
        raise ContractError("per_key_identity_setting_missing")
    if raw.count('disable-image-generation: passthrough') != 1:
        raise ContractError("no_tools_setting_missing")
    if "gpt-6-luna" not in raw or "glm-5.3-flash" not in raw:
        raise ContractError("exact_model_missing")
    if "AGY_" in raw or "GITSTORE" in raw:
        raise ContractError("unreviewed_credential_route")
    actual = raw.replace(UPSTREAM_BASE, FAKE_BASE)
    auth_dir = str(folder / "runtime" / "auth")
    if actual.count(auth_dir) != 1:
        raise ContractError("mock_auth_dir_not_found")
    actual = actual.replace(auth_dir, "/tmp/mock-auth")
    config.write_text(actual, encoding="utf-8")
    config.chmod(0o600)
    return config


def sanitized_diagnostic(gateway: str, stub: str) -> None:
    # No process log bodies or HTTP provider errors are emitted, even though
    # this scenario only uses synthetic credentials.
    for name, label in ((gateway, "gateway"), (stub, "stub")):
        state = command("docker", "inspect", "-f",
                        "{{.State.Status}} {{.State.ExitCode}}",
                        name, allow_failure=True, timeout=10)
        if state.returncode == 0:
            parts = state.stdout.strip().split()
            if len(parts) == 2 and parts[0] in ("running", "exited", "dead"):
                print(f"dual_mock_{label}_state={parts[0]} exit={parts[1][:3]}",
                      file=sys.stderr)
    stats = command("docker", "exec", stub, "python3", "-c",
                    "import json,urllib.request;"
                    "print(json.dumps(json.load(urllib.request.urlopen("
                    "'http://127.0.0.1:8766/_stats',timeout=2))))",
                    timeout=8, allow_failure=True)
    if stats.returncode == 0:
        try:
            data = json.loads(stats.stdout)
            permitted = ("total", "glm", "luna", "wrong_path", "wrong_auth",
                         "wrong_model", "wrong_session", "wrong_agent",
                         "unexpected_tools", "oversize_request")
            if set(data) == set(permitted):
                print("dual_mock_counters=" + ",".join(
                    f"{key}:{int(data[key])}" for key in permitted), file=sys.stderr)
        except (ValueError, TypeError, KeyError):
            pass


def main() -> int:
    stage = "initial"
    stamp = uuid.uuid4().hex[:12]
    prefix = "llm-dual-ci-" + stamp
    bridge, stub, gateway = prefix + "-internal", prefix + "-stub", prefix + "-gateway"
    created_bridge = False
    try:
        verify_fixed_image()
        if not STUB.is_file():
            raise ContractError("mock_fixture_missing")
        with tempfile.TemporaryDirectory(prefix="llm-dual-") as tmp:
            config = generate_config(Path(tmp))
            stage = "image_available"
            command("docker", "image", "inspect", IMAGE, timeout=15)
            # Docker Hub access is needed only for this Python test image,
            # *before* creating an isolated internal network.
            command("docker", "pull", STUB_IMAGE, timeout=240)
            stage = "create_internal_network"
            command("docker", "network", "create", "--driver", "bridge",
                    "--internal", bridge)
            created_bridge = True
            net = command("docker", "network", "inspect", bridge,
                          "--format", "{{.Internal}}", timeout=12)
            if net.stdout.strip() != "true":
                raise ContractError("isolation_unverified")
            stage = "start_fake_upstream"
            command(
                "docker", "run", "-d", "--name", stub, "--network", bridge,
                "--network-alias", "fake-upstream",
                "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--pids-limit", "64", "--memory", "128m",
                "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m",
                "-v", f"{STUB}:/mock/dual.py:ro",
                "--entrypoint", "python3", STUB_IMAGE,
                "/mock/dual.py", "server", timeout=30,
            )
            stage = "start_real_pinned_gateway"
            command(
                "docker", "run", "-d", "--name", gateway, "--network", bridge,
                "--network-alias", "gateway",
                "--user", str(os.getuid()) + ":" + str(os.getgid()),
                "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--pids-limit", "64", "--memory", "512m",
                "--tmpfs", "/tmp:rw,nosuid,noexec,size=64m",
                "--workdir", "/tmp",
                "-v", f"{config}:/config.yaml:ro",
                "--entrypoint", "/CLIProxyAPI/CLIProxyAPI", IMAGE,
                "--config", "/config.yaml", timeout=30,
            )
            stage = "exercise_dual_model_requests"
            outcome = command(
                "docker", "exec", stub, "python3", "/mock/dual.py", "client",
                timeout=90, allow_failure=True)
            if outcome.returncode or "dual_gateway_smoke=PASS" not in outcome.stdout:
                for line in outcome.stderr.splitlines():
                    if line.startswith("dual_gateway_smoke=FAIL") and len(line) <= 130:
                        print(line, file=sys.stderr)
                sanitized_diagnostic(gateway, stub)
                raise ContractError("dual_models_not_verified")
            print(outcome.stdout.strip())
            print("gateway_dual_protocol_ci=PASS image_digest_pinned=true "
                  "existing_glm_preserved=true candidate_luna_verified_with_mock=true "
                  "anonymous_denied=true host_ports=none provider_calls=0")
            return 0
    except ContractError:
        print("gateway_dual_protocol_ci=FAIL stage=" + stage, file=sys.stderr)
        return 1
    finally:
        command("docker", "rm", "-f", gateway, stub, timeout=20, allow_failure=True)
        if created_bridge:
            command("docker", "network", "rm", bridge, timeout=20, allow_failure=True)


if __name__ == "__main__":
    raise SystemExit(main())
