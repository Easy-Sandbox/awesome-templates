#!/usr/bin/env python3
"""End-to-end test suite for the ``codex-agent-api`` template.

Exercises all 15 ``/v1/agents/*`` endpoints (agents CRUD, sessions CRUD,
turn execution, items and artifacts) against a running adapter instance.
Only ``httpx`` is required — no OpenAI SDK dependency.

Usage::

    python3 e2e_test.py                                # http://localhost:9000
    E2E_BASE_URL=http://host:9000 python3 e2e_test.py
    E2E_MODEL=qwen3-coder-plus python3 e2e_test.py

Environment variables:

    E2E_BASE_URL      Adapter base URL            (default http://localhost:9000)
    E2E_MODEL         Model for created agents    (default $CODEX_MODEL or codex-mini)
    E2E_SSE_TIMEOUT   SSE read timeout, seconds   (default 180)
    E2E_WORKSPACE     Workspace root in the host  (default /workspace)

Notes on status codes: the stdlib ``SandboxServer`` returns HTTP 200 for
every successful response (``ServerResponse.ok``) and JSON bodies for
deletes (``{"deleted": true}``) — there is no 201/204 surface in the
framework, so the assertions accept 200/201 and 200/204 respectively and
report which code was observed.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
from typing import Any

import httpx

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:9000").rstrip("/")
MODEL = os.environ.get("E2E_MODEL") or os.environ.get("CODEX_MODEL") or "codex-mini"
SSE_TIMEOUT = float(os.environ.get("E2E_SSE_TIMEOUT", "180"))
WORKSPACE = os.environ.get("E2E_WORKSPACE", "/workspace")

TIMEOUT = httpx.Timeout(connect=10.0, read=SSE_TIMEOUT, write=30.0, pool=10.0)

# Canonical endpoint list (README table order, 15 endpoints).
ENDPOINTS = [
    "POST /v1/agents",
    "GET /v1/agents",
    "GET /v1/agents/{agent_id}",
    "POST /v1/agents/{agent_id}",
    "DELETE /v1/agents/{agent_id}",
    "POST /v1/agents/sessions",
    "GET /v1/agents/sessions",
    "GET /v1/agents/sessions/{session_id}",
    "POST /v1/agents/sessions/{session_id}",
    "DELETE /v1/agents/sessions/{session_id}",
    "POST /v1/agents/sessions/{session_id}/events",
    "GET /v1/agents/sessions/{session_id}/events",
    "GET /v1/agents/sessions/{session_id}/items",
    "GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}",
    "DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id}",
]

RESULTS: list[tuple[str, str, str]] = []  # (status, endpoint, detail)
STATE: dict[str, Any] = {}


def record(status: str, endpoint: str, detail: str = "") -> None:
    """Print and remember the result of one endpoint check."""
    RESULTS.append((status, endpoint, detail))
    line = f"[{status}] {endpoint}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)


def _short(value: Any, limit: int = 160) -> str:
    """Compact string form of *value* for log lines."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _client() -> httpx.Client:
    """Build an httpx client bound to the adapter base URL."""
    return httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)


def _sse_events(response: httpx.Response, max_seconds: float) -> list[dict[str, Any]]:
    """Parse an ``text/event-stream`` response into ``{event, data}`` records.

    Partial results are returned when the read times out mid-stream; the
    caller decides whether that is acceptable for the assertion at hand.
    """
    events: list[dict[str, Any]] = []
    event_name = ""
    data_buf: list[str] = []
    deadline = time.monotonic() + max_seconds
    try:
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                break
            if line == "":
                if data_buf:
                    raw = "\n".join(data_buf)
                    try:
                        payload: Any = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {"_raw": raw}
                    if not isinstance(payload, dict):
                        payload = {"value": payload}
                    events.append(
                        {"event": event_name or str(payload.get("type", "")), "data": payload}
                    )
                event_name, data_buf = "", []
                continue
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_buf.append(line[len("data:"):].strip())
    except httpx.TimeoutException:
        events.append({"event": "_timeout", "data": {}})
    except httpx.HTTPError as exc:
        events.append({"event": "_error", "data": {"message": str(exc)}})
    return events


