# Truthrail LLM Gateway: staged GPT 6 Luna Responses route

**Source integration only. The already verified Render GLM service is not
replaced, redeployed, or granted a new model by this document or PR.**

Canonical deployment and credential owner: the publicly sanitized source
repository Dmitry-dev-pet/truthrail-llm-gateway, which is already served from
https://truthrail-llm-gateway.onrender.com/v1 on Render.
Its existing verified model is OpenCode Go / Z.ai glm-5.3-flash through
OpenAI Chat Completions, with a separate owner-authorized Python review
workflow. The retired private Dimkin33/cli-config work is **reference
evidence only**, not the deployment source or a second runtime.

## One process, two protocols, one stable Truthrail LLM capability

Default: CPA_OPENCODE_GO_LUNA_ENABLED is **unset**. Existing GLM-only
source generation, protected downstream client key, original OpenCode
Go upstream credential, network listener and sealed no-provider mode
must be unchanged.

Optional exact value: CPA_OPENCODE_GO_LUNA_ENABLED=1. Only after explicit
operator approval and deployment does the existing binary register:

| Route | API family | Upstream model | Client model |
| --- | --- | --- | --- |
| Existing GLM | Chat Completions via openai-compatibility | glm-5.3-flash | opencode-go/glm-5.3-flash |
| Opt-in Luna | Responses via codex API-key | gpt-6-luna | opencode-go/gpt-6-luna |

The provider is the *same* separately approved OpenCode Go API-key
credential already held in Render's protected environment. No new
credential, GitStore, AGY subscription OAuth, Telegram session, or user
inference entitlement is implied. The Dockerfile pins CLIProxyAPI
v8.0.13 by the same immutable image digest as the existing service.

Unknown flag values (including explicit empty) fail before any runtime
config is written. The exact Luna route requires **both** the original
upstream credential and protected downstream key. Unknown model IDs,
Responses model-list injection and Anthropic Messages model lists are
not accepted. Default fallback remains deny. Extra retries remain zero.

## Why this is not a general-purpose AI endpoint

The OpenCode Go route is for coding-agent tasks under its own subscription
terms. Direct one-shot OpenCode Go Luna inference was verified through
the original it-mentor sandbox key at
https://github.com/Dmitry-dev-pet/it-mentor/actions/runs/38826372714
(61 input, 31 output tokens). That direct API test did **not** grant
general Truthrail routing or permission to send private/newspaper content.

The actual pinned CLIProxyAPI codex adapter previously passed an isolated
synthetic Responses test at
https://github.com/Dimkin33/cli-config/actions/runs/38835860810.
This implementation in the **working** gateway must pass its own
two-protocol mock test before any integration is accepted.

The existing restricted review workflow
https://github.com/Dmitry-dev-pet/it-mentor/issues/84
remains fixed to glm-5.3-flash. No Issue field may select Luna or send
arbitrary private data until reviewed Truthrail contract and recipient
approval are recorded.

## Instance-wide side-effect to review explicitly

The pinned Codex executor normally rewrites the coding User-Agent and can
inject an unrequested image_generation tool. Synthetic findings showed
two independent controls are required:

1. The Luna API key is configured with disable-codex-cloaking: true
   (**per-key**) to preserve the approved coding-agent identity.
2. When and ONLY when the Luna flag is enabled, the source config sets
   multimedia.disable-image-generation: passthrough, which is
   **instance-wide**. It prevents injecting a tool not provided by the
   client. This can also influence other model/provider behavior on the
   same instance.

There is NO reason to create a new Mac-hosted proxy. A separate internal
Responses **instance of the same existing gateway source on Render** may
be considered ONLY if shared-instance regression tests demonstrate that
the instance-wide setting breaks existing GLM workflows. That would be
a separate reviewed deployment change, not a new top-level Truthrail
capability, model, or orchestration agent.

## Verifications before deployment

1. Review the GitHub PR, exact source and pinned Docker digest. Run all
   existing tests and new fail-closed opt-in tests.
2. Boot the real pinned binary on an isolated Docker network using
   synthetic client/provider keys and a local mock upstream. The exact
   routes must receive ONE GLM Chat Completions request and ONE Luna
   Responses request. Test no fallback, unchanged model names, stable
   provider identity, exact per-model session headers and no unsolicited
   tools. Reject anonymous clients BEFORE any upstream read.
3. Only after these pass, the owner may authorize staging deployment
   to Render. Existing Render service auto-deploy is OFF; merging a PR
   does not alter live credentials or configured models.
4. For the real activation, set CPA_OPENCODE_GO_LUNA_ENABLED=1 in
   the protected Render runtime environment and redeploy the pinned
   reviewed source. **Do not paste any upstream or client key into Git,
   Issues, CI, chat, or artifacts.** Use the already provisioned protected
   environment, with no second export from it-mentor.
5. Verify authenticated GET /v1/models behind the **existing**
   downstream client key. It must include existing GLM and exact
   gpt-6-luna, and nothing else; anonymous requests must remain 401.
6. Independently authorize **one** small coding-only Luna request
   through that actual Render proxy. Record only protocol, fixed
   publisher/provider/model, result status, token counts and source
   commit, not prompts, replies, headers, or secret values.
7. Also run a separately authorized existing GLM coding-review
   acceptance check on the newly deployed image, verifying that the
   conditional media config did not break GLM. A prior success from
   an earlier deployment is insufficient.
8. Only when both pass may Truthrail register an explicitly reviewed
   Luna route with classification, recipient/permission, cost,
   quota/retention and approved invoker rules. No generic ChatGPT
   use or autonomous news inference is implied.

## Failure and rollback

If Luna fails, returns an unrecognized model, alters GLM behavior,
loses an authentication check, hits quota, or injects tools, leave
Truthrail Luna routing BLOCKED. First disable the flag and redeploy
the earlier reviewed GLM-only source. Verify GLM with its known
bounded acceptance path; do not silently switch provider, retry an
upstream, or disable client authentication. Changing the flag is an
operator action, not a model decision.

This candidate avoids additional Mac/VPS dependencies and continues
to use the already live Render LLM gateway.
