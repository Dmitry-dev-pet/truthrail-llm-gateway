# Truthrail LLM Gateway source contract

This public repository is a sanitized source-only release target. It is not a
credential store, a Truthrail user-instance, or an autonomous agent.

- Keep the public repository free of secrets, OAuth sessions, or personal/private repository state.
- Never add real credentials to source, workflows, tests, Docker image, Git history, or Issues.
- Keep the gateway fail-closed: missing upstream means no model is registered.
- Preserve a private runtime config with restricted file modes and disabled remote management.
- Keep the existing verified GLM-5.3-Flash coding model unchanged by default.
- A separate GPT 6 Luna Responses adapter may be prepared in source, but it
  must remain OFF unless an owner-reviewed explicit opt-in, same-instance
  GLM coexistence verification, authenticated Render coding inference and
  Truthrail route/recipient approval all succeed. Never treat a synthetic
  mock response as live provider inference or deployment acceptance.
- Do not automatically add provider models or copy OpenCode/AGY credentials.
- Require a stable caller-provided `X-OpenCode-Session` forwarded to the provider.
- Never invent a session ID or silently change the model/provider.
- Work through branch, PR, green CI, and source-linked verification before merge.
- Production Render activation requires runtime secrets and a real inference smoke;
  source CI alone never proves provider entitlement.

- See `docs/LUNA_RESPONSES_ROLLOUT.md` for exact activation/rollback gates.
