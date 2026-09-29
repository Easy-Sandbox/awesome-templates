# codex-agent-api

**Self-hosted OpenAI Agents API compatible service powered by Codex CLI.**

`codex-agent-api` turns an Easy Sandbox instance into a fully self-hosted,
OpenAI Agents API-compatible service. Each sandbox runs a lightweight HTTP
adapter on port `9000` that exposes the `/v1/agents/sessions/*` surface and
internally drives [Codex CLI](https://www.npmjs.com/package/@openai/codex)
in headless mode (`codex exec --json`) for LLM orchestration.

## Key Feature: Drop-in OpenAI Compatibility

The service is **100% compatible with the OpenAI Agents API specification**
for the sessions surface. To use it, you only need to **switch the
`base_url`** of your existing OpenAI SDK client — no code changes, no
vendor-specific SDKs:

```python
from openai import OpenAI

# Before: OpenAI cloud
client = OpenAI()

# After: your self-hosted sandbox — only base_url changes
client = OpenAI(base_url="http://<sandbox-host>:9000/v1")
```

Your `OPENAI_API_KEY` is still used — it is forwarded to Codex CLI, which
calls the OpenAI API under the hood. The sandbox itself is the API gateway.

## Environment

| Category | Details |
|----------|---------|
| **OS** | Ubuntu 22.04 |
| **Python** | Python 3 + venv at `/opt/venv` (preinstalled: `openai>=1.0`, `rich`, `httpx`) |
| **Node.js** | Node.js 22.x + npm |
| **Agent runtime** | `@openai/codex` (Codex CLI) |
| **System tools** | git, curl, wget, build-essential, ripgrep, jq |
| **Resources** | 2 CPU / 4096 MB memory |
| **Service port** | `9000` (SandboxServer, stdlib-only HTTP) |

## Installation

Install the template from the awesome-templates registry:

```bash
ebx install Easy-Sandbox/awesome-templates//codex-agent-api
```

Then create a sandbox from it (see Quick Start below).

## Quick Start

**Step 1 — Create a sandbox with your API key:**

```bash
ebx create --template codex-agent-api --env OPENAI_API_KEY=sk-xxx
```

**Step 2 — Point the OpenAI SDK at the sandbox:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<sandbox-host>:9000/v1",
    api_key="sk-xxx",  # forwarded to Codex CLI / OpenAI
)

session = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="Write hello world in Python",
    stream=True,
)

for event in session:
    print(event.type, event.data)
