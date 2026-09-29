"""codex-agent-api — Self-hosted OpenAI Agents API compatible service.

Exposes /v1/agents/sessions/* endpoints that are 100% compatible with the
OpenAI Agents API specification. Internally drives Codex CLI in headless
mode (codex exec --json) for LLM orchestration.

Architecture::

    +-----------------------------------------+
    | SandboxServer (port 9000)               |
    |                                         |
    | Standard routes:                        |
    |   /health, /commands, /files/*, etc.    |
    |                                         |
    | Agent API routes (new):                 |
    |   POST   /v1/agents/sessions            |
    |   GET    /v1/agents/sessions            |
    |   GET    /v1/agents/sessions/{id}       |
    |   POST   /v1/agents/sessions/{id}       |
    |   DELETE /v1/agents/sessions/{id}       |
    |   POST   /v1/agents/sessions/{id}/events|
    |   GET    /v1/agents/sessions/{id}/events|
    |   GET    /v1/agents/sessions/{id}/items |
    |   GET    /v1/agents/sessions/{id}/       |
    |          artifacts/{artifact_id}        |
    |   DELETE /v1/agents/sessions/{id}/       |
    |          artifacts/{artifact_id}        |
    |   POST   /v1/agents                     |
    |   GET    /v1/agents                     |
    |   GET    /v1/agents/{agent_id}          |
    |   POST   /v1/agents/{agent_id}          |
    |   DELETE /v1/agents/{agent_id}          |
    +---------------------+-------------------+
                          |
                          v
                  codex exec --json
                  (subprocess per turn)

Usage with OpenAI Python SDK::

    from openai import OpenAI

    client = OpenAI(base_url="http://<sandbox-host>:9000/v1")
    session = client.beta.agents.sessions.create(
        agent={"model": "codex-mini"},
        input="Write hello world in Python",
        stream=True,
    )
"""
from __future__ import annotations

import atexit
import base64
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

from easy_sandbox.server import (
    CapabilityGroup,
    CommandRegistry,
    SandboxServer,
    SSEResponse,
    ServerRequest,
    ServerResponse,
    default_table,
)

# ── Configuration ──────────────────────────────────────────────────────

DEFAULT_MODEL = os.environ.get("CODEX_MODEL", "codex-mini")
MAX_SESSIONS = int(os.environ.get("AGENT_MAX_SESSIONS", "20"))
SESSION_TTL = int(os.environ.get("AGENT_SESSION_TTL", "1800"))  # seconds
TURN_TIMEOUT = 300  # seconds per turn
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")

# ── Route table & capability groups ────────────────────────────────────

table = default_table()
table.enable_group(CapabilityGroup.FILE_OPS)
table.enable_group(CapabilityGroup.PROCESS)
table.enable_group(CapabilityGroup.SYSTEM)

# ── Command registry (basic codex command for backward compat) ─────────

registry = CommandRegistry()


