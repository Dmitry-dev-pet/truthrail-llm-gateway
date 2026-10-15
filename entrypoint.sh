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
for var in GITSTORE_GIT_URL GITSTORE_GIT_TOKEN GITSTORE_GIT_USERNAME MANAGEMENT_PASSWORD PGSTORE_DSN OBJECTSTORE_ENDPOINT; do
  eval "present=\${$var:-}"
  [ -z "$present" ] || fail 'legacy_credentials_or_storage_not_allowed'
done
unset present

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
  fi
} > "$tmp"

chmod 600 "$tmp"
mv "$tmp" "$root/config.yaml"
trap - EXIT HUP INT TERM

unset CPA_CLIENT_API_KEY CPA_OPENCODE_GO_API_KEY

if [ "${CPA_VALIDATE_ONLY:-}" = 1 ]; then
  if [ "$sealed" = 1 ]; then
    printf 'gateway=SEALED provider_count=0\n'
  else
    printf 'gateway=CONFIGURED provider_count=1 model=opencode-go/glm-5.3-flash\n'
  fi
  exit 0
fi

if [ "$sealed" = 1 ]; then
  printf 'gateway=SEALED upstream_not_configured\n'
else
  printf 'gateway=STARTING model=opencode-go/glm-5.3-flash\n'
fi
exec /CLIProxyAPI/CLIProxyAPI --config "$root/config.yaml"