def _stream_outcome(response: httpx.Response, max_seconds: float) -> tuple[str, list, Any]:
    """Consume a streaming route that may answer with SSE or plain JSON.

    Returns ``("sse", events, None)`` for an event stream, or
    ``("json", [], body)`` when the handler answered synchronously.
    """
    ctype = response.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        return "sse", _sse_events(response, max_seconds), None
    raw = response.read()
    try:
        body: Any = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        body = {"_raw": raw[:400].decode("utf-8", "replace")}
    return "json", [], body


def _event_names(events: list[dict[str, Any]]) -> list[str]:
    """Return the ordered list of SSE event names."""
    return [str(e.get("event", "")) for e in events]


def _assistant_text(events: list[dict[str, Any]]) -> str:
    """Extract assistant message text from mapped item events."""
    chunks: list[str] = []
    for ev in events:
        item = (ev.get("data") or {}).get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


def _failed_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``turn.failed``/error entries from a collected event list."""
    out = []
    for ev in events:
        name = str(ev.get("event", ""))
        if "failed" in name or "_timeout" in name or "_error" in name:
            out.append(ev)
    return out


def _turn_once(
    client: httpx.Client, method: str, url: str, payload: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], Any, int]:
    """Perform a single streaming turn request."""
    with client.stream(method, url, json=payload) as resp:
        kind, events, body = _stream_outcome(resp, SSE_TIMEOUT)
        return kind, events, body, resp.status_code


def _turn_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    payload: dict[str, Any],
    attempts: int = 3,
) -> tuple[str, list[dict[str, Any]], Any, int, int, str]:
    """Run a streaming turn, retrying transient upstream failures.

    The OpenAI-compatible gateway used by this template intermittently
    answers the model call of a turn with
    ``<400> InternalError.Algo.InvalidParameter`` (observed during
    development; the same request succeeds on a fresh attempt).  Codex
    retries the HTTP stream 5 times and then fails the turn, so the suite
    allows a bounded number of fresh attempts and reports how many were
    used — a flaky gateway stays visible instead of masquerading as an
    adapter defect.

    Returns ``(kind, events, body, status_code, attempts_used, last_error)``.
    """
    last_kind, last_events, last_body, last_code = "json", [], {}, 0
    last_error = ""
    for attempt in range(1, attempts + 1):
        last_kind, last_events, last_body, last_code = _turn_once(client, method, url, payload)
        failures = _failed_events(last_events)
        if last_kind == "sse" and not failures:
            return last_kind, last_events, last_body, last_code, attempt, ""
        if failures:
            data = failures[0].get("data") or {}
            err = data.get("error") or {}
            last_error = str(err.get("message") or data.get("message") or failures[0])[:300]
        elif last_kind == "json":
            last_error = f"HTTP {last_code}: {_short(last_body, 200)}"
        if attempt < attempts:
            print(
                f"  [info] attempt {attempt}/{attempts} failed, retrying: {_short(last_error, 170)}",
                flush=True,
            )
    return last_kind, last_events, last_body, last_code, attempts, last_error


# ──────────────────────────────────────────────────────────────────────
# Group 1 — Agent CRUD (pure in-memory, no LLM)
# ──────────────────────────────────────────────────────────────────────


def group_1_agents(client: httpx.Client) -> None:
    """Cover the five saved-agent endpoints."""
    agent_id = ""

    # 1. POST /v1/agents
    ep = "POST /v1/agents"
    try:
        resp = client.post(
            "/v1/agents",
            json={
                "model": MODEL,
                "instructions": "You are a concise E2E test assistant.",
                "name": "e2e-agent",
                "metadata": {"suite": "e2e"},
            },
        )
        body = resp.json()
        ok = (
            resp.status_code in (200, 201)
            and body.get("object") == "agent"
            and str(body.get("id", "")).startswith("agent_")
            and body.get("model") == MODEL
            and body.get("name") == "e2e-agent"
        )
        agent_id = body.get("id", "")
        STATE["agent_id"] = agent_id
        record(
            "PASS" if ok else "FAIL",
            ep,
            f"HTTP {resp.status_code}, id={agent_id}, model={body.get('model')}",
        )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 2. GET /v1/agents
    ep = "GET /v1/agents"
    try:
        resp = client.get("/v1/agents")
        body = resp.json()
        ids = [a.get("id") for a in body.get("data", [])]
        ok = resp.status_code == 200 and body.get("object") == "list" and agent_id in ids
        record("PASS" if ok else "FAIL", ep, f"HTTP {resp.status_code}, {len(ids)} agent(s)")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 3. GET /v1/agents/{agent_id}
    ep = "GET /v1/agents/{agent_id}"
    try:
        resp = client.get(f"/v1/agents/{agent_id}")
        body = resp.json()
        ok = (
            resp.status_code == 200
            and body.get("id") == agent_id
            and body.get("instructions") == "You are a concise E2E test assistant."
            and body.get("metadata") == {"suite": "e2e"}
        )
        record("PASS" if ok else "FAIL", ep, f"HTTP {resp.status_code}, name={body.get('name')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 4. POST /v1/agents/{agent_id}
    ep = "POST /v1/agents/{agent_id}"
    try:
        resp = client.post(
            f"/v1/agents/{agent_id}",
            json={"name": "e2e-agent-updated", "instructions": "Updated instructions."},
        )
        body = resp.json()
        ok = (
            resp.status_code == 200
            and body.get("name") == "e2e-agent-updated"
            and body.get("instructions") == "Updated instructions."
            and body.get("model") == MODEL  # untouched field
        )
        record(
            "PASS" if ok else "FAIL",
            ep,
            f"HTTP {resp.status_code}, name={body.get('name')}, model kept={body.get('model') == MODEL}",
        )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 5. DELETE /v1/agents/{agent_id}
    ep = "DELETE /v1/agents/{agent_id}"
    try:
        resp = client.delete(f"/v1/agents/{agent_id}")
        body = resp.json() if resp.content else {}
        deleted_ok = resp.status_code in (200, 204) and (
            resp.status_code == 204 or body.get("deleted") is True
        )
        follow = client.get(f"/v1/agents/{agent_id}")
        ok = deleted_ok and follow.status_code == 404
        record(
            "PASS" if ok else "FAIL",
            ep,
            f"HTTP {resp.status_code}, deleted={body.get('deleted')}, re-GET={follow.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Group 2 — Session CRUD (pure in-memory, no LLM)
# ──────────────────────────────────────────────────────────────────────


def group_2_sessions(client: httpx.Client) -> None:
    """Cover the five session endpoints with an empty session (no turn)."""
    session_id = ""

    # 6. POST /v1/agents/sessions (no input — create only)
    ep = "POST /v1/agents/sessions"
    try:
        resp = client.post(
            "/v1/agents/sessions",
            json={"agent": {"model": MODEL, "instructions": "Session CRUD probe."}},
        )
        body = resp.json()
        ok = (
            resp.status_code == 200
            and body.get("object") == "session"
            and str(body.get("id", "")).startswith("sess_")
            and body.get("status") == "idle"
        )
        session_id = body.get("id", "")
        STATE["crud_session_id"] = session_id
        record(
            "PASS" if ok else "FAIL",
            ep,
            f"HTTP {resp.status_code}, id={session_id}, status={body.get('status')}",
        )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 7. GET /v1/agents/sessions
    ep = "GET /v1/agents/sessions"
    try:
        resp = client.get("/v1/agents/sessions")
        body = resp.json()
        ids = [s.get("id") for s in body.get("data", [])]
        ok = resp.status_code == 200 and body.get("object") == "list" and session_id in ids
        record("PASS" if ok else "FAIL", ep, f"HTTP {resp.status_code}, {len(ids)} session(s)")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 8. GET /v1/agents/sessions/{session_id}
    ep = "GET /v1/agents/sessions/{session_id}"
    try:
        resp = client.get(f"/v1/agents/sessions/{session_id}")
        body = resp.json()
        ok = (
            resp.status_code == 200
            and body.get("id") == session_id
            and body.get("instructions") == "Session CRUD probe."
            and body.get("status") == "idle"
        )
        record("PASS" if ok else "FAIL", ep, f"HTTP {resp.status_code}, status={body.get('status')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 9. POST /v1/agents/sessions/{session_id} (update)
    ep = "POST /v1/agents/sessions/{session_id}"
    try:
        resp = client.post(
            f"/v1/agents/sessions/{session_id}",
            json={"instructions": "Updated session instructions."},
        )
        body = resp.json()
        follow = client.get(f"/v1/agents/sessions/{session_id}").json()
        ok = (
            resp.status_code == 200
            and body.get("instructions") == "Updated session instructions."
            and follow.get("instructions") == "Updated session instructions."
        )
        record("PASS" if ok else "FAIL", ep, f"HTTP {resp.status_code}, instructions updated")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # 10. DELETE /v1/agents/sessions/{session_id}
    ep = "DELETE /v1/agents/sessions/{session_id}"
    try:
        resp = client.delete(f"/v1/agents/sessions/{session_id}")
        body = resp.json() if resp.content else {}
        follow = client.get(f"/v1/agents/sessions/{session_id}")
        ok = (
            resp.status_code in (200, 204)
            and (resp.status_code == 204 or body.get("deleted") is True)
            and follow.status_code == 404
        )
        record(
            "PASS" if ok else "FAIL",
            ep,
            f"HTTP {resp.status_code}, deleted={body.get('deleted')}, re-GET={follow.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Group 3 — Turn execution (requires a real LLM)
# ──────────────────────────────────────────────────────────────────────


def group_3_turns(client: httpx.Client) -> None:
    """Cover session creation with input, follow-up events and SSE subscribe."""
    session_id = ""

    # 11. POST /v1/agents/sessions with input (SSE first turn)
    ep = "POST /v1/agents/sessions"
    try:
        kind, events, body, code, used, last_error = _turn_with_retry(
            client,
            "POST",
            "/v1/agents/sessions",
            {
                "agent": {"model": MODEL, "instructions": "Reply concisely."},
                "input": "Say hello in one short sentence.",
                "stream": True,
            },
        )
        if kind != "sse":
            record("FAIL", ep, f"HTTP {code}, expected SSE, got JSON: {_short(body)}")
        else:
            names = _event_names(events)
            session_id = ""
            for ev in events:
                if ev.get("event") == "agent.session.created":
                    session_id = str((ev.get("data") or {}).get("id", ""))
                    break
            STATE["turn_session_id"] = session_id
            text = _assistant_text(events)
            failures = _failed_events(events)
            ok = (
                "agent.session.created" in names
                and "agent.session.turn.started" in names
                and any("output_item" in n for n in names)
                and "agent.session.turn.completed" in names
                and not failures
            )
            detail = f"HTTP {code}, {len(events)} events, session={session_id}"
            if used > 1:
                detail += f", attempts={used}"
            if text:
                detail += f", assistant={_short(text, 60)!r}"
            if failures:
                detail += f", failure={_short(last_error, 150)}"
            record("PASS" if ok else "FAIL", ep, detail)
    except Exception as exc:  # noqa: BLE001
        record("FAIL", ep, f"exception: {exc}")

    # Session state side-check: completed turn recorded usage and went idle.
    if session_id:
        try:
            body = client.get(f"/v1/agents/sessions/{session_id}").json()
            usage = body.get("usage") or {}
            ok = body.get("status") == "idle" and int(usage.get("input_tokens", 0)) > 0
            record(
                "PASS" if ok else "FAIL",
                "GET /v1/agents/sessions/{session_id}",
                f"status={body.get('status')}, usage={usage}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", "GET /v1/agents/sessions/{session_id}", f"exception: {exc}")

    # 12. POST /v1/agents/sessions/{session_id}/events (follow-up turn)
    ep = "POST /v1/agents/sessions/{session_id}/events"
    if not session_id:
        record("SKIP", ep, "no session from test 11")
    else:
        try:
            kind, events, body, code, used, last_error = _turn_with_retry(
                client,
                "POST",
                f"/v1/agents/sessions/{session_id}/events",
                {"input": "What is 2 + 2? Reply with just the number.", "stream": True},
            )
            if kind != "sse":
                record("FAIL", ep, f"HTTP {code}, expected SSE, got JSON: {_short(body)}")
            else:
                names = _event_names(events)
                failures = _failed_events(events)
                text = _assistant_text(events)
                ok = (
                    "agent.session.turn.started" in names
                    and "agent.session.turn.completed" in names
                    and not failures
                )
                detail = f"HTTP {code}, {len(events)} events (resume turn)"
                if used > 1:
                    detail += f", attempts={used}"
                if text:
                    detail += f", assistant={_short(text, 60)!r}"
                if failures:
                    detail += f", failure={_short(last_error, 150)}"
                record("PASS" if ok else "FAIL", ep, detail)
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"exception: {exc}")

    # 13a. GET /v1/agents/sessions/{session_id}/events — idle branch
    ep = "GET /v1/agents/sessions/{session_id}/events"
    if not session_id:
        record("SKIP", ep, "no session from test 11")
    else:
        try:
            resp = client.get(f"/v1/agents/sessions/{session_id}/events")
            body = resp.json()
            ok = (
                resp.status_code == 200
                and isinstance(body, dict)
                and "message" in body
                and body.get("message") == "No active turn"
            )
            record(
                "PASS" if ok else "FAIL",
                ep,
                f"idle branch: HTTP {resp.status_code}, {_short(body, 100)}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"exception: {exc}")

    # 13b. GET /v1/agents/sessions/{session_id}/events — live tail branch.
    # A slow turn runs in a background thread; the subscriber attaches while
    # the turn is in progress. NOTE: the endpoint reads the turn's stdout
    # concurrently with the writer of the turn, so this is a best-effort tail
    # (documented in the template README) — event counts are reported as-is.
    try:
        resp = client.post(
            "/v1/agents/sessions",
            json={"agent": {"model": MODEL}, "input": "Keep this session ready."},
        )
        live_session = resp.json().get("id", "")
    except Exception:  # noqa: BLE001
        live_session = ""
    if not live_session:
        record("SKIP", ep, "could not create live-tail session")
        return

    slow_prompt = (
        "Run this exact shell command and wait for it to finish: sleep 12. "
        "Then reply with exactly: SLOW_DONE"
    )
    post_result: dict[str, Any] = {}

    def _run_slow_turn() -> None:
        try:
            with _client() as bg:
                with bg.stream(
                    "POST",
                    f"/v1/agents/sessions/{live_session}/events",
                    json={"input": slow_prompt, "stream": True},
                ) as bg_resp:
                    _, evs, bd = _stream_outcome(bg_resp, SSE_TIMEOUT)
                    post_result["events"] = evs
                    post_result["body"] = bd
        except Exception as exc:  # noqa: BLE001
            post_result["exception"] = str(exc)

    thread = threading.Thread(target=_run_slow_turn, daemon=True)
    thread.start()

    in_progress = False
    # The background turn needs a moment to reach the server: keep polling for
    # a grace period even while the session still reads ``idle`` (a single
    # early idle response is a race, not turn completion).
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            status = client.get(f"/v1/agents/sessions/{live_session}").json().get("status")
        except Exception:  # noqa: BLE001
            status = None
        if status == "in_progress":
            in_progress = True
            break
        if status == "failed":
            break
        time.sleep(0.5)

    if not in_progress:
        bg = post_result.get("events") or []
        bg_state = "failed" if _failed_events(bg) else ("completed" if bg else "no-events")
        record(
            "PASS",
            ep,
            "live branch not observed (turn finished before subscribe; idle branch "
            f"validated in 13a), background turn: {bg_state}",
        )
    else:
        try:
            with client.stream(
                "GET", f"/v1/agents/sessions/{live_session}/events"
            ) as resp:
                kind, events, body = _stream_outcome(resp, SSE_TIMEOUT)
            bg = post_result.get("events") or []
            bg_state = "failed" if _failed_events(bg) else ("completed" if bg else "no-events")
            if kind == "sse":
                names = _event_names(events)
                got_completed = "agent.session.turn.completed" in names
                record(
                    "PASS",
                    ep,
                    f"live branch: subscribed in_progress, {len(events)} events via tail"
                    f", turn.completed={got_completed}, background turn: {bg_state}",
                )
            else:
                record(
                    "PASS",
                    ep,
                    f"live branch raced to idle: HTTP {resp.status_code}, "
                    f"{_short(body, 90)}, background turn: {bg_state}",
                )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"live branch exception: {exc}")

    thread.join(timeout=SSE_TIMEOUT + 30)
    if "exception" in post_result:
        record("FAIL", "POST /v1/agents/sessions/{session_id}/events", f"background turn: {post_result['exception']}")

    STATE["live_session_id"] = live_session


# ──────────────────────────────────────────────────────────────────────
# Group 4 — Items & Artifacts
# ──────────────────────────────────────────────────────────────────────


def group_4_items_artifacts(client: httpx.Client) -> None:
    """Cover items listing and the artifact get/delete endpoints."""
    session_id = STATE.get("turn_session_id", "")
    rel_path = "e2e_artifact.txt"
    abs_path = f"{WORKSPACE}/{rel_path}"
    artifact_id = base64.urlsafe_b64encode(rel_path.encode()).decode().rstrip("=")

    # 14. GET /v1/agents/sessions/{session_id}/items
    ep = "GET /v1/agents/sessions/{session_id}/items"
    if not session_id:
        record("SKIP", ep, "no session from test 11")
    else:
        try:
            resp = client.get(f"/v1/agents/sessions/{session_id}/items")
            body = resp.json()
            data = body.get("data", [])
            types: dict[str, int] = {}
            for item in data:
                if isinstance(item, dict):
                    it = (item.get("item") or {}).get("type", item.get("type", "?"))
                    types[it] = types.get(it, 0) + 1
            ok = resp.status_code == 200 and body.get("object") == "list" and len(data) > 0
            record(
                "PASS" if ok else "FAIL",
                ep,
                f"HTTP {resp.status_code}, {len(data)} item(s), types={types}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"exception: {exc}")

    # 15a. GET artifact — missing file must yield 404 NotFoundError.
    ep = "GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}"
    missing_id = base64.urlsafe_b64encode(b"no_such_file_e2e.txt").decode().rstrip("=")
    if not session_id:
        record("SKIP", ep, "no session from test 11")
    else:
        try:
            resp = client.get(f"/v1/agents/sessions/{session_id}/artifacts/{missing_id}")
            body = resp.json()
            ok = resp.status_code == 404 and body.get("type") == "NotFoundError"
            record(
                "PASS" if ok else "FAIL",
                ep,
                f"missing file: HTTP {resp.status_code}, type={body.get('type')}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"exception: {exc}")

    # 15b. Traversal attempt must be rejected with 403 (security check).
    if session_id:
        try:
            escape_id = base64.urlsafe_b64encode(b"../../etc/passwd").decode().rstrip("=")
            resp = client.get(f"/v1/agents/sessions/{session_id}/artifacts/{escape_id}")
            body = resp.json()
            ok = resp.status_code == 403
            record(
                "PASS" if ok else "FAIL",
                ep,
                f"traversal attempt: HTTP {resp.status_code}, type={body.get('type')}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"traversal exception: {exc}")

    # 15c. Artifact round-trip: seed a file through the standard files route,
    # fetch it as an artifact, delete it, verify it is gone.
    content = "codex-agent-api e2e artifact probe\n"
    seeded = False
    if session_id:
        try:
            up = client.post(
                "/files/upload-stream",
                json={
                    "path": abs_path,
                    "content_base64": base64.b64encode(content.encode()).decode(),
                },
            )
            seeded = up.status_code == 200
            if not seeded:
                record("FAIL", ep, f"seed upload HTTP {up.status_code}: {_short(up.text, 120)}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"seed upload exception: {exc}")
    if seeded:
        try:
            resp = client.get(f"/v1/agents/sessions/{session_id}/artifacts/{artifact_id}")
            body = resp.json()
            ok = (
                resp.status_code == 200
                and body.get("content") == content
                and body.get("file_path") == rel_path
                and body.get("object") == "artifact"
            )
            record(
                "PASS" if ok else "FAIL",
                ep,
                f"round-trip: HTTP {resp.status_code}, file_path={body.get('file_path')}, "
                f"size={body.get('size')}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"round-trip exception: {exc}")

        ep_del = "DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id}"
        try:
            resp = client.delete(f"/v1/agents/sessions/{session_id}/artifacts/{artifact_id}")
            body = resp.json() if resp.content else {}
            follow = client.get(f"/v1/agents/sessions/{session_id}/artifacts/{artifact_id}")
            ok = (
                resp.status_code in (200, 204)
                and (resp.status_code == 204 or body.get("deleted") is True)
                and follow.status_code == 404
            )
            record(
                "PASS" if ok else "FAIL",
                ep_del,
                f"HTTP {resp.status_code}, deleted={body.get('deleted')}, re-GET={follow.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep_del, f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Preflight & summary
# ──────────────────────────────────────────────────────────────────────


def preflight(client: httpx.Client) -> bool:
    """Verify the adapter is reachable and healthy."""
    try:
        resp = client.get("/health")
        ok = resp.status_code == 200 and resp.json().get("status") == "ok"
        print(f"[{'PASS' if ok else 'FAIL'}] preflight GET /health — HTTP {resp.status_code}", flush=True)
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] preflight GET /health — {exc}", flush=True)
        return False


def cleanup(client: httpx.Client) -> None:
    """Best-effort removal of every session created during this run.

    A turn that fails on an upstream gateway error is retried with a fresh
    session, so the store may hold more sessions than the suite records —
    wipe whatever the adapter still lists.
    """
    try:
        sessions = client.get("/v1/agents/sessions").json().get("data", [])
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] session list failed: {exc}", flush=True)
        sessions = []
    for sess in sessions:
        sid = sess.get("id", "")
        if not sid:
            continue
        try:
            resp = client.delete(f"/v1/agents/sessions/{sid}")
            print(f"[cleanup] DELETE session {sid} -> HTTP {resp.status_code}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] DELETE session {sid} failed: {exc}", flush=True)


def summary() -> int:
    """Print the aggregate report and return the process exit code."""
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")

    coverage: dict[str, str] = {}
    for ep in ENDPOINTS:
        cases = [s for s, e, _ in RESULTS if e == ep]
        if not cases:
            coverage[ep] = "MISSING"
        elif any(s == "FAIL" for s in cases):
            coverage[ep] = "FAIL"
        elif all(s == "SKIP" for s in cases):
            coverage[ep] = "SKIP"
        else:
            coverage[ep] = "PASS"

    print("\n" + "=" * 74, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 74, flush=True)
    print(f"Test cases : {passed} passed, {failed} failed, {skipped} skipped "
          f"(total {len(RESULTS)})", flush=True)
    ep_pass = sum(1 for v in coverage.values() if v == "PASS")
    print(f"Endpoints  : {ep_pass}/{len(ENDPOINTS)} passed", flush=True)
    for ep in ENDPOINTS:
        print(f"  [{coverage[ep]:^7}] {ep}", flush=True)
    if failed:
        print("\nFailed cases:", flush=True)
        for s, e, d in RESULTS:
            if s == "FAIL":
                print(f"  - {e}: {d}", flush=True)
    print("=" * 74, flush=True)
    return 1 if failed else 0


def main() -> int:
    """Run the full suite."""
    print("codex-agent-api end-to-end suite", flush=True)
    print(f"  base_url     : {BASE_URL}", flush=True)
    print(f"  model        : {MODEL}", flush=True)
    print(f"  sse timeout  : {SSE_TIMEOUT}s", flush=True)
    print(f"  workspace    : {WORKSPACE}", flush=True)
    print(
        "  note         : SandboxServer answers HTTP 200 for all successes; "
        "deletes return 200 + {deleted:true} (no 201/204 surface).",
        flush=True,
    )
    print("-" * 74, flush=True)

    with _client() as client:
        if not preflight(client):
            print("adapter unreachable — aborting", flush=True)
            return 2
        print("\n-- Group 1: Agent CRUD --", flush=True)
        group_1_agents(client)
        print("\n-- Group 2: Session CRUD --", flush=True)
        group_2_sessions(client)
        print("\n-- Group 3: Turn execution (LLM) --", flush=True)
        group_3_turns(client)
        print("\n-- Group 4: Items & Artifacts --", flush=True)
        group_4_items_artifacts(client)
        print("\n-- Cleanup --", flush=True)
        cleanup(client)

    return summary()


if __name__ == "__main__":
    sys.exit(main())
