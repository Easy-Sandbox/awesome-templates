# codex-agent-api

> [中文版](#中文) | [English](#english)

---

## English

**Self-hosted OpenAI Agents API compatible service powered by Codex CLI.**

`codex-agent-api` turns an Easy Sandbox instance into a fully self-hosted,
OpenAI Agents API-compatible service. Each sandbox runs a lightweight HTTP
adapter on port `9000` that exposes the `/v1/agents/*` surface (sessions,
saved agents, artifacts) and internally drives
[Codex CLI](https://www.npmjs.com/package/@openai/codex)
in headless mode (`codex exec --json`) for LLM orchestration.

### Key Feature: Drop-in OpenAI Compatibility

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

### Environment

| Category | Details |
|----------|---------|
| **OS** | Ubuntu 22.04 |
| **Python** | Python 3 + venv at `/opt/venv` (preinstalled: `openai>=1.0`, `rich`, `httpx`) |
| **Node.js** | Node.js 22.x + npm |
| **Agent runtime** | `@openai/codex` (Codex CLI) |
| **System tools** | git, curl, wget, build-essential, ripgrep, jq |
| **Resources** | 2 CPU / 4096 MB memory |
| **Service port** | `9000` (SandboxServer, stdlib-only HTTP) |

### Installation

Install the template from the awesome-templates registry:

```bash
ebx install Easy-Sandbox/awesome-templates//codex-agent-api
```

Then create a sandbox from it (see Quick Start below).

### Quick Start

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

### Quick Start with Easy Sandbox SDK

The full pipeline — install the template, create a sandbox, call the API —
works with either the `ebx` CLI or the Easy Sandbox Python SDK.

#### CLI way

```bash
# 1. Install the template from the awesome-templates registry
ebx install Easy-Sandbox/awesome-templates//codex-agent-api

# 2. Create a sandbox from the template, injecting your API key
ebx create --template codex-agent-api --env OPENAI_API_KEY=sk-xxx

# 3. Find the sandbox host/port (or use `ebx sandbox list`)
ebx list

# 4. Test the API with curl
curl http://<sandbox-host>:9000/v1/agents
```

#### Python SDK way

```python
import asyncio

import httpx
from openai import OpenAI

from easy_sandbox import Sandbox


async def main() -> None:
    # 1. Create the sandbox from the template, injecting the API key
    sandbox = await Sandbox.create(
        template="codex-agent-api",
        envs={"OPENAI_API_KEY": "sk-xxx"},
        timeout=600,
    )
    try:
        # 2. Compute the host that exposes the service on port 9000
        base_url = sandbox.network.get_url(port=9000)
        headers = sandbox.network.get_access_headers()  # {} unless EBX_SERVER_TOKEN is set

        # Way 1 — OpenAI SDK: only the base_url changes
        client = OpenAI(base_url=f"{base_url}/v1", api_key="sk-xxx")
        session = client.beta.agents.sessions.create(
            agent={"model": "codex-mini"},
            input="Write hello world in Python",
        )
        print(session.status, session.output)

        # Way 2 — httpx directly against the REST surface
        resp = httpx.post(
            f"{base_url}/v1/agents/sessions",
            json={"agent": {"model": "codex-mini"}, "input": "Hello!"},
            headers=headers,
        )
        print(resp.json())
    finally:
        # 3. Clean up
        await sandbox.kill()


asyncio.run(main())
```

> Note: in secure mode, port access requires the `X-Access-Token` header
> returned by `sandbox.network.get_access_headers()` — the example passes it
> to `httpx` for that reason.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key used by Codex CLI for model calls. Always inject via `--env`, never hardcode. |
| `CODEX_MODEL` | No | `codex-mini` | Default Codex model for new sessions. Can be overridden per session via `agent.model`. |
| `AGENT_MAX_SESSIONS` | No | `20` | Maximum number of concurrent sessions (429 when exceeded). |
| `AGENT_SESSION_TTL` | No | `1800` | Session idle TTL in seconds; expired sessions are garbage-collected. |
| `CODEX_SANDBOX_MODE` | No | `true` | Marker indicating the agent runs inside an Easy Sandbox. |
| `WORKSPACE` | No | `/workspace` | Working directory for Codex turns. |

### API Reference

All 15 endpoints follow the OpenAI Agents API agents & sessions surfaces:

| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | `POST` | `/v1/agents/sessions` | Create a session; optionally run a first turn (`input`, `stream`). Accepts an inline `agent` dict **or** a saved `agent_id` string. |
| 2 | `GET` | `/v1/agents/sessions` | List all active sessions. |
| 3 | `GET` | `/v1/agents/sessions/{session_id}` | Retrieve a session (includes recent output items and usage). |
| 4 | `POST` | `/v1/agents/sessions/{session_id}` | Update session configuration (`model`, `instructions`). |
| 5 | `DELETE` | `/v1/agents/sessions/{session_id}` | Delete a session and terminate any live turn. |
| 6 | `POST` | `/v1/agents/sessions/{session_id}/events` | Send user input to a session and start a new turn (SSE by default). |
| 7 | `GET` | `/v1/agents/sessions/{session_id}/events` | Subscribe to the SSE event stream of the active turn. |
| 8 | `GET` | `/v1/agents/sessions/{session_id}/items` | List the output items accumulated by a session. |
| 9 | `POST` | `/v1/agents` | Create a reusable agent configuration (`model`, `instructions`, `tools`, `name`, `metadata`). |
| 10 | `GET` | `/v1/agents` | List all saved agents. |
| 11 | `GET` | `/v1/agents/{agent_id}` | Retrieve a saved agent by ID. |
| 12 | `POST` | `/v1/agents/{agent_id}` | Update a saved agent (`model`, `instructions`, `tools`, `name`, `metadata`). |
| 13 | `DELETE` | `/v1/agents/{agent_id}` | Delete a saved agent. |
| 14 | `GET` | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | Download a workspace file artifact produced during the session. |
| 15 | `DELETE` | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | Delete a workspace file artifact. |

In addition, all standard Easy Sandbox endpoints remain available
(`/health`, `/commands`, `/files/*`, `/process/*`, `/system/*`).

#### Request & Response Conventions

- **Base URL** — examples below use `http://localhost:9000`; substitute your mapped sandbox host and port.
- **Auth** — when `EBX_SERVER_TOKEN` is set on the sandbox, add `-H "X-Access-Token: <token>"` to every request; when unset, no auth is required.
- **Success** — every successful call returns HTTP `200` (the stdlib server has no `201`/`204` surface); deletes return `200` with `{"deleted": true}`.
- **Errors** — JSON body `{"error": "<message>", "type": "<ErrorClass>"}`. Common generic codes: `400` invalid JSON body, `401` token configured but header missing/invalid, `413` body too large.

#### SSE Event Streams

Streaming endpoints answer with `Content-Type: text/event-stream`. Each frame is one event, written line by line as an `event:` line, a `data:` line holding one JSON object, then a blank line:

```
event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

```

Event names: `agent.session.created`, `agent.session.turn.started`, `agent.session.turn.completed`, `agent.session.turn.failed`, `agent.session.output_item.added`, `agent.session.output_item.done`, `agent.session.output_text.delta`, `agent.session.output_text.done`; unknown Codex events pass through as `agent.session.<type>`. See the event mapping table for the Codex → SSE correspondence.

#### Group 1 — Agents CRUD

##### `POST /v1/agents` — Create Agent

Create a reusable agent configuration that sessions can reference by ID.

**Request body** (all fields optional):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `codex-mini` (`$CODEX_MODEL`) | Codex model used for turns. |
| `instructions` | string | `""` | Instruction text stored with the agent. |
| `tools` | array | `[]` | Tool definitions; URL-based `mcp` entries are mapped into Codex. |
| `name` | string | `""` | Human-readable label. |
| `metadata` | object | `{}` | Arbitrary client metadata, echoed back. |

```bash
curl http://localhost:9000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"model": "codex-mini", "instructions": "You are a Python expert.", "name": "py-expert"}'
```

**Response** `200`:

```json
{
  "id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d",
  "object": "agent",
  "model": "codex-mini",
  "instructions": "You are a Python expert.",
  "tools": [],
  "name": "py-expert",
  "metadata": {},
  "created_at": 1790640000
}
```

**Status codes**: `200` success · `400` invalid JSON body.

##### `GET /v1/agents` — List Agents

List all saved agents.

```bash
curl http://localhost:9000/v1/agents
```

**Response** `200`:

```json
{
  "object": "list",
  "data": [
    {
      "id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d",
      "object": "agent",
      "model": "codex-mini",
      "instructions": "You are a Python expert.",
      "tools": [],
      "name": "py-expert",
      "metadata": {},
      "created_at": 1790640000
    }
  ]
}
```

`data` is `[]` when no agent has been saved. **Status codes**: `200` success.

##### `GET /v1/agents/{agent_id}` — Get Agent

Retrieve one saved agent by ID.

```bash
curl http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d
```

**Response** `200`: the agent object shown under Create Agent.

**Status codes**: `200` success · `404` `{"error": "Agent agent_9f2c1b8e4d7a4c3f8b1e6a2d not found", "type": "NotFoundError"}`.

##### `POST /v1/agents/{agent_id}` — Update Agent

Partially update a saved agent. Only `model`, `instructions`, `tools`, `name` and `metadata` are applied; unknown keys are ignored, and `id` / `object` / `created_at` are immutable.

**Request body** — include only the fields to change:

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Replacement model. |
| `instructions` | string | Replacement instruction text. |
| `tools` | array | Replacement tool definitions. |
| `name` | string | Replacement label. |
| `metadata` | object | Replacement metadata. |

```bash
curl http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d \
  -H "Content-Type: application/json" \
  -d '{"name": "py-expert-v2", "instructions": "Answer with code first."}'
```

**Response** `200`: the updated agent object; fields not included in the request keep their previous values.

**Status codes**: `200` success · `400` invalid JSON body · `404` agent not found.

##### `DELETE /v1/agents/{agent_id}` — Delete Agent

Delete a saved agent. Sessions already created from it are unaffected.

```bash
curl -X DELETE http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d
```

**Response** `200`:

```json
{"id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d", "object": "agent", "deleted": true}
```

**Status codes**: `200` success · `404` agent not found.

#### Group 2 — Sessions

##### `POST /v1/agents/sessions` — Create Session

Create a session; optionally run a first turn by passing `input`.

**Request body** (all fields optional):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent` | object \| string | `{}` | Inline agent config (`model`, `instructions`, `tools`) or the ID of a saved agent; an unknown ID returns `404`. |
| `input` | string \| array | — | User input for the first turn (forms below). Omit to create the session without running a turn. |
| `stream` | boolean | `false` | `true` → SSE stream (first turn); `false` with `input` → block until the turn ends, then return the session JSON. |

Supported `input` forms (same on the events endpoint):

```json
{"input": "Write hello world in Python"}
{"input": [{"type": "input_text", "text": "Write hello world in Python"}]}
{"type": "agent.session.input.message", "content": [{"type": "input_text", "text": "Write hello world in Python"}]}
```

```bash
# create only — no turn is started
curl http://localhost:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": {"model": "codex-mini", "instructions": "Reply concisely."}}'

# create + first turn, streamed as SSE
curl -N http://localhost:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": {"model": "codex-mini"}, "input": "Write hello world in Python", "stream": true}'
```

**Response** `200` (create-only):

```json
{
  "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "object": "session",
  "status": "idle",
  "model": "codex-mini",
  "instructions": "Reply concisely.",
  "tools": [],
  "created_at": 1790640000,
  "metadata": {}
}
```

**Response** `200` (`input` with `stream: false`) — the session object plus `output` (last 5 accumulated items) and `usage`:

```json
{
  "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "object": "session",
  "status": "idle",
  "model": "codex-mini",
  "instructions": "Reply concisely.",
  "tools": [],
  "created_at": 1790640000,
  "metadata": {},
  "output": [
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "print(\"Hello, world!\")"}}
  ],
  "usage": {"input_tokens": 1352, "output_tokens": 29}
}
```

**Response** (`stream: true`) — SSE frames, in order:

```
event: agent.session.created
data: {"id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "object": "session", "status": "in_progress", "model": "codex-mini", "instructions": "", "tools": [], "created_at": 1790640000, "metadata": {}}

event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

event: agent.session.turn.completed
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "status": "completed"}
```

Mapped Codex events (`agent.session.output_item.*`, `agent.session.output_text.*`) appear between the two turn frames.

**Status codes**: `200` success · `400` invalid JSON body · `404` saved `agent` ID not found · `429` `{"error": "Too many active sessions", "type": "CapacityError"}` · `500` Codex process could not be spawned.

##### `GET /v1/agents/sessions` — List Sessions

List all active sessions (metadata only — no `output` / `usage`).

```bash
curl http://localhost:9000/v1/agents/sessions
```

**Response** `200`:

```json
{
  "object": "list",
  "data": [
    {
      "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
      "object": "session",
      "status": "idle",
      "model": "codex-mini",
      "instructions": "",
      "tools": [],
      "created_at": 1790640000,
      "metadata": {}
    }
  ]
}
```

**Status codes**: `200` success.

##### `GET /v1/agents/sessions/{session_id}` — Get Session

Retrieve a session, including its recent output and accumulated usage.

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d
```

