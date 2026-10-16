#!/bin/sh
set -eu
umask 077

fail() {
  printf 'gateway=BLOCKED reason=%s\n' "$1" >&2
  exit 1
}

valid_client_key() {
  [ -n "$1" ] && printf '%s' "$1" | LC_ALL=C grep -Eq '^[A-Za-z0-9._/+=:-]{32,512}$'
}

valid_provider_key() {
  [ -n "$1" ] && printf '%s' "$1" | LC_ALL=C grep -Eq '^[A-Za-z0-9._/+=:-]{20,512}$'
}

# The public candidate never synchronizes OAuth/session files to Git.
if [ -n "${GITSTORE_GIT_URL:-}" ] || [ -n "${GITSTORE_GIT_TOKEN:-}" ] ||
   [ -n "${GITSTORE_GIT_USERNAME:-}" ] || [ -n "${MANAGEMENT_PASSWORD:-}" ] ||
   [ -n "${PGSTORE_DSN:-}" ] || [ -n "${OBJECTSTORE_ENDPOINT:-}" ]; then
  fail 'legacy_credentials_or_storage_not_allowed'
fi

port="${PORT:-10000}"
case "$port" in ''|*[!0-9]*) fail 'invalid_port' ;; esac
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail 'invalid_port'

root="${CPA_RUNTIME_DIR:-/tmp/truthrail-llm}"
case "$root" in
  /*) ;;
  *) fail 'runtime_dir_must_be_absolute' ;;
esac
printf '%s' "$root" | LC_ALL=C grep -Eq '^/[A-Za-z0-9_./-]+$' || fail 'invalid_runtime_dir'
case "$root" in *..*) fail 'runtime_parent_path_forbidden' ;; esac

sealed=1
if [ -n "${CPA_OPENCODE_GO_API_KEY:-}" ]; then
  valid_provider_key "$CPA_OPENCODE_GO_API_KEY" || fail 'invalid_opencode_credential_format'
  sealed=0
fi

# Luna is an explicit, individually reviewed coding-only Responses opt-in.
# Invalid or empty input must never silently select or enable a model.
luna_mode="${CPA_OPENCODE_GO_LUNA_ENABLED-0}"
case "$luna_mode" in
  0|1) ;;
  *) fail 'invalid_luna_opt_in' ;;
esac
if [ "$luna_mode" = 1 ] && [ "$sealed" = 1 ]; then
  fail 'luna_requires_existing_upstream_key'
fi
if [ "${CPA_OPENCODE_GO_RESPONSES_MODELS+x}" = x ] ||
   [ "${CPA_OPENCODE_GO_MESSAGES_MODELS+x}" = x ]; then
  fail 'dynamic_protocol_model_selection_not_reviewed'
fi

if [ -z "${CPA_CLIENT_API_KEY:-}" ]; then
  # Sealed mode is health-only: inaccessible random client key, no upstream.
  [ "$sealed" = 1 ] || fail 'client_key_required_for_upstream'
  CPA_CLIENT_API_KEY="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
fi
valid_client_key "$CPA_CLIENT_API_KEY" || fail 'invalid_client_key_format'

case "$(printf '%s' "$CPA_CLIENT_API_KEY" | LC_ALL=C tr '[:upper:]' '[:lower:]')" in
  *example*|*placeholder*|*your-api-key*|*sk-test*|*test-key*) fail 'example_client_key_forbidden' ;;
esac

mkdir -p "$root/auth" || fail 'cannot_create_runtime'
chmod 700 "$root" "$root/auth"
tmp="$(mktemp "$root/.cfg.XXXXXX")" || fail 'cannot_create_private_config'
trap 'rm -f "$tmp"' EXIT HUP INT TERM

{
  printf 'config-version: 8\n'
  printf 'server:\n  host: ""\n  port: %s\n' "$port"
  printf 'management:\n  allow-remote: false\n  secret-key: ""\n  disable-control-panel: true\n'
  printf 'access:\n  api-keys:\n    - "%s"\n' "$CPA_CLIENT_API_KEY"
  printf 'oauth:\n  auth-dir: "%s/auth"\n' "$root"
  printf 'routing:\n  retry:\n    request-retry: 0\n'
  if [ "$luna_mode" = 1 ]; then
    # This switch is instance-wide; a live rollout needs GLM coexistence review.
    printf 'multimedia:\n  disable-image-generation: passthrough\n'
  fi
  if [ "$sealed" = 1 ]; then
    printf 'api-keys: {}\n'
  else
    printf 'api-keys:\n  openai-compatibility:\n'
    printf '    - name: "opencode-go-coding"\n'
    printf '      prefix: "opencode-go"\n'
    printf '      base-url: "https://opencode.ai/inference/go/openai/v1"\n'
    printf '      request-retry: 0\n'
    printf '      headers:\n        X-OpenCode-Session: "$X-OpenCode-Session"\n'
    printf '        User-Agent: "Truthrail-Coding-Agent/1.0"\n'
    printf '      keys:\n        - api-key: "%s"\n' "$CPA_OPENCODE_GO_API_KEY"
    printf '      models:\n        - name: "glm-5.3-flash"\n          alias: "glm-5.3-flash"\n'
    if [ "$luna_mode" = 1 ]; then
      # Same authorized Go reseller key, but a separate Responses-capable provider.
      printf '  codex:\n    - name: "opencode-go-luna-coding"\n'
      printf '      prefix: "opencode-go"\n'
      printf '      base-url: "https://opencode.ai/inference/go/openai/v1"\n'
      printf '      request-retry: 0\n'
      printf '      headers:\n        X-OpenCode-Session: "$X-OpenCode-Session"\n'
      printf '        User-Agent: "Truthrail-Coding-Agent/1.0"\n'
      printf '      keys:\n        - api-key: "%s"\n          disable-codex-cloaking: true\n' "$CPA_OPENCODE_GO_API_KEY"
      printf '      models:\n        - name: "gpt-6-luna"\n          alias: "gpt-6-luna"\n'
    fi

  fi
} > "$tmp"

chmod 600 "$tmp"
mv "$tmp" "$root/config.yaml"
trap - EXIT HUP INT TERM

unset CPA_CLIENT_API_KEY CPA_OPENCODE_GO_API_KEY CPA_OPENCODE_GO_LUNA_ENABLED

if [ "${CPA_VALIDATE_ONLY:-}" = 1 ]; then
  if [ "$sealed" = 1 ]; then
    printf 'gateway=SEALED provider_count=0\n'
  else
    if [ "$luna_mode" = 1 ]; then
      printf 'gateway=CONFIGURED provider_count=2 models=opencode-go/glm-5.3-flash,opencode-go/gpt-6-luna opt_in=true\n'
    else
      printf 'gateway=CONFIGURED provider_count=1 model=opencode-go/glm-5.3-flash\n'
    fi
  fi
  exit 0
fi

if [ "$sealed" = 1 ]; then
  printf 'gateway=SEALED upstream_not_configured\n'
else
  printf 'gateway=STARTING model=opencode-go/glm-5.3-flash\n'
  if [ "$luna_mode" = 1 ]; then
    printf 'gateway=LUNA_STAGED model=opencode-go/gpt-6-luna coding_only=true\n'
  fi
fi
exec /CLIProxyAPI/CLIProxyAPI --config "$root/config.yaml"