@registry.command("codex", description="Run Codex agent.")
def codex_cmd(prompt: str, model: str = "") -> str:
    """Run Codex agent (simple mode)."""
    m = model or DEFAULT_MODEL
    result = subprocess.run(
        ["codex", "-p", prompt, "--model", m, "--yolo", "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


# ── Session data model ─────────────────────────────────────────────────


@dataclass
class Turn:
    """A single turn within a session."""

    id: str = field(default_factory=lambda: f"turn_{uuid.uuid4().hex[:24]}")
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    created_at: int = field(default_factory=lambda: int(time.time()))
    completed_at: int | None = None
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Session:
    """An Agent API session backed by Codex CLI."""

    id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:24]}")
    object: str = "session"
    status: str = "idle"  # idle | in_progress | completed | failed | cancelled
    model: str = ""
    instructions: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time()))
    last_active: int = field(default_factory=lambda: int(time.time()))
    turns: list[Turn] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    # Token usage accumulated from Codex ``turn.completed`` events.
    usage: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0}
    )
    # Codex thread id recorded from the first turn (used for resume).
    thread_id: str = ""
    _process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to OpenAI-compatible JSON."""
        return {
            "id": self.id,
            "object": self.object,
            "status": self.status,
            "model": self.model,
            "instructions": self.instructions,
            "tools": self.tools,
            "created_at": self.created_at,
            "metadata": {},
        }

    def to_dict_with_output(self) -> dict[str, Any]:
        """Serialize with output items (for completed sessions)."""
        d = self.to_dict()
        d["output"] = self.items[-5:] if self.items else []  # last 5 items
        d["usage"] = dict(self.usage)  # real usage accumulated from turn.completed
        return d


# ── Session store (thread-safe) ────────────────────────────────────────


class CapacityError(Exception):
    """Raised when the session store cannot accept new sessions."""


def _kill_process(proc: subprocess.Popen[bytes]) -> None:
    """Safely terminate a subprocess."""
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


class SessionStore:
    """Thread-safe in-memory session store with TTL and capacity limits."""

    def __init__(self, max_sessions: int = MAX_SESSIONS, ttl: int = SESSION_TTL) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._max = max_sessions
        self._ttl = ttl
        # Start GC daemon thread
        self._gc_thread = threading.Thread(target=self._gc_loop, daemon=True)
        self._gc_thread.start()

    def create(self, model: str, instructions: str, tools: list[dict[str, Any]]) -> Session:
        """Create a new session, evicting expired ones when at capacity."""
        with self._lock:
            if len(self._sessions) >= self._max:
                # Try to evict expired sessions first
                self._evict_expired()
                if len(self._sessions) >= self._max:
                    raise CapacityError("Too many active sessions")
            session = Session(model=model or DEFAULT_MODEL, instructions=instructions, tools=tools)
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        """Return the session with *session_id*, or ``None``."""
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        """Delete a session (killing any live turn process)."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session and session._process:
                _kill_process(session._process)
            return session is not None

    def list_all(self) -> list[Session]:
        """Return a snapshot of all sessions."""
        with self._lock:
            return list(self._sessions.values())

    def _evict_expired(self) -> None:
        """Drop sessions idle for longer than the TTL (caller holds the lock)."""
        now = int(time.time())
        expired = [sid for sid, s in self._sessions.items() if now - s.last_active > self._ttl]
        for sid in expired:
            s = self._sessions.pop(sid, None)
            if s and s._process:
                _kill_process(s._process)

    def _gc_loop(self) -> None:
        """Background loop evicting expired sessions every 60 seconds."""
        while True:
            time.sleep(60)
            with self._lock:
                self._evict_expired()


# Global session store
store = SessionStore()


# Cleanup on exit
def _cleanup() -> None:
    """Terminate any live turn processes when the server exits."""
    for s in store.list_all():
        if s._process:
            _kill_process(s._process)


atexit.register(_cleanup)


# ── Agent configuration store (thread-safe) ─────────────────────