**Response** `200`: the session object with `output` (last 5 items) and `usage`, as in the interactive create response above.

**Status codes**: `200` success · `404` session not found.

##### `POST /v1/agents/sessions/{session_id}` — Update Session

Update session configuration. Only `model` and `instructions` are applied.

**Request body** — include only the fields to change:

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Model used by subsequent turns. |
| `instructions` | string | Replacement instruction text. |

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d \
  -H "Content-Type: application/json" \
  -d '{"instructions": "Answer in French."}'
```

**Response** `200`: the updated session object (metadata only — no `output` / `usage`).

**Status codes**: `200` success · `400` invalid JSON body · `404` session not found.

##### `DELETE /v1/agents/sessions/{session_id}` — Delete Session

Delete a session and terminate any live turn process.

```bash
curl -X DELETE http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d
```

**Response** `200`:

```json
{"id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "object": "session", "deleted": true}
```

**Status codes**: `200` success · `404` session not found.

#### Group 3 — Turns & Events

##### `POST /v1/agents/sessions/{session_id}/events` — Send Input (new turn)

Send user input to an existing session and start a new turn. Later turns resume the exact Codex thread recorded from the first turn.

**Request body**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `input` | string \| array | — | **Required.** Same three input forms as session creation. |
| `stream` | boolean | `true` | `true` → SSE stream; `false` → block and return the session JSON. |

```bash
# streamed turn (default)
curl -N http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events \
  -H "Content-Type: application/json" \
  -d '{"input": "Now add a unit test"}'

# synchronous turn
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events \
  -H "Content-Type: application/json" \
  -d '{"input": "Now add a unit test", "stream": false}'
```

**Response** `200` (`stream: false`): the session object with `output` and `usage` (same shape as above).

**Response** (`stream: true`) — SSE frames:

```
event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

event: agent.session.output_item.done
data: {"type": "agent.session.output_item.done", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "item": {"id": "item_1", "type": "agent_message", "text": "Add a pytest case to test_hello.py."}}

event: agent.session.turn.completed
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "status": "completed"}
```

**Status codes**: `200` success · `400` `{"error": "Missing input text", "type": "ValueError"}` · `404` session not found · `409` `{"error": "Session has an active turn", "type": "ConflictError"}` (only one turn may run per session) · `500` spawn failure.

##### `GET /v1/agents/sessions/{session_id}/events` — Subscribe to Events (SSE)

Attach to the event stream of the session's currently running turn. This is a best-effort tail of the live Codex stdout — not a replayable event log.

```bash
curl -N http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events
```

**Response** `200` — JSON instead of SSE when no turn is active:

```json
{"status": "idle", "message": "No active turn"}
```

When a turn is in progress, the response is `text/event-stream` with the remaining mapped events until the turn finishes (same frame format and event names as above).

**Status codes**: `200` success (both branches) · `404` session not found.

#### Group 4 — Items & Artifacts

##### `GET /v1/agents/sessions/{session_id}/items` — List Output Items

List every item accumulated by the session — the raw Codex `item.started` / `item.completed` events, oldest first.

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/items
```

