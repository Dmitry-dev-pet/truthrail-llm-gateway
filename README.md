# Truthrail LLM Gateway

A small, secretless Docker source project for an OpenAI-compatible
authenticated LLM gateway, designed to run on Render without copying an old
private Git repository or its credential-bearing history.

**Status:** Source must pass CI and container verification before deployment.

## How it works

- Uses a pinned CLIProxyAPI v8.0.13 base-image digest.
- Generates its runtime configuration from Render's protected environment.
- Access requires an API client key, separate from any upstream provider key.
- Management access, OAuth/GitStore, and unreviewed token stores are disabled.
- Only the OpenCode Go coding model `glm-5.3-flash` is configured when its
  credential is present. No model switching or fallback is enabled.
- `X-OpenCode-Session` is passed through from the authenticated client to
  support stable coding-agent conversation identity.

## Sealed first deploy

The container supports a secure bootstrap **without any provider credentials**.
It generates a random temporary client key, configures zero upstream models,
and listens on Render's `PORT`. The key is never logged, so this state cannot
be used for inference. This is a deployment/health validation mode, not a
claim that OpenCode Go works through Render.

Once at least one upstream credential is supplied, the service fails closed
unless `CPA_CLIENT_API_KEY` is also supplied. This prevents accidentally
publishing a model endpoint without authentication.

## Production secrets

Configure both values in **Render Environment** or in a separately reviewed
secret transfer operation. Never put them into GitHub source or a prompt:

| Variable | Meaning |
| --- | --- |
| `CPA_CLIENT_API_KEY` | Fresh high-entropy key for callers to this gateway |
| `CPA_OPENCODE_GO_API_KEY` | OpenCode Go provider key for coding-agent traffic |
| `PORT` | Render public listener port (defaults to 10000) |

Render's `render.yaml` can generate the client key and request the upstream
key privately when a Blueprint is first applied. An existing GitHub Actions
secret cannot simply be read through a connector: secret transfer requires
a reviewed workflow and Render-side authority, or the owner may supply a key
directly in the protected Render Environment editor.

## Public code, private credentials

The repository is public by design and contains only the sanitized source.
No historical auth files, internal tokens, or personal configuration are
copied. The upstream endpoint and model ID are public information.

OpenCode Go is intended for coding agents. This gateway does not authorize
arbitrary unrelated prompts, even though the underlying HTTP protocol accepts
chat-style requests. Callers must use the approved coding-only task scope.

## Staged GPT 6 Luna Responses model (NOT deployed)

The existing Render gateway still serves the verified GLM coding route
unless the operator explicitly sets `CPA_OPENCODE_GO_LUNA_ENABLED=1`
**after review**. The exact flag adds `opencode-go/gpt-6-luna` through
CLIProxyAPI's native `codex` Responses provider alongside the unchanged
GLM Chat Completions model; invalid flags or missing keys fail closed.

The Codex adapter requires per-key disable-codex-cloaking and an
**instance-wide** image-generation passthrough setting, so a real dual-model
smoke and GLM regression check are mandatory before changing the
production Render environment. It does not permit automatic news
summarization, generic model inference, AGY OAuth use or arbitrary
provider/model fallback. The current `render.yaml` has autoDeploy OFF.

See [the Luna protocol and rollback runbook](docs/LUNA_RESPONSES_ROLLOUT.md).

## Tests

```sh
sh -n entrypoint.sh
python3 -m pip install -r requirements-test.txt
python3 -m unittest discover -s tests -v
docker build -t truthrail-gateway:test .
```

CI additionally boots an isolated sealed container, checks HTTP readiness
and rejects unauthenticated inference. Real provider inference is a separate
post-deployment acceptance test.

## Deployment

Use the GitHub repo as Render's `runtime: docker` source, with Dockerfile
`Dockerfile` and Docker context `.`. A separate free service in Frankfurt
is preferred for the first smoke so the historical image-backed service
can remain untouched. After authentication, validate both the client-key
boundary and one exact-model, session-aware coding inference.