@dataclass
class AgentConfig:
    """A saved, reusable Agent configuration."""

    id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:24]}")
    object: str = "agent"
    model: str = ""
    instructions: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to OpenAI-compatible JSON."""
        return {
            "id": self.id,
            "object": self.object,
            "model": self.model,
            "instructions": self.instructions,
            "tools": self.tools,
            "name": self.name,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class AgentStore:
    """Thread-safe in-memory agent configuration store."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentConfig] = {}
        self._lock = threading.Lock()

    def create(
        self,
        model: str,
        instructions: str = "",
        tools: list[dict[str, Any]] | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentConfig:
        """Create and store a new agent configuration."""
        with self._lock:
            agent = AgentConfig(
                model=model,
                instructions=instructions,
                tools=tools or [],
                name=name,
                metadata=metadata or {},
            )
            self._agents[agent.id] = agent
            return agent

    def get(self, agent_id: str) -> AgentConfig | None:
        """Return the agent with *agent_id*, or ``None``."""
        with self._lock:
            return self._agents.get(agent_id)

    def list_all(self) -> list[AgentConfig]:
        """Return a snapshot of all saved agents."""
        with self._lock:
            return list(self._agents.values())

    def update(self, agent_id: str, **kwargs: Any) -> AgentConfig | None:
        """Update mutable fields of an agent.

        The ``id``, ``object`` and ``created_at`` fields are immutable.
        """
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return None
            for key, value in kwargs.items():
                if hasattr(agent, key) and key not in ("id", "object", "created_at"):
                    setattr(agent, key, value)
            return agent

    def delete(self, agent_id: str) -> bool:
        """Delete an agent, returning whether it existed."""
        with self._lock:
            return self._agents.pop(agent_id, None) is not None


# Global agent store
agent_store = AgentStore()


# ── Codex CLI adapter ──────────────────────────────────────────────────


def _unique_mcp_label(raw_label: Any, index: int, used: set[str]) -> str:
    """Return a config-safe, unique label for an MCP server.

    Codex config keys are dotted paths and quoted path segments are rejected
    (verified against Codex CLI 0.158.0: ``mcp_servers."a.b"`` fails to parse),
    so labels are restricted to ``[A-Za-z0-9_-]`` and de-duplicated.
    """
    base = re.sub(r"[^A-Za-z0-9_-]", "_", str(raw_label or "")).strip("_") or f"mcp_{index}"
    label = base
    suffix = 2
    while label in used:
        label = f"{base}_{suffix}"
        suffix += 1
    used.add(label)
    return label


def _mcp_server_overrides(tools: list[dict[str, Any]]) -> list[str]:
    """Translate Agents API MCP tool definitions into ``-c`` config overrides.

    Codex CLI 0.158.0 has no ``--mcp-config`` flag; remote MCP servers are
    configured through ``mcp_servers.<label>.url`` / ``.http_headers`` keys
    passed as ``-c key=value`` overrides (the value portion is parsed as TOML
    by Codex — verified with ``--strict-config``). Only URL-based servers can
    be proxied: hosted ``connector_id`` tools are host-side and are skipped.
    """
    overrides: list[str] = []
    used_labels: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "mcp":
            continue
        # Accept both the flat Responses-API shape and a nested ``transport``.
        transport = tool.get("transport")
        transport = transport if isinstance(transport, dict) else {}
        url = (
            transport.get("server_url")
            or transport.get("url")
            or tool.get("server_url")
            or tool.get("url")
        )
        if not isinstance(url, str) or not url:
            continue
        label = _unique_mcp_label(
            tool.get("server_label") or tool.get("name"), len(used_labels), used_labels
        )
        overrides += ["-c", f"mcp_servers.{label}.url={json.dumps(url)}"]
        headers = tool.get("headers") or transport.get("headers")
        if isinstance(headers, dict) and headers:
            entries = ", ".join(
                f"{json.dumps(str(key))} = {json.dumps(str(value))}"
                for key, value in headers.items()
            )
            overrides += ["-c", f"mcp_servers.{label}.http_headers={{{entries}}}"]
    return overrides


def _provider_overrides() -> list[str]:
    """Translate a custom ``OPENAI_BASE_URL`` into Codex provider overrides.

    Codex CLI 0.158.0 does *not* re-route its built-in ``openai`` provider
    from the ``OPENAI_BASE_URL`` environment variable alone (verified against
    the real binary: requests still hit ``api.openai.com`` and fail with
    ``401 Missing bearer``).  When this adapter is pointed at an
    OpenAI-compatible gateway (e.g. Alibaba Cloud MaaS / Bailian), declare a
    custom provider through ``-c`` config overrides so every turn talks to
    that endpoint using the ``OPENAI_API_KEY`` from the environment.  When
    ``OPENAI_BASE_URL`` is unset the default OpenAI provider is kept.
    """
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if not base_url:
        return []
    prefix = "model_providers.openai_compatible"
    return [
        "-c", f"model_provider={json.dumps('openai_compatible')}",
        "-c", f"{prefix}.name={json.dumps('OpenAI-compatible endpoint')}",
        "-c", f"{prefix}.base_url={json.dumps(base_url)}",
        "-c", f"{prefix}.env_key={json.dumps('OPENAI_API_KEY')}",
        "-c", f"{prefix}.wire_api={json.dumps('responses')}",
        # Custom gateways serve the Responses HTTP API only; skip websockets.
        "-c", f"{prefix}.supports_websockets=false",
    ]


def _track_codex_event(session: Session, event: dict[str, Any], turn: Turn | None = None) -> None:
    """Fold a Codex JSONL event into session state.

    - ``item.started`` / ``item.completed`` events are accumulated as items.
    - ``thread.started`` records the Codex thread id so later turns can resume
      the exact thread instead of relying on ``resume --last`` (which picks the
      most recent thread in the workspace and can collide when several Agent
      API sessions share one sandbox).
    - ``turn.completed`` accumulates the token usage reported by Codex.
    """
    event_type = event.get("type")
    if event_type in ("item.started", "item.completed"):
        session.items.append(event)
        if turn is not None:
            turn.items.append(event)
    elif event_type == "thread.started":
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            session.thread_id = thread_id
    elif event_type == "turn.completed":
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            for key in ("input_tokens", "output_tokens"):
                value = event_usage.get(key, 0)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    session.usage[key] += int(value)


def spawn_codex_turn(session: Session, input_text: str) -> subprocess.Popen[bytes]:
    """Spawn a ``codex exec`` process for a new turn.

    The argv shape is locked against Codex CLI 0.158.0 (verified against the
    real binary):

    * first turn — ``codex exec --json ... -- <prompt>``
    * later turns — ``codex exec --json ... resume <thread_id|--last> -- <prompt>``

    ``resume`` does not accept ``--sandbox``, so every option is passed at the
    ``exec`` level before the subcommand (verified: they apply to the resumed
    turn). ``--`` terminates option parsing so prompts beginning with ``-``
    are not mistaken for flags.

    When ``OPENAI_BASE_URL`` points at an OpenAI-compatible gateway, a custom
    Codex provider is injected via :func:`_provider_overrides` so the turn
    does not silently fall back to ``api.openai.com``.
    """
    cmd = [
        "codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        session.model,
    ]
    cmd.extend(_provider_overrides())
    cmd.extend(_mcp_server_overrides(session.tools))
    if session.turns:
        # Prefer the exact thread recorded from the first turn; fall back to
        # the most recent thread in the workspace only when no id was captured.
        cmd.extend(["resume", session.thread_id or "--last"])
    cmd.extend(["--", input_text])

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=WORKSPACE,
    )
    return proc


