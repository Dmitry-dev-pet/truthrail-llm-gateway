# VPS staging: CLIProxyAPI without provider credentials

This repo owns the same pinned CLIProxyAPI v8.0.13 wrapper as the running
Render gateway. The initial VPS migration is an **isolated, sealed**
deployment: it must not replace the existing Render endpoint, route any LLM
traffic, expose a public listener, or receive OAuth credentials.

## Source-to-image chain

1. Open a same-repository branch and PR; wait for **Gateway validation** CI.
2. Merge to `main` only after review. A successful **push-to-main** gateway
   validation triggers `Publish validated Truthrail LLM gateway to GHCR`.
3. Publishing builds the reviewed pinned image, launches a sealed container,
   checks anonymous inference is denied, then publishes only
   `ghcr.io/dmitry-dev-pet/truthrail-llm-gateway:<full 40-character source SHA>`.
4. The repository-owner-controlled `infra-access` inventory must
   independently register a loopback-only, resource-bounded VPS service.
   Require available disk/memory and a reviewed image before onboarding.
5. Existing Render gateway and MCP remain unchanged while the VPS version is
   sealed. Do not remove Render credentials or rotate shared keys prematurely.

## Future activation is a **separate** security decision

- Route is OpenCode Go **coding-agent only**, fixed
  `opencode-go/glm-5.3-flash`. Luna opt-in remains off; AGY OAuth is forbidden.
- A dedicated, reviewed control-plane operation must provision **only** the
  required private upstream/client credentials into protected VPS runtime state.
  Do not copy secrets through GitHub files, Issues, logs, shell commands or
  chat; do not make a generic SSH/exec or Docker-socket surface.
- The MCP currently runs on Render and points to the Render gateway.
  Loopback on VPS cannot serve it directly. Before a cutover, review a
  scoped HTTPS/private tunnel route and MCP client authorization. Do not
  open TCP 10000 publicly as a shortcut.
- Verify authenticated `/v1/models` read-only, then **one** explicitly
  authorized coding-only inference with rate/cost guardrails. Roll back to
  the unchanged Render route on failure, without automatic LLM retries.
- After successful independent verification, change only the approved MCP
  destination and document the evidence in Truthrail's `llm-routes.yaml`.
- Do not treat a healthy sealed Docker container as proof of an active model.