```

That's it — standard Agents API semantics, served from your own sandbox.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key used by Codex CLI for model calls. Always inject via `--env`, never hardcode. |
| `CODEX_MODEL` | No | `codex-mini` | Default Codex model for new sessions. Can be overridden per session via `agent.model`. |
| `AGENT_MAX_SESSIONS` | No | `20` | Maximum number of concurrent sessions (429 when exceeded). |
| `AGENT_SESSION_TTL` | No | `1800` | Session idle TTL in seconds; expired sessions are garbage-collected. |
| `CODEX_SANDBOX_MODE` | No | `true` | Marker indicating the agent runs inside an Easy Sandbox. |
| `WORKSPACE` | No | `/workspace` | Working directory for Codex turns. |

## API Reference

All 8 endpoints follow the OpenAI Agents API sessions surface:

| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | `POST` | `/v1/agents/sessions` | Create a session; optionally run a first turn (`input`, `stream`). |
| 2 | `GET` | `/v1/agents/sessions` | List all active sessions. |
| 3 | `GET` | `/v1/agents/sessions/{session_id}` | Retrieve a session (includes recent output items and usage). |
| 4 | `POST` | `/v1/agents/sessions/{session_id}` | Update session configuration (`model`, `instructions`). |
| 5 | `DELETE` | `/v1/agents/sessions/{session_id}` | Delete a session and terminate any live turn. |
| 6 | `POST` | `/v1/agents/sessions/{session_id}/events` | Send user input to a session and start a new turn (SSE by default). |
| 7 | `GET` | `/v1/agents/sessions/{session_id}/events` | Subscribe to the SSE event stream of the active turn. |
| 8 | `GET` | `/v1/agents/sessions/{session_id}/items` | List the output items accumulated by a session. |

In addition, all standard Easy Sandbox endpoints remain available
(`/health`, `/commands`, `/files/*`, `/process/*`, `/system/*`).

## Usage Examples

### curl

Create a session and stream the first turn (SSE):

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{
        "agent": {"model": "codex-mini"},
        "input": "Write hello world in Python",
        "stream": true
      }'
```

Send follow-up input to an existing session:

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/events \
  -H "Content-Type: application/json" \
  -d '{"input": "Now add a unit test"}'
```

List sessions:

```bash
curl http://<sandbox-host>:9000/v1/agents/sessions
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<sandbox-host>:9000/v1",
    api_key="sk-xxx",
)

# Streaming session
stream = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="Write hello world in Python",
    stream=True,
)
for event in stream:
    print(event.type, event.data)

# Non-streaming session
session = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="What is 2 + 2?",
)
print(session.status, session.output)

# Follow-up turn
for event in client.beta.agents.sessions.events.create(
    session_id=session.id,
    input="Now explain it to a child",
    stream=True,
):
    print(event.type, event.data)

# Inspect accumulated items
items = client.beta.agents.sessions.items.list(session_id=session.id)
for item in items.data:
    print(item)

# Clean up
client.beta.agents.sessions.delete(session_id=session.id)
```

### JavaScript / TypeScript (openai SDK)

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://<sandbox-host>:9000/v1",
  apiKey: "sk-xxx",
});

// Streaming session
const stream = await client.beta.agents.sessions.create({
  agent: { model: "codex-mini" },
  input: "Write hello world in TypeScript",
  stream: true,
});

for await (const event of stream) {
  console.log(event.type, event.data);
}
```

## Compatibility Matrix

| Agents API Feature | Supported | Notes |
|--------------------|-----------|-------|
| Create session (`POST /v1/agents/sessions`) | ✅ | With optional first turn (`input`, `stream`). |
| List sessions | ✅ | |
| Get / update / delete session | ✅ | Update supports `model` and `instructions`. |
| Send input / events | ✅ | String input and `agent.session.input.message` content arrays. |
| SSE streaming | ✅ | Full event mapping (see below). |
| Session items | ✅ | Accumulated Codex items (`item.started` / `item.completed`). |
| Multi-turn conversations | ⚠️ Partial | Uses `codex exec resume --last`; state is per-sandbox, best-effort. |
| Custom tools / function calling | ❌ | Tool definitions are accepted but not executed by the adapter. |
| Remote MCP / connectors | ❌ | Not proxied through the adapter. |
| Token usage accounting | ❌ | Placeholder zeros; Codex JSONL usage is not yet parsed. |
| Guardrails / moderations | ❌ | Not implemented. |
| Persistent storage / checkpoints | ❌ | Sessions are in-memory only. |

### Event mapping (Codex JSONL → Agents API SSE)

| Codex event | Agents API event |
|-------------|------------------|
| `thread.started` | `agent.session.created` |
| `turn.started` | `agent.session.turn.started` |
| `turn.completed` | `agent.session.turn.completed` |
| `item.started` | `agent.session.output_item.added` |
| `item.completed` | `agent.session.output_item.done` |
| `message.delta` | `agent.session.output_text.delta` |
| `message.completed` | `agent.session.output_text.done` |
| `error` | `agent.session.turn.failed` |

Unknown Codex event types are passed through as `agent.session.<type>`.

## Known Limitations

- **In-memory sessions** — all session state lives in the adapter process.
  Restarting the sandbox drops every session; there is no persistence or
  checkpointing.
- **Single instance** — the adapter is single-process; sessions are not
  shared across replicas and there is no clustering.
- **One active turn per session** — concurrent input to the same session
  returns `409 Conflict`.
- **Session capacity** — bounded by `AGENT_MAX_SESSIONS` (default 20);
  requests beyond the limit return `429` after expired-session eviction.
- **Turn timeout** — each turn is hard-capped at 300 seconds; the Codex
  process is killed and the turn fails on timeout.
- **`GET .../events` subscription** — attaches to the active turn's stdout;
  it is a best-effort tail, not a replayable event log.
- **Usage / billing metrics** — not reported (placeholder values).
- **Thread-safety of `codex resume`** — multi-turn resume relies on Codex
  CLI session files in `/workspace`; treat it as best-effort.

## Security Notes

- **Never hardcode `OPENAI_API_KEY`.** Always inject it at sandbox creation
  time (`ebx create --env OPENAI_API_KEY=sk-xxx`) or via your secret store.
- The adapter runs Codex with `--sandbox danger-full-access` inside the
  Easy Sandbox container — the sandbox boundary is the isolation layer.
  Do not expose port `9000` to untrusted networks.
- Optional bearer/token auth is inherited from the sandbox server
  (`EBX_SERVER_TOKEN`); set it if the sandbox port is reachable beyond
  your trust boundary.
- Traffic to OpenAI leaves the sandbox over the network; ensure your
  compliance policy allows it.

---

Part of [awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) · Maintained by Easy-Sandbox