def iter_codex_events(
    proc: subprocess.Popen[bytes],
    timeout: int = TURN_TIMEOUT,
) -> Iterator[dict[str, Any]]:
    """Read JSONL events from ``codex exec`` stdout."""
    start = time.monotonic()
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        if time.monotonic() - start > timeout:
            _kill_process(proc)
            yield {"type": "error", "error": {"message": "Turn timeout exceeded"}}
            return
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue
    returncode = proc.wait()
    if returncode:
        # ``resume`` of an unknown thread id (or another early failure) can
        # exit non-zero without emitting a JSONL error event — surface the
        # stderr tail so the turn is not silently marked as completed.
        detail = ""
        if proc.stderr is not None:
            try:
                detail = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                detail = ""
        message = f"codex exec exited with code {returncode}"
        if detail:
            message = f"{message}: {detail[-2000:]}"
        yield {"type": "error", "error": {"message": message}}


# Codex event type -> OpenAI Agents API event type
_EVENT_TYPE_MAP = {
    "thread.started": "agent.session.created",
    "turn.started": "agent.session.turn.started",
    "turn.completed": "agent.session.turn.completed",
    "item.started": "agent.session.output_item.added",
    "item.completed": "agent.session.output_item.done",
    "message.delta": "agent.session.output_text.delta",
    "message.completed": "agent.session.output_text.done",
    "error": "agent.session.turn.failed",
}


def map_event(event: dict[str, Any], session_id: str, turn_id: str) -> str | None:
    """Map a Codex JSONL event to an OpenAI Agents API SSE event string.

    Returns a formatted SSE string like::

        event: agent.session.turn.started
        data: {...}

    Returns ``None`` for events that should be skipped.
    """
    etype = event.get("type", "")

    api_event_type = _EVENT_TYPE_MAP.get(etype)
    if not api_event_type:
        # Pass through unknown events with a generic type
        if not etype:
            return None
        api_event_type = f"agent.session.{etype}"

    # Build the data payload
    data: dict[str, Any] = {
        "type": api_event_type,
        "session_id": session_id,
    }

    if "turn" in api_event_type:
        data["turn_id"] = turn_id

    # Include original event data
    if "item" in event:
        data["item"] = event["item"]
    if "message" in event:
        data["message"] = event["message"]
    if "delta" in event:
        data["delta"] = event["delta"]
    if "content" in event:
        data["content"] = event["content"]
    if "error" in event:
        data["error"] = event["error"]
    if "status" in event:
        data["status"] = event["status"]

    # Copy over any additional fields from the original event
    for key in ("result", "output", "text", "code", "tool_call", "function_call"):
        if key in event:
            data[key] = event[key]

    return f"event: {api_event_type}\ndata: {json.dumps(data)}\n\n"