**Response** `200`:

```json
{
  "object": "list",
  "data": [
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "print(\"Hello, world!\")"}}
  ]
}
```

Assistant messages appear as `{"type": "agent_message", "text": "..."}` inside the `item` object; command executions, reasoning and other Codex item types are passed through as-is.

**Status codes**: `200` success · `404` session not found.

##### `GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}` — Download Artifact

Fetch a workspace file as an artifact. `artifact_id` is the URL-safe base64 encoding of the workspace-relative path (padding optional); values that fail to decode are used as plain relative paths, and paths escaping the workspace are rejected.

```bash
artifact_id=$(printf 'report.md' | base64)   # -> cmVwb3J0Lm1k
curl "http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/artifacts/$artifact_id"
```

**Response** `200`:

```json
{
  "id": "cmVwb3J0Lm1k",
  "object": "artifact",
  "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "file_path": "report.md",
  "content": "# Report\n\n...",
  "size": 1234
}
```

`content` is read as UTF-8 text (invalid bytes are replaced); `size` is the file size in bytes.

**Status codes**: `200` success · `403` `{"error": "Access denied: path outside workspace", "type": "ForbiddenError"}` · `404` session not found, or `{"error": "Artifact not found: <path>", "type": "NotFoundError"}` · `500` read failure.

##### `DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id}` — Delete Artifact

Delete a workspace file artifact.

```bash
curl -X DELETE \
  "http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/artifacts/cmVwb3J0Lm1k"
```

**Response** `200`:

```json
{"id": "cmVwb3J0Lm1k", "object": "artifact", "deleted": true}
```

**Status codes**: `200` success · `403` path outside workspace · `404` session or artifact not found · `500` delete failure.

### Usage Examples

#### curl

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

Create a reusable agent, then reference it by ID when creating sessions:

```bash
# 1. Save an agent configuration once
agent_id=$(curl -s http://<sandbox-host>:9000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"model": "codex-mini", "instructions": "You are a Python expert."}' \
  | jq -r .id)

# 2. Reuse it across sessions — `agent` is the saved agent's ID
curl http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": "'"$agent_id"'", "input": "Write hello world in Python"}'
```

Fetch a file artifact produced by a session (the artifact ID is the
URL-safe base64 encoding of its workspace-relative path):

```bash
artifact_id=$(printf 'report.md' | base64)  # -> cmVwb3J0Lm1k
curl http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/artifacts/$artifact_id

# Delete it afterwards
curl -X DELETE \
  http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/artifacts/$artifact_id
```

### Remote MCP tools

Pass URL-based MCP servers through the agent's `tools` array — the adapter
maps them into Codex (`mcp_servers.*`) for every turn of the session:

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{
        "agent": {
          "model": "codex-mini",
          "tools": [
            {
              "type": "mcp",
              "server_label": "deepwiki",
              "server_url": "https://mcp.deepwiki.com/mcp",
              "headers": {"Authorization": "Bearer <token>"}
            }
          ]
        },
        "input": "List the MCP tools you can use",
        "stream": true
      }'
