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
import json
import os
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
        d["usage"] = {"input_tokens": 0, "output_tokens": 0}  # placeholder
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


# ── Codex CLI adapter ──────────────────────────────────────────────────


def spawn_codex_turn(session: Session, input_text: str) -> subprocess.Popen[bytes]:
    """Spawn a ``codex exec`` process for a new turn."""
    cmd = [
        "codex",
        "exec",
        "--json",
        "--sandbox",
        "danger-full-access",
        "--skip-git-repo-check",
        "--model",
        session.model,
    ]
    # For subsequent turns, try resume
    if session.turns:
        cmd.extend(["resume", "--last"])
    cmd.append(input_text)

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/workspace",
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
    proc.wait()


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
                    # Accumulate items
                    if codex_event.get("type") in ("item.completed", "item.started"):
                        session.items.append(codex_event)
                        turn.items.append(codex_event)

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
        if codex_event.get("type") in ("item.completed", "item.started"):
            session.items.append(codex_event)
            turn.items.append(codex_event)
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
                    if codex_event.get("type") in ("item.completed", "item.started"):
                        session.items.append(codex_event)
                        turn.items.append(codex_event)

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
        if codex_event.get("type") in ("item.completed", "item.started"):
            session.items.append(codex_event)
            turn.items.append(codex_event)
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
                if codex_event.get("type") in ("item.completed", "item.started"):
                    session.items.append(codex_event)
                    if current_turn:
                        current_turn.items.append(codex_event)

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


# ── Serve ──────────────────────────────────────────────────────────────

registry.freeze()
server = SandboxServer(registry=registry)
server.serve(port=9000)