def _extract_input_text(body: dict[str, Any]) -> str:
    """Extract user input text from a request body.

    Supports the plain string form (``{"input": "..."}``), the structured
    content-array form, and the ``agent.session.input.message`` event form
    used by the events endpoint.
    """
    input_text = body.get("input", "")
    if isinstance(input_text, str) and input_text:
        return input_text
    # input may be a structured content array: [{"type": "input_text", ...}]
    if isinstance(input_text, list):
        for part in input_text:
            if isinstance(part, dict) and part.get("type") == "input_text":
                return str(part.get("text", ""))
        return ""
    # "type": "agent.session.input.message" format
    if body.get("type") == "agent.session.input.message":
        content = body.get("content", [])
        if content and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "input_text":
                    return str(c.get("text", ""))
    return ""


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _finish_turn(session: Session, turn: Turn) -> None:
    """Mark a turn (and its session) as completed."""
    turn.status = "completed"
    turn.completed_at = int(time.time())
    session.status = "idle"
    session._process = None
    session.last_active = int(time.time())


# ── Agent API routes ───────────────────────────────────────────────────


# POST /v1/agents/sessions — Create session
@table.route("POST", "/v1/agents/sessions", group=CapabilityGroup.COMMANDS, streaming=True)
def create_session(request: ServerRequest) -> SSEResponse | ServerResponse:
    """Create a session and optionally run a first turn."""
    body = request.body or {}
    agent_config = body.get("agent", {})
    if isinstance(agent_config, str):
        # `agent` may reference a saved agent by ID instead of an inline dict.
        saved_agent = agent_store.get(agent_config)
        if not saved_agent:
            return ServerResponse.error(404, f"Agent {agent_config} not found", "NotFoundError")
        agent_config = saved_agent.to_dict()
    if not isinstance(agent_config, dict):
        agent_config = {}
    model = agent_config.get("model", DEFAULT_MODEL)
    instructions = agent_config.get("instructions", "")
    tools = agent_config.get("tools", [])
    input_text = _extract_input_text(body)
    stream = body.get("stream", False)

    try:
        session = store.create(model=model, instructions=instructions, tools=tools)
    except CapacityError:
        return ServerResponse.error(429, "Too many active sessions", "CapacityError")

    if not input_text:
        # No input — just create the session and return
        return ServerResponse.ok(session.to_dict())

    # Start a turn — turn creation, status update and process spawn happen
    # atomically under the session lock so concurrent requests cannot
    # interleave state transitions on this session.
    with session._lock:
        turn = Turn()
        session.turns.append(turn)
        session.status = "in_progress"
        session.last_active = int(time.time())

        try:
            proc = spawn_codex_turn(session, input_text)
            session._process = proc
        except Exception as exc:  # noqa: BLE001
            session.status = "failed"
            turn.status = "failed"
            return ServerResponse.error(500, str(exc), "SpawnError")

    if stream:
        # Return SSE stream
        def event_gen() -> Iterator[str]:
            # Emit session created event
            yield _sse("agent.session.created", session.to_dict())
            yield _sse("agent.session.turn.started", {"turn_id": turn.id, "session_id": session.id})

            failed = False
            try:
                for codex_event in iter_codex_events(proc):
                    _track_codex_event(session, codex_event, turn)

                    if codex_event.get("type") == "error":
                        failed = True

                    sse_str = map_event(codex_event, session.id, turn.id)
                    if sse_str:
                        yield sse_str
            except Exception as exc:  # noqa: BLE001
                failed = True
                yield _sse(
                    "agent.session.turn.failed",
                    {"error": {"message": str(exc)}, "session_id": session.id},
                )

            # Update state atomically — an error event (e.g. a turn timeout)
            # must not leave the turn marked as completed. Yields stay
            # outside the lock so it is never held while streaming.
            with session._lock:
                if failed:
                    session.status = "failed"
                    turn.status = "failed"
                    session._process = None
                    session.last_active = int(time.time())
                else:
                    _finish_turn(session, turn)

            if not failed:
                yield _sse(
                    "agent.session.turn.completed",
                    {"turn_id": turn.id, "session_id": session.id, "status": "completed"},
                )

        return SSEResponse(event_iterator=event_gen())
    # Synchronous: collect all events and return completed session
    failed = False
    for codex_event in iter_codex_events(proc):
        _track_codex_event(session, codex_event, turn)
        if codex_event.get("type") == "error":
            failed = True

    with session._lock:
        if failed:
            session.status = "failed"
            turn.status = "failed"
            session._process = None
            session.last_active = int(time.time())
        else:
            _finish_turn(session, turn)
    return ServerResponse.ok(session.to_dict_with_output())