```

Supported fields: `server_label` / `name` (sanitized into a config-safe
label), `server_url` / `url` (flat or nested under `transport`), and
`headers` (forwarded as `http_headers`). Tools without a URL — e.g. hosted
connectors declared by `connector_id` — are skipped.

#### Python (openai SDK)

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

#### JavaScript / TypeScript (openai SDK)

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

### Compatibility Matrix

| Agents API Feature | Supported | Notes |
|--------------------|-----------|-------|
| Create session (`POST /v1/agents/sessions`) | ✅ | With optional first turn (`input`, `stream`). |
| List sessions | ✅ | |
| Get / update / delete session | ✅ | Update supports `model` and `instructions`. |
| Send input / events | ✅ | String input and `agent.session.input.message` content arrays. |
| SSE streaming | ✅ | Full event mapping (see below). |
| Session items | ✅ | Accumulated Codex items (`item.started` / `item.completed`). |
| Saved agents (Agents CRUD) | ✅ | Create/list/get/update/delete reusable agent configs; reference them by ID in `agent`. |
| Artifacts (get / delete) | ✅ | Workspace file artifacts addressed by URL-safe base64-encoded relative paths; paths outside the workspace are rejected (403). |
| Multi-turn conversations | ✅ | Resumes the exact Codex thread recorded from the first turn (`codex exec resume <thread_id> -- <prompt>`), falling back to `resume --last`. Verified against Codex CLI 0.158.0. |
| Custom tools / function calling | ⚠️ Partial | Built-in Codex tools (shell, file edits, MCP) work; custom function callbacks are Phase 2. |
| Remote MCP / connectors | ✅ | URL-based remote MCP servers (`server_url` + `headers`) are mapped into Codex via `-c mcp_servers.*` config overrides. Hosted `connector_id` tools are not proxied and are skipped. |
| Token usage accounting | ✅ | `turn.completed` usage is accumulated per session and reported as `usage.input_tokens` / `usage.output_tokens`. |
| Guardrails / moderations | ❌ | Not implemented. |
| Persistent storage / checkpoints | ❌ | Sessions are in-memory only. |

#### Event mapping (Codex JSONL → Agents API SSE)

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

The `thread_id` of the `thread.started` event is recorded per session and
reused by later turns to resume the exact Codex thread. `turn.completed`
usage is accumulated into the session's `usage` counters.

Unknown Codex event types are passed through as `agent.session.<type>`.

### Known Limitations

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
- **Multi-turn state** — resume relies on Codex session files under
  `$CODEX_HOME` (default `/root/.codex`) inside the sandbox. They are lost
  when the sandbox is recreated, after which a resumed turn fails with the
  Codex error surfaced in the turn-failed event.
- **MCP connectors** — only URL-based remote MCP servers can be proxied;
  hosted `connector_id` tools and custom function callbacks are ignored.

### Security Notes

- **Never hardcode `OPENAI_API_KEY`.** Always inject it at sandbox creation
  time (`ebx create --env OPENAI_API_KEY=sk-xxx`) or via your secret store.
- The adapter runs Codex with
  `--dangerously-bypass-approvals-and-sandbox` inside the Easy Sandbox
  container — the sandbox boundary is the isolation layer. Do not expose
  port `9000` to untrusted networks.
- Optional bearer/token auth is inherited from the sandbox server
  (`EBX_SERVER_TOKEN`); set it if the sandbox port is reachable beyond
  your trust boundary.
- Traffic to OpenAI leaves the sandbox over the network; ensure your
  compliance policy allows it.

---

## 中文

**由 Codex CLI 驱动的自托管 OpenAI Agents API 兼容服务。**

`codex-agent-api` 将 Easy Sandbox 实例变为完全自托管的 OpenAI Agents API
兼容服务。每个沙箱在 `9000` 端口上运行一个轻量级 HTTP 适配器，对外暴露
`/v1/agents/*` 接口（会话、已保存的 Agent、产物），并在内部以无头模式
驱动 [Codex CLI](https://www.npmjs.com/package/@openai/codex)
（`codex exec --json`）完成 LLM 编排。

### 核心特性：开箱即用的 OpenAI 兼容

本服务在会话接口上**与 OpenAI Agents API 规范 100% 兼容**。使用时只需
**替换现有 OpenAI SDK 客户端的 `base_url`**——无需改动代码，也无需
厂商专用 SDK：

```python
from openai import OpenAI

# 之前：OpenAI 云端
client = OpenAI()

# 之后：你的自托管沙箱 —— 只需修改 base_url
client = OpenAI(base_url="http://<sandbox-host>:9000/v1")
```

`OPENAI_API_KEY` 依然会被使用——它会被转发给 Codex CLI，由后者在底层调用
OpenAI API。沙箱本身即是 API 网关。

### 环境说明

| 类别 | 内容 |
|------|------|
| **操作系统** | Ubuntu 22.04 |
| **Python** | Python 3 + venv（位于 `/opt/venv`），预装：`openai>=1.0`、`rich`、`httpx` |
| **Node.js** | Node.js 22.x + npm |
| **Agent 运行时** | `@openai/codex`（Codex CLI） |
| **系统工具** | git、curl、wget、build-essential、ripgrep、jq |
| **资源配置** | 2 CPU / 4096 MB 内存 |
| **服务端口** | `9000`（SandboxServer，仅使用标准库的 HTTP 服务） |

### 安装方式

从 awesome-templates 仓库安装模板：

```bash
ebx install Easy-Sandbox/awesome-templates//codex-agent-api
```

然后基于它创建沙箱（见下方快速开始）。

### 快速开始

**第 1 步 —— 携带 API Key 创建沙箱：**

```bash
ebx create --template codex-agent-api --env OPENAI_API_KEY=sk-xxx
```

**第 2 步 —— 将 OpenAI SDK 指向沙箱：**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<sandbox-host>:9000/v1",
    api_key="sk-xxx",  # 转发给 Codex CLI / OpenAI
)

session = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="用 Python 写一个 hello world",
    stream=True,
)

for event in session:
    print(event.type, event.data)
```

就这么简单——标准的 Agents API 语义，由你自己的沙箱提供服务。

### Easy Sandbox SDK 快速开始

从安装模板、创建沙箱到调用 API 的完整链路，既可以用 `ebx` CLI 完成，也可以
通过 Easy Sandbox Python SDK 完成。

#### CLI 方式

```bash
# 1. 从 awesome-templates 仓库安装模板
ebx install Easy-Sandbox/awesome-templates//codex-agent-api

# 2. 基于模板创建沙箱，注入 API Key
ebx create --template codex-agent-api --env OPENAI_API_KEY=sk-xxx

# 3. 查看沙箱主机与端口（也可以用 `ebx sandbox list`）
ebx list

# 4. 用 curl 测试 API
curl http://<sandbox-host>:9000/v1/agents
```

#### Python SDK 方式

```python
import asyncio

import httpx
from openai import OpenAI

from easy_sandbox import Sandbox


async def main() -> None:
    # 1. 基于模板创建沙箱，注入 API Key
    sandbox = await Sandbox.create(
        template="codex-agent-api",
        envs={"OPENAI_API_KEY": "sk-xxx"},
        timeout=600,
    )
    try:
        # 2. 计算 9000 端口对外暴露的访问地址
        base_url = sandbox.network.get_url(port=9000)
        headers = sandbox.network.get_access_headers()  # 未设置 EBX_SERVER_TOKEN 时为 {}

        # 方式 1 —— OpenAI SDK：只需替换 base_url
        client = OpenAI(base_url=f"{base_url}/v1", api_key="sk-xxx")
        session = client.beta.agents.sessions.create(
            agent={"model": "codex-mini"},
            input="用 Python 写一个 hello world",
        )
        print(session.status, session.output)

        # 方式 2 —— 直接用 httpx 调用 REST 接口
        resp = httpx.post(
            f"{base_url}/v1/agents/sessions",
            json={"agent": {"model": "codex-mini"}, "input": "Hello!"},
            headers=headers,
        )
        print(resp.json())
    finally:
        # 3. 清理沙箱
        await sandbox.kill()


asyncio.run(main())
```

> 说明：secure 模式下端口访问需要携带 `sandbox.network.get_access_headers()`
> 返回的 `X-Access-Token` 请求头——示例中的 `httpx` 调用正是为此传入该头。

### 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | **是** | — | Codex CLI 调用模型所用的 OpenAI API 密钥。始终通过 `--env` 注入，切勿硬编码。 |
| `CODEX_MODEL` | 否 | `codex-mini` | 新会话的默认 Codex 模型。可通过 `agent.model` 按会话覆盖。 |
| `AGENT_MAX_SESSIONS` | 否 | `20` | 最大并发会话数（超出时返回 429）。 |
| `AGENT_SESSION_TTL` | 否 | `1800` | 会话空闲 TTL（秒）；过期会话会被回收。 |
| `CODEX_SANDBOX_MODE` | 否 | `true` | 标识 Agent 运行在 Easy Sandbox 内的标记。 |
| `WORKSPACE` | 否 | `/workspace` | Codex 轮次的工作目录。 |

### API 参考

全部 15 个端点遵循 OpenAI Agents API 的 agents 与 sessions 接口：

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | `POST` | `/v1/agents/sessions` | 创建会话；可选执行首个轮次（`input`、`stream`）。接受内联 `agent` 字典**或**已保存的 `agent_id` 字符串。 |
| 2 | `GET` | `/v1/agents/sessions` | 列出全部活跃会话。 |
| 3 | `GET` | `/v1/agents/sessions/{session_id}` | 获取会话（包含最近的输出条目与用量）。 |
| 4 | `POST` | `/v1/agents/sessions/{session_id}` | 更新会话配置（`model`、`instructions`）。 |
| 5 | `DELETE` | `/v1/agents/sessions/{session_id}` | 删除会话并终止正在执行的轮次。 |
| 6 | `POST` | `/v1/agents/sessions/{session_id}/events` | 向会话发送用户输入并启动新轮次（默认 SSE）。 |
| 7 | `GET` | `/v1/agents/sessions/{session_id}/events` | 订阅当前活跃轮次的 SSE 事件流。 |
| 8 | `GET` | `/v1/agents/sessions/{session_id}/items` | 列出会话累积的输出条目。 |
| 9 | `POST` | `/v1/agents` | 创建可复用的 Agent 配置（`model`、`instructions`、`tools`、`name`、`metadata`）。 |
| 10 | `GET` | `/v1/agents` | 列出全部已保存的 Agent。 |
| 11 | `GET` | `/v1/agents/{agent_id}` | 按 ID 获取已保存的 Agent。 |
| 12 | `POST` | `/v1/agents/{agent_id}` | 更新已保存的 Agent（`model`、`instructions`、`tools`、`name`、`metadata`）。 |
| 13 | `DELETE` | `/v1/agents/{agent_id}` | 删除已保存的 Agent。 |
| 14 | `GET` | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | 下载会话期间产生的工作区文件产物。 |
| 15 | `DELETE` | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | 删除工作区文件产物。 |

此外，所有标准 Easy Sandbox 端点依然可用
（`/health`、`/commands`、`/files/*`、`/process/*`、`/system/*`）。

#### 请求与响应约定

- **Base URL** —— 下文示例统一使用 `http://localhost:9000`；实际使用时替换为映射后的沙箱主机与端口。
- **认证** —— 沙箱设置了 `EBX_SERVER_TOKEN` 时，每个请求都需携带 `-H "X-Access-Token: <token>"`；未设置则无需认证。
- **成功响应** —— 所有成功调用均返回 HTTP `200`（标准库服务端没有 `201`/`204` 形态）；删除返回 `200` 与 `{"deleted": true}`。
- **错误响应** —— JSON 形如 `{"error": "<message>", "type": "<ErrorClass>"}`。通用错误码：`400` 请求体不是合法 JSON、`401` 已配置 token 但请求头缺失或无效、`413` 请求体过大。

#### SSE 事件流

流式端点以 `Content-Type: text/event-stream` 响应。每帧为一个事件，逐行写出：一行 `event: <name>`、一行 `data: <json>`（单个 JSON 对象），随后一个空行结束该帧：

```
event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

```

事件名包括：`agent.session.created`、`agent.session.turn.started`、`agent.session.turn.completed`、`agent.session.turn.failed`、`agent.session.output_item.added`、`agent.session.output_item.done`、`agent.session.output_text.delta`、`agent.session.output_text.done`；未知的 Codex 事件以 `agent.session.<type>` 透传。Codex → SSE 的映射关系见事件映射表。

#### Group 1 — Agents CRUD（Agent 增删改查）

##### `POST /v1/agents` — 创建 Agent

创建可复用的 Agent 配置，会话可通过其 ID 引用。

**请求体**（全部字段可选）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | `codex-mini`（`$CODEX_MODEL`） | 轮次使用的 Codex 模型。 |
| `instructions` | string | `""` | 随 Agent 保存的指令文本。 |
| `tools` | array | `[]` | 工具定义；基于 URL 的 `mcp` 条目会映射到 Codex。 |
| `name` | string | `""` | 可读名称。 |
| `metadata` | object | `{}` | 任意客户端元数据，原样回显。 |

```bash
curl http://localhost:9000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"model": "codex-mini", "instructions": "你是一名 Python 专家。", "name": "py-expert"}'
```

**响应** `200`：

```json
{
  "id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d",
  "object": "agent",
  "model": "codex-mini",
  "instructions": "你是一名 Python 专家。",
  "tools": [],
  "name": "py-expert",
  "metadata": {},
  "created_at": 1790640000
}
```

**状态码**：`200` 成功 · `400` 请求体非法 JSON。

##### `GET /v1/agents` — 列出 Agent

列出全部已保存的 Agent。

```bash
curl http://localhost:9000/v1/agents
```

**响应** `200`：

```json
{
  "object": "list",
  "data": [
    {
      "id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d",
      "object": "agent",
      "model": "codex-mini",
      "instructions": "你是一名 Python 专家。",
      "tools": [],
      "name": "py-expert",
      "metadata": {},
      "created_at": 1790640000
    }
  ]
}
```

无已保存 Agent 时 `data` 为 `[]`。**状态码**：`200` 成功。

##### `GET /v1/agents/{agent_id}` — 获取 Agent

按 ID 获取单个已保存的 Agent。

```bash
curl http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d
```

**响应** `200`：即上文“创建 Agent”处的 Agent 对象。

**状态码**：`200` 成功 · `404` `{"error": "Agent agent_9f2c1b8e4d7a4c3f8b1e6a2d not found", "type": "NotFoundError"}`。

##### `POST /v1/agents/{agent_id}` — 更新 Agent

部分更新已保存的 Agent。仅应用 `model`、`instructions`、`tools`、`name`、`metadata`；未知字段会被忽略，`id` / `object` / `created_at` 不可修改。

**请求体** —— 只包含需要变更的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | string | 替换后的模型。 |
| `instructions` | string | 替换后的指令文本。 |
| `tools` | array | 替换后的工具定义。 |
| `name` | string | 替换后的名称。 |
| `metadata` | object | 替换后的元数据。 |

```bash
curl http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d \
  -H "Content-Type: application/json" \
  -d '{"name": "py-expert-v2", "instructions": "Answer with code first."}'
```

**响应** `200`：更新后的 Agent 对象；未出现在请求中的字段保持原值。

**状态码**：`200` 成功 · `400` 请求体非法 JSON · `404` Agent 不存在。

##### `DELETE /v1/agents/{agent_id}` — 删除 Agent

删除已保存的 Agent。已由它创建的会话不受影响。

```bash
curl -X DELETE http://localhost:9000/v1/agents/agent_9f2c1b8e4d7a4c3f8b1e6a2d
```

**响应** `200`：

```json
{"id": "agent_9f2c1b8e4d7a4c3f8b1e6a2d", "object": "agent", "deleted": true}
```

**状态码**：`200` 成功 · `404` Agent 不存在。

#### Group 2 — Sessions（会话）

##### `POST /v1/agents/sessions` — 创建会话

创建会话；传入 `input` 时可选执行首个轮次。

**请求体**（全部字段可选）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `agent` | object \| string | `{}` | 内联 Agent 配置（`model`、`instructions`、`tools`）或已保存 Agent 的 ID；ID 不存在时返回 `404`。 |
| `input` | string \| array | — | 首轮用户输入（支持下方三种形式）。省略则只创建会话、不执行轮次。 |
| `stream` | boolean | `false` | `true` → SSE 流（首个轮次）；`false` 且带 `input` → 阻塞至轮次结束，然后返回会话 JSON。 |

支持的 `input` 形式（events 端点同样适用）：

```json
{"input": "用 Python 写一个 hello world"}
{"input": [{"type": "input_text", "text": "用 Python 写一个 hello world"}]}
{"type": "agent.session.input.message", "content": [{"type": "input_text", "text": "用 Python 写一个 hello world"}]}
```

```bash
# 仅创建 —— 不执行轮次
curl http://localhost:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": {"model": "codex-mini", "instructions": "Reply concisely."}}'

# 创建并执行首个轮次，以 SSE 流式返回
curl -N http://localhost:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": {"model": "codex-mini"}, "input": "用 Python 写一个 hello world", "stream": true}'
```

**响应** `200`（仅创建）：

```json
{
  "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "object": "session",
  "status": "idle",
  "model": "codex-mini",
  "instructions": "Reply concisely.",
  "tools": [],
  "created_at": 1790640000,
  "metadata": {}
}
```

**响应** `200`（带 `input` 且 `stream: false`）—— 会话对象额外包含 `output`（最近 5 个累积条目）与 `usage`：

```json
{
  "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "object": "session",
  "status": "idle",
  "model": "codex-mini",
  "instructions": "Reply concisely.",
  "tools": [],
  "created_at": 1790640000,
  "metadata": {},
  "output": [
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "print(\"Hello, world!\")"}}
  ],
  "usage": {"input_tokens": 1352, "output_tokens": 29}
}
```

**响应**（`stream: true`）—— SSE 帧，按顺序：

```
event: agent.session.created
data: {"id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "object": "session", "status": "in_progress", "model": "codex-mini", "instructions": "", "tools": [], "created_at": 1790640000, "metadata": {}}

event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

event: agent.session.turn.completed
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "status": "completed"}
```

映射后的 Codex 事件（`agent.session.output_item.*`、`agent.session.output_text.*`）出现在两个轮次帧之间。

**状态码**：`200` 成功 · `400` 请求体非法 JSON · `404` 引用的 `agent` ID 不存在 · `429` `{"error": "Too many active sessions", "type": "CapacityError"}` · `500` 无法启动 Codex 进程。

##### `GET /v1/agents/sessions` — 列出会话

列出全部活跃会话（仅元数据——不含 `output` / `usage`）。

```bash
curl http://localhost:9000/v1/agents/sessions
```

**响应** `200`：

```json
{
  "object": "list",
  "data": [
    {
      "id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
      "object": "session",
      "status": "idle",
      "model": "codex-mini",
      "instructions": "",
      "tools": [],
      "created_at": 1790640000,
      "metadata": {}
    }
  ]
}
```

**状态码**：`200` 成功。

##### `GET /v1/agents/sessions/{session_id}` — 获取会话

获取会话，包含最近输出与累计用量。

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d
```

**响应** `200`：带 `output`（最近 5 个条目）与 `usage` 的会话对象，形态与上文交互式创建响应一致。

**状态码**：`200` 成功 · `404` 会话不存在。

##### `POST /v1/agents/sessions/{session_id}` — 更新会话

更新会话配置。仅应用 `model` 与 `instructions`。

**请求体** —— 只包含需要变更的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | string | 后续轮次使用的模型。 |
| `instructions` | string | 替换后的指令文本。 |

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d \
  -H "Content-Type: application/json" \
  -d '{"instructions": "Answer in French."}'
```

**响应** `200`：更新后的会话对象（仅元数据——不含 `output` / `usage`）。

**状态码**：`200` 成功 · `400` 请求体非法 JSON · `404` 会话不存在。

##### `DELETE /v1/agents/sessions/{session_id}` — 删除会话

删除会话，并终止仍在执行的轮次进程。

```bash
curl -X DELETE http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d
```

**响应** `200`：

```json
{"id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "object": "session", "deleted": true}
```

**状态码**：`200` 成功 · `404` 会话不存在。

#### Group 3 — Turns & Events（轮次与事件）

##### `POST /v1/agents/sessions/{session_id}/events` — 发送输入（新轮次）

向已有会话发送用户输入并启动新轮次。后续轮次会恢复首个轮次记录的同一 Codex thread。

**请求体**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input` | string \| array | — | **必填。** 与创建会话相同的三种输入形式。 |
| `stream` | boolean | `true` | `true` → SSE 流；`false` → 阻塞并返回会话 JSON。 |

```bash
# 流式轮次（默认）
curl -N http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events \
  -H "Content-Type: application/json" \
  -d '{"input": "现在添加一个单元测试"}'

# 同步轮次
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events \
  -H "Content-Type: application/json" \
  -d '{"input": "现在添加一个单元测试", "stream": false}'
```

**响应** `200`（`stream: false`）：带 `output` 与 `usage` 的会话对象（形态同上）。

**响应**（`stream: true`）—— SSE 帧：

```
event: agent.session.turn.started
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d"}

event: agent.session.output_item.done
data: {"type": "agent.session.output_item.done", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "item": {"id": "item_1", "type": "agent_message", "text": "Add a pytest case to test_hello.py."}}

event: agent.session.turn.completed
data: {"turn_id": "turn_4c8e2f6a9b1d3e5c7a9f2b4d", "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d", "status": "completed"}
```

**状态码**：`200` 成功 · `400` `{"error": "Missing input text", "type": "ValueError"}` · `404` 会话不存在 · `409` `{"error": "Session has an active turn", "type": "ConflictError"}`（每个会话同时只允许一个轮次）· `500` 启动失败。

##### `GET /v1/agents/sessions/{session_id}/events` — 订阅事件（SSE）

附着到会话当前运行轮次的事件流。这是对 Codex 实时 stdout 的尽力而为式跟踪，并非可重放的事件日志。

```bash
curl -N http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/events
```

**响应** `200` —— 无活跃轮次时返回 JSON（而非 SSE）：

```json
{"status": "idle", "message": "No active turn"}
```

轮次进行中时，响应为 `text/event-stream`，持续推送剩余的映射事件直至轮次结束（帧格式与事件名同上）。

**状态码**：`200` 成功（两种分支）· `404` 会话不存在。

#### Group 4 — Items & Artifacts（条目与产物）

##### `GET /v1/agents/sessions/{session_id}/items` — 列出输出条目

列出会话累积的全部条目 —— 原始 Codex `item.started` / `item.completed` 事件，按时间从旧到新。

```bash
curl http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/items
```

**响应** `200`：

```json
{
  "object": "list",
  "data": [
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "print(\"Hello, world!\")"}}
  ]
}
```

assistant 消息呈现为 `item` 对象内的 `{"type": "agent_message", "text": "..."}`；命令执行、推理等其它 Codex 条目类型原样透传。

**状态码**：`200` 成功 · `404` 会话不存在。

##### `GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}` — 下载产物

以产物形式获取工作区文件。`artifact_id` 为工作区相对路径的 URL-safe base64 编码（可省略填充）；无法解码的值会按普通相对路径处理；逃逸工作区的路径会被拒绝。

```bash
artifact_id=$(printf 'report.md' | base64)   # -> cmVwb3J0Lm1k
curl "http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/artifacts/$artifact_id"
```

**响应** `200`：

```json
{
  "id": "cmVwb3J0Lm1k",
  "object": "artifact",
  "session_id": "sess_7a3f9c2e5b8d1a4f6c9e2b7d",
  "file_path": "report.md",
  "content": "# Report\n\n...",
  "size": 1234
}
```

`content` 以 UTF-8 文本读取（非法字节会被替换）；`size` 为文件字节数。

**状态码**：`200` 成功 · `403` `{"error": "Access denied: path outside workspace", "type": "ForbiddenError"}` · `404` 会话不存在，或 `{"error": "Artifact not found: <path>", "type": "NotFoundError"}` · `500` 读取失败。

##### `DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id}` — 删除产物

删除工作区文件产物。

```bash
curl -X DELETE \
  "http://localhost:9000/v1/agents/sessions/sess_7a3f9c2e5b8d1a4f6c9e2b7d/artifacts/cmVwb3J0Lm1k"
```

**响应** `200`：

```json
{"id": "cmVwb3J0Lm1k", "object": "artifact", "deleted": true}
```

**状态码**：`200` 成功 · `403` 路径在工作区之外 · `404` 会话或产物不存在 · `500` 删除失败。

### 使用示例

#### curl

创建会话并流式输出首个轮次（SSE）：

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{
        "agent": {"model": "codex-mini"},
        "input": "用 Python 写一个 hello world",
        "stream": true
      }'
```

向已有会话发送后续输入：

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/events \
  -H "Content-Type: application/json" \
  -d '{"input": "现在添加一个单元测试"}'
```

列出会话：

```bash
curl http://<sandbox-host>:9000/v1/agents/sessions
```

创建可复用的 Agent，然后在创建会话时按 ID 引用：

```bash
# 1. 保存一次 Agent 配置
agent_id=$(curl -s http://<sandbox-host>:9000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"model": "codex-mini", "instructions": "你是一名 Python 专家。"}' \
  | jq -r .id)

# 2. 在多个会话间复用它 —— `agent` 为已保存 Agent 的 ID
curl http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{"agent": "'"$agent_id"'", "input": "用 Python 写一个 hello world"}'
```

获取会话产生的文件产物（产物 ID 为其工作区相对路径的 URL-safe base64 编码）：

```bash
artifact_id=$(printf 'report.md' | base64)  # -> cmVwb3J0Lm1k
curl http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/artifacts/$artifact_id

# 之后将其删除
curl -X DELETE \
  http://<sandbox-host>:9000/v1/agents/sessions/sess_xxx/artifacts/$artifact_id
```

### 远程 MCP 工具

通过 Agent 的 `tools` 数组传入基于 URL 的 MCP 服务器——适配器会将它们映射为
Codex 的 `mcp_servers.*`，并应用于该会话的每个轮次：

```bash
curl -N http://<sandbox-host>:9000/v1/agents/sessions \
  -H "Content-Type: application/json" \
  -d '{
        "agent": {
          "model": "codex-mini",
          "tools": [
            {
              "type": "mcp",
              "server_label": "deepwiki",
              "server_url": "https://mcp.deepwiki.com/mcp",
              "headers": {"Authorization": "Bearer <token>"}
            }
          ]
        },
        "input": "列出你可以使用的 MCP 工具",
        "stream": true
      }'
```

支持的字段：`server_label` / `name`（会被规范化为配置安全的标签）、
`server_url` / `url`（可平铺或嵌套在 `transport` 下）以及 `headers`
（转发为 `http_headers`）。不带 URL 的工具——例如通过 `connector_id`
声明的托管连接器——会被跳过。

#### Python（openai SDK）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<sandbox-host>:9000/v1",
    api_key="sk-xxx",
)

# 流式会话
stream = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="用 Python 写一个 hello world",
    stream=True,
)
for event in stream:
    print(event.type, event.data)

# 非流式会话
session = client.beta.agents.sessions.create(
    agent={"model": "codex-mini"},
    input="2 + 2 等于几？",
)
print(session.status, session.output)

# 后续轮次
for event in client.beta.agents.sessions.events.create(
    session_id=session.id,
    input="再用小孩能听懂的方式解释一下",
    stream=True,
):
    print(event.type, event.data)

# 检查累积的条目
items = client.beta.agents.sessions.items.list(session_id=session.id)
for item in items.data:
    print(item)

# 清理
client.beta.agents.sessions.delete(session_id=session.id)
```

#### JavaScript / TypeScript（openai SDK）

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://<sandbox-host>:9000/v1",
  apiKey: "sk-xxx",
});

// 流式会话
const stream = await client.beta.agents.sessions.create({
  agent: { model: "codex-mini" },
  input: "用 TypeScript 写一个 hello world",
  stream: true,
});

for await (const event of stream) {
  console.log(event.type, event.data);
}
```

### 兼容性矩阵

| Agents API 特性 | 支持情况 | 说明 |
|-----------------|----------|------|
| 创建会话（`POST /v1/agents/sessions`） | ✅ | 支持可选的首次轮次（`input`、`stream`）。 |
| 列出会话 | ✅ | |
| 获取 / 更新 / 删除会话 | ✅ | 更新支持 `model` 与 `instructions`。 |
| 发送输入 / 事件 | ✅ | 支持字符串输入与 `agent.session.input.message` 内容数组。 |
| SSE 流式输出 | ✅ | 完整事件映射（见下文）。 |
| 会话条目 | ✅ | 累积的 Codex 条目（`item.started` / `item.completed`）。 |
| 已保存 Agent（Agents CRUD） | ✅ | 创建/列出/获取/更新/删除可复用 Agent 配置；在 `agent` 中按 ID 引用。 |
| 产物（获取 / 删除） | ✅ | 以 URL-safe base64 编码的相对路径寻址工作区文件产物；工作区之外的路径会被拒绝（403）。 |
| 多轮对话 | ✅ | 从首个轮次记录确切的 Codex thread 并在后续轮次恢复（`codex exec resume <thread_id> -- <prompt>`），回退到 `resume --last`。已针对 Codex CLI 0.158.0 验证。 |
| 自定义工具 / 函数调用 | ⚠️ 部分支持 | Codex 内置工具（shell、文件编辑、MCP）可用；自定义函数回调属于 Phase 2。 |
| 远程 MCP / 连接器 | ✅ | 基于 URL 的远程 MCP 服务器（`server_url` + `headers`）通过 `-c mcp_servers.*` 配置覆盖映射到 Codex。托管型 `connector_id` 工具不会被代理，会被跳过。 |
| Token 用量统计 | ✅ | `turn.completed` 的用量按会话累计，并以 `usage.input_tokens` / `usage.output_tokens` 返回。 |
| 护栏 / 内容审查 | ❌ | 未实现。 |
| 持久化存储 / 检查点 | ❌ | 会话仅存于内存。 |

#### 事件映射（Codex JSONL → Agents API SSE）

| Codex 事件 | Agents API 事件 |
|------------|------------------|
| `thread.started` | `agent.session.created` |
| `turn.started` | `agent.session.turn.started` |
| `turn.completed` | `agent.session.turn.completed` |
| `item.started` | `agent.session.output_item.added` |
| `item.completed` | `agent.session.output_item.done` |
| `message.delta` | `agent.session.output_text.delta` |
| `message.completed` | `agent.session.output_text.done` |
| `error` | `agent.session.turn.failed` |

`thread.started` 事件的 `thread_id` 会按会话记录，并在后续轮次复用以恢复确切的
Codex thread。`turn.completed` 的用量会累加到会话的 `usage` 计数中。

未知的 Codex 事件类型会以 `agent.session.<type>` 透传。

### 已知限制

- **内存中的会话** —— 所有会话状态都保存在适配器进程内。重启沙箱会丢失
  全部会话；没有持久化或检查点机制。
- **单实例** —— 适配器为单进程；会话不在副本间共享，也没有集群能力。
- **每个会话同时只有一个活跃轮次** —— 对同一会话的并发输入会返回
  `409 Conflict`。
- **会话容量** —— 受 `AGENT_MAX_SESSIONS` 限制（默认 20）；超出上限的
  请求在清理过期会话后仍会返回 `429`。
- **轮次超时** —— 每个轮次硬性上限 300 秒；超时后 Codex 进程会被终止，
  轮次失败。
- **`GET .../events` 订阅** —— 附着到活跃轮次的 stdout；属于尽力而为的
  尾部跟踪，并非可重放的事件日志。
- **多轮状态** —— 恢复依赖沙箱内 `$CODEX_HOME`（默认 `/root/.codex`）下的
  Codex 会话文件。沙箱重建后这些文件会丢失，此后恢复的轮次会失败，失败原因
  会以 turn-failed 事件中的 Codex 错误呈现。
- **MCP 连接器** —— 只能代理基于 URL 的远程 MCP 服务器；托管型
  `connector_id` 工具与自定义函数回调会被忽略。

### 安全说明

- **切勿硬编码 `OPENAI_API_KEY`。** 始终在创建沙箱时注入
  （`ebx create --env OPENAI_API_KEY=sk-xxx`）或通过你的密钥管理服务注入。
- 适配器在 Easy Sandbox 容器内以 `--dangerously-bypass-approvals-and-sandbox`
  运行 Codex——沙箱边界即隔离层。请勿将 `9000` 端口暴露给不受信任的网络。
- 可选的 bearer/token 认证继承自沙箱服务器（`EBX_SERVER_TOKEN`）；
  如果沙箱端口可被信任边界之外的网络访问，请设置它。
- 发往 OpenAI 的流量会经网络离开沙箱；请确保你的合规策略允许此流量。

---

Part of [awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) · Maintained by Easy-Sandbox