# GET /v1/agents/sessions — List sessions
@table.route("GET", "/v1/agents/sessions", group=CapabilityGroup.COMMANDS)
def list_sessions(request: ServerRequest) -> ServerResponse:
    """List all sessions."""
    sessions = store.list_all()
    return ServerResponse.ok(
        {
            "object": "list",
            "data": [s.to_dict() for s in sessions],
        }
    )


# GET /v1/agents/sessions/{session_id} — Get session
@table.route("GET", "/v1/agents/sessions/{session_id}", group=CapabilityGroup.COMMANDS)
def get_session(request: ServerRequest) -> ServerResponse:
    """Retrieve a session by ID."""
    session_id = request.path_params.get("session_id", "")
    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")
    return ServerResponse.ok(session.to_dict_with_output())


# POST /v1/agents/sessions/{session_id} — Update session
@table.route("POST", "/v1/agents/sessions/{session_id}", group=CapabilityGroup.COMMANDS)
def update_session(request: ServerRequest) -> ServerResponse:
    """Update session configuration (model / instructions)."""
    session_id = request.path_params.get("session_id", "")
    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")

    body = request.body or {}
    if "model" in body:
        session.model = body["model"]
    if "instructions" in body:
        session.instructions = body["instructions"]
    session.last_active = int(time.time())

    return ServerResponse.ok(session.to_dict())


# DELETE /v1/agents/sessions/{session_id} — Delete session
@table.route("DELETE", "/v1/agents/sessions/{session_id}", group=CapabilityGroup.COMMANDS)
def delete_session(request: ServerRequest) -> ServerResponse:
    """Delete a session."""
    session_id = request.path_params.get("session_id", "")
    if store.delete(session_id):
        return ServerResponse.ok({"id": session_id, "object": "session", "deleted": True})
    return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")


# POST /v1/agents/sessions/{session_id}/events — Send input
@table.route(
    "POST",
    "/v1/agents/sessions/{session_id}/events",
    group=CapabilityGroup.COMMANDS,
    streaming=True,
)
def send_event(request: ServerRequest) -> SSEResponse | ServerResponse:
    """Send user input to a session, starting a new turn."""
    session_id = request.path_params.get("session_id", "")
    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")

    # Conflict check, turn creation, status update and process spawn must
    # happen atomically under the session lock — otherwise two concurrent
    # requests can both pass the status check and start competing Codex
    # subprocesses.
    with session._lock:
        if session.status == "in_progress":
            return ServerResponse.error(409, "Session has an active turn", "ConflictError")

        body = request.body or {}
        input_text = _extract_input_text(body)

        if not input_text:
            return ServerResponse.error(400, "Missing input text", "ValueError")

        stream = body.get("stream", True)  # default to streaming for events endpoint

        turn = Turn()
        session.turns.append(turn)
        session.status = "in_progress"
        session.last_active = int(time.time())

        try:
            proc = spawn_codex_turn(session, input_text)
            session._process = proc
        except Exception as exc:  # noqa: BLE001
            session.status = "failed"
            turn.status = "failed"
            return ServerResponse.error(500, str(exc), "SpawnError")

    if stream:

        def event_gen() -> Iterator[str]:
            yield _sse("agent.session.turn.started", {"turn_id": turn.id, "session_id": session.id})

            failed = False
            try:
                for codex_event in iter_codex_events(proc):
                    _track_codex_event(session, codex_event, turn)

                    if codex_event.get("type") == "error":
                        failed = True

                    sse_str = map_event(codex_event, session.id, turn.id)
                    if sse_str:
                        yield sse_str
            except Exception as exc:  # noqa: BLE001
                failed = True
                yield _sse(
                    "agent.session.turn.failed",
                    {"error": {"message": str(exc)}, "session_id": session.id},
                )

            # Update state atomically — an error event (e.g. a turn timeout)
            # must not leave the turn marked as completed. Yields stay
            # outside the lock so it is never held while streaming.
            with session._lock:
                if failed:
                    session.status = "failed"
                    turn.status = "failed"
                    session._process = None
                    session.last_active = int(time.time())
                else:
                    _finish_turn(session, turn)

            if not failed:
                yield _sse(
                    "agent.session.turn.completed",
                    {"turn_id": turn.id, "session_id": session.id, "status": "completed"},
                )

        return SSEResponse(event_iterator=event_gen())
    # Synchronous mode
    failed = False
    for codex_event in iter_codex_events(proc):
        _track_codex_event(session, codex_event, turn)
        if codex_event.get("type") == "error":
            failed = True

    with session._lock:
        if failed:
            session.status = "failed"
            turn.status = "failed"
            session._process = None
            session.last_active = int(time.time())
        else:
            _finish_turn(session, turn)
    return ServerResponse.ok(session.to_dict_with_output())


# GET /v1/agents/sessions/{session_id}/events — SSE subscribe
@table.route(
    "GET",
    "/v1/agents/sessions/{session_id}/events",
    group=CapabilityGroup.COMMANDS,
    streaming=True,
)
def subscribe_events(request: ServerRequest) -> SSEResponse | ServerResponse:
    """Subscribe to the SSE event stream of the active turn."""
    session_id = request.path_params.get("session_id", "")
    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")

    if session.status != "in_progress" or not session._process:
        return ServerResponse.ok({"status": session.status, "message": "No active turn"})

    proc = session._process
    current_turn = session.turns[-1] if session.turns else None
    turn_id = current_turn.id if current_turn else "unknown"

    def event_gen() -> Iterator[str]:
        failed = False
        try:
            for codex_event in iter_codex_events(proc):
                _track_codex_event(session, codex_event, current_turn)

                if codex_event.get("type") == "error":
                    failed = True

                sse_str = map_event(codex_event, session.id, turn_id)
                if sse_str:
                    yield sse_str
        except Exception as exc:  # noqa: BLE001
            failed = True
            yield _sse(
                "agent.session.turn.failed",
                {"error": {"message": str(exc)}, "session_id": session.id},
            )

        # Update turn/session state atomically so the session does not stay
        # stuck in "in_progress" after the stream ends.
        with session._lock:
            if current_turn is not None:
                if failed:
                    session.status = "failed"
                    current_turn.status = "failed"
                    session._process = None
                    session.last_active = int(time.time())
                else:
                    _finish_turn(session, current_turn)

    return SSEResponse(event_iterator=event_gen())


# GET /v1/agents/sessions/{session_id}/items — List items
@table.route("GET", "/v1/agents/sessions/{session_id}/items", group=CapabilityGroup.COMMANDS)
def list_items(request: ServerRequest) -> ServerResponse:
    """List the output items of a session."""
    session_id = request.path_params.get("session_id", "")
    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")
    return ServerResponse.ok(
        {
            "object": "list",
            "data": session.items,
        }
    )


# ── Artifacts helpers ──────────────────────────────────────────


def _decode_artifact_path(artifact_id: str) -> str:
    """Decode an artifact ID into a workspace-relative file path.

    Artifact IDs are URL-safe base64-encoded paths (e.g. ``cmVwb3J0Lm1k``
    for ``report.md``).  Values that fail to decode are used as-is so
    plain relative paths also work.
    """
    padded = artifact_id + "=" * (-len(artifact_id) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:  # noqa: BLE001
        return artifact_id


def _resolve_artifact_path(file_path: str) -> str | None:
    """Resolve *file_path* against the workspace root, safely.

    Returns the normalised absolute path, or ``None`` when the path escapes
    the workspace (e.g. ``../../etc/passwd`` or an absolute foreign path).
    """
    root = os.path.normpath(WORKSPACE)
    full_path = os.path.normpath(os.path.join(root, file_path))
    if full_path == root or full_path.startswith(root + os.sep):
        return full_path
    return None


# GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id} — Get artifact
@table.route(
    "GET",
    "/v1/agents/sessions/{session_id}/artifacts/{artifact_id}",
    group=CapabilityGroup.COMMANDS,
)
def get_artifact(request: ServerRequest) -> ServerResponse:
    """Download a workspace file artifact produced during a session."""
    session_id = request.path_params.get("session_id", "")
    artifact_id = request.path_params.get("artifact_id", "")

    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")

    file_path = _decode_artifact_path(artifact_id)
    full_path = _resolve_artifact_path(file_path)
    if full_path is None:
        return ServerResponse.error(403, "Access denied: path outside workspace", "ForbiddenError")

    if not os.path.isfile(full_path):
        return ServerResponse.error(404, f"Artifact not found: {file_path}", "NotFoundError")

    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return ServerResponse.ok(
            {
                "id": artifact_id,
                "object": "artifact",
                "session_id": session_id,
                "file_path": file_path,
                "content": content,
                "size": os.path.getsize(full_path),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return ServerResponse.error(500, str(exc), "ReadError")


# DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id} — Delete artifact
@table.route(
    "DELETE",
    "/v1/agents/sessions/{session_id}/artifacts/{artifact_id}",
    group=CapabilityGroup.COMMANDS,
)
def delete_artifact(request: ServerRequest) -> ServerResponse:
    """Delete a workspace file artifact."""
    session_id = request.path_params.get("session_id", "")
    artifact_id = request.path_params.get("artifact_id", "")

    session = store.get(session_id)
    if not session:
        return ServerResponse.error(404, f"Session {session_id} not found", "NotFoundError")

    file_path = _decode_artifact_path(artifact_id)
    full_path = _resolve_artifact_path(file_path)
    if full_path is None:
        return ServerResponse.error(403, "Access denied: path outside workspace", "ForbiddenError")

    if not os.path.isfile(full_path):
        return ServerResponse.error(404, f"Artifact not found: {file_path}", "NotFoundError")

    try:
        os.remove(full_path)
        return ServerResponse.ok({"id": artifact_id, "object": "artifact", "deleted": True})
    except Exception as exc:  # noqa: BLE001
        return ServerResponse.error(500, str(exc), "DeleteError")


# ── Saved agents CRUD routes ─────────────────────────────────────
#
# NOTE: these generic ``/v1/agents/{agent_id}`` routes are deliberately
# registered AFTER the session routes above — RouteTable matches in
# registration order (linear scan), so the literal ``/v1/agents/sessions``
# paths win over the ``{agent_id}`` placeholder.


# POST /v1/agents — Create agent
@table.route("POST", "/v1/agents", group=CapabilityGroup.COMMANDS)
def create_agent(request: ServerRequest) -> ServerResponse:
    """Create a reusable agent configuration."""
    body = request.body or {}
    agent = agent_store.create(
        model=body.get("model", DEFAULT_MODEL),
        instructions=body.get("instructions", ""),
        tools=body.get("tools", []),
        name=body.get("name", ""),
        metadata=body.get("metadata", {}),
    )
    return ServerResponse.ok(agent.to_dict())


# GET /v1/agents — List agents
@table.route("GET", "/v1/agents", group=CapabilityGroup.COMMANDS)
def list_agents(request: ServerRequest) -> ServerResponse:
    """List all saved agents."""
    agents = agent_store.list_all()
    return ServerResponse.ok({"object": "list", "data": [a.to_dict() for a in agents]})


# GET /v1/agents/{agent_id} — Get agent
@table.route("GET", "/v1/agents/{agent_id}", group=CapabilityGroup.COMMANDS)
def get_agent(request: ServerRequest) -> ServerResponse:
    """Retrieve a saved agent by ID."""
    agent_id = request.path_params.get("agent_id", "")
    agent = agent_store.get(agent_id)
    if not agent:
        return ServerResponse.error(404, f"Agent {agent_id} not found", "NotFoundError")
    return ServerResponse.ok(agent.to_dict())


# POST /v1/agents/{agent_id} — Update agent
@table.route("POST", "/v1/agents/{agent_id}", group=CapabilityGroup.COMMANDS)
def update_agent(request: ServerRequest) -> ServerResponse:
    """Update a saved agent's model / instructions / tools / name / metadata."""
    agent_id = request.path_params.get("agent_id", "")
    body = request.body or {}
    updates = {
        k: v for k, v in body.items() if k in ("model", "instructions", "tools", "name", "metadata")
    }
    agent = agent_store.update(agent_id, **updates)
    if not agent:
        return ServerResponse.error(404, f"Agent {agent_id} not found", "NotFoundError")
    return ServerResponse.ok(agent.to_dict())


# DELETE /v1/agents/{agent_id} — Delete agent
@table.route("DELETE", "/v1/agents/{agent_id}", group=CapabilityGroup.COMMANDS)
def delete_agent(request: ServerRequest) -> ServerResponse:
    """Delete a saved agent."""
    agent_id = request.path_params.get("agent_id", "")
    if agent_store.delete(agent_id):
        return ServerResponse.ok({"id": agent_id, "object": "agent", "deleted": True})
    return ServerResponse.error(404, f"Agent {agent_id} not found", "NotFoundError")


# ── Serve ──────────────────────────────────────────────────────────

registry.freeze()
server = SandboxServer(registry=registry)
server.serve(port=9000)
