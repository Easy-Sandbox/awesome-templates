#!/usr/bin/env python3
"""End-to-end test suite for the ``codex`` template.

Exercises built-in routes (/health, /commands), the registered ``codex``
command (Codex CLI), FILE_OPS file round-trip and PROCESS shell/process
control against a running sandbox server.

The ``codex`` command invokes the Codex CLI inside the sandbox and needs
``OPENAI_API_KEY``; when no key is visible on the host running this script
the LLM case is reported as ``[SKIP]`` (see ``E2E_RUN_LLM`` to override).

Usage::

    python3 e2e_test.py                                # http://localhost:9000
    E2E_BASE_URL=http://host:9000 python3 e2e_test.py
    OPENAI_API_KEY=sk-xxx python3 e2e_test.py          # enables the LLM case

Environment variables:

    E2E_BASE_URL     Server base URL                     (default http://localhost:9000)
    E2E_TOKEN        X-Access-Token header value          (default: none — local mode)
    E2E_BASE_DIR     File-ops root inside the container   (default /home/user)
    E2E_TIMEOUT      HTTP read timeout in seconds         (default 60)
    E2E_LLM_TIMEOUT  Timeout for the LLM command call     (default 420)
    E2E_RUN_LLM      1 = force the LLM case, 0 = skip it  (default: auto-detect key)
    E2E_MODEL        Override the ``model`` argument      (default: command default)

Notes:

- ``/health`` (CORE) and ``/commands`` (COMMANDS) are always registered;
  FILE_OPS and PROCESS are enabled by this template's ``commands.py``.
- File paths are constrained by the server to ``EBX_SERVER_BASE_DIR``
  (default ``/home/user``); keep ``E2E_BASE_DIR`` inside that root.
- The host-side key check is a proxy: the key must also be visible
  *inside* the sandbox for the LLM case to actually succeed.
- The ``codex`` command's CLI contract (see ``commands.py``):
  ``codex -p <prompt> --model <model> --yolo --output-format json``.

Only ``httpx`` is required — no SDK dependency.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from typing import Any

import httpx

TEMPLATE = "codex"
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:9000").rstrip("/")
TOKEN = os.environ.get("E2E_TOKEN", "")
BASE_DIR = os.environ.get("E2E_BASE_DIR", "/home/user").rstrip("/") or "/home/user"
TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=float(os.environ.get("E2E_TIMEOUT", "60")),
    write=30.0,
    pool=10.0,
)
LLM_TIMEOUT = float(os.environ.get("E2E_LLM_TIMEOUT", "420"))
MODEL = os.environ.get("E2E_MODEL", "")
RUN_LLM = os.environ.get("E2E_RUN_LLM", "").strip().lower()

# ── Template contract (see commands.py / template.yaml) ────────────────
CMD = "codex"
CMD_ARGS = {"prompt": "string", "model": "string"}  # name -> expected type
REQUIRED_ARGS = ("prompt",)  # required args of CMD (validated by the server)
KEY_ENVS = ("OPENAI_API_KEY",)  # host env vars that enable the LLM case
LLM_PROMPT = "Reply with exactly: EBX_E2E_OK"

PROBE_DIR = f"{BASE_DIR}/ebx_e2e_{TEMPLATE}"
PROBE_FILE = f"{PROBE_DIR}/probe.txt"

RESULTS: list[tuple[str, str, str]] = []  # (status, test, detail)
STATE: dict[str, Any] = {}


def record(status: str, test: str, detail: str = "") -> None:
    """Print and remember the result of one check."""
    RESULTS.append((status, test, detail))
    line = f"[{status}] {test}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)


def _short(value: object, limit: int = 160) -> str:
    """Compact string form of *value* for log lines."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _client() -> httpx.Client:
    """Build an httpx client bound to the server base URL."""
    headers = {"X-Access-Token": TOKEN} if TOKEN else {}
    return httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, headers=headers)


def _group_on(name: str) -> bool:
    """Return whether capability group *name* is enabled (default: assume yes)."""
    groups = STATE.get("groups")
    if not isinstance(groups, dict):
        return True  # probe unavailable — attempt anyway, failures stay visible
    return bool(groups.get(name, True))


def _read_sse(response: httpx.Response, max_seconds: float) -> list[dict[str, Any]]:
    """Parse a ``text/event-stream`` response into ``{event, data}`` records."""
    events: list[dict[str, Any]] = []
    event_name = ""
    data_buf: list[str] = []
    deadline = time.monotonic() + max_seconds
    try:
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                events.append({"event": "_timeout", "data": {}})
                break
            if line == "":
                if data_buf:
                    raw = "\n".join(data_buf)
                    try:
                        payload: Any = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {"_raw": raw}
                    events.append({"event": event_name, "data": payload})
                event_name, data_buf = "", []
                continue
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_buf.append(line[len("data:"):].strip())
    except httpx.HTTPError as exc:
        events.append({"event": "_error", "data": {"message": str(exc)}})
    return events


def preflight(client: httpx.Client) -> bool:
    """Verify the server is reachable and healthy."""
    try:
        resp = client.get("/health")
        ok = resp.status_code == 200 and resp.json().get("status") == "ok"
        print(f"[{'PASS' if ok else 'FAIL'}] preflight GET /health — HTTP {resp.status_code}",
              flush=True)
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] preflight GET /health — {exc}", flush=True)
        return False


# ──────────────────────────────────────────────────────────────────────
# Group 1 — Built-in routes
# ──────────────────────────────────────────────────────────────────────


def group_builtin(client: httpx.Client) -> None:
    # Capability probe — also feeds the FILE_OPS / PROCESS gates below.
    try:
        resp = client.get("/capabilities")
        body = resp.json()
        groups = body.get("groups", {})
        if resp.status_code == 200 and isinstance(groups, dict):
            STATE["groups"] = groups
            enabled = [g for g, on in sorted(groups.items()) if on]
            record("PASS", "GET /capabilities",
                   f"HTTP {resp.status_code}, enabled: {', '.join(enabled)}")
        elif resp.status_code == 401:
            record("SKIP", "GET /capabilities",
                   "HTTP 401 (auth configured) — pass E2E_TOKEN to probe groups")
        else:
            record("FAIL", "GET /capabilities",
                   f"HTTP {resp.status_code}, {_short(body, 120)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /capabilities", f"exception: {exc}")

    # GET /commands — the registered command and its declared args.
    try:
        resp = client.get("/commands")
        body = resp.json()
        entries = body.get("commands", body if isinstance(body, list) else [])
        by_name = {c.get("name"): c for c in entries if isinstance(c, dict)}
        entry = by_name.get(CMD) or {}
        args = {a.get("name"): a.get("type") for a in entry.get("args", [])
                if isinstance(a, dict)}
        missing = [n for n in CMD_ARGS if n not in args]
        typed = [f"{n}:{args.get(n)}" for n, t in CMD_ARGS.items() if n in args and args[n] != t]
        ok = resp.status_code == 200 and entry != {} and not missing and not typed
        record("PASS" if ok else "FAIL", "GET /commands",
               f"HTTP {resp.status_code}, {len(by_name)} command(s), "
               f"{CMD} args={sorted(f'{n}:{t}' for n, t in args.items())}"
               + (f", missing={missing}" if missing else "")
               + (f", unexpected types={typed}" if typed else ""))
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /commands", f"exception: {exc}")

    # Unknown command must be rejected with 404.
    try:
        resp = client.post("/commands/__no_such_command__", json={})
        body = resp.json()
        ok = resp.status_code == 404 and body.get("type") == "ValueError"
        record("PASS" if ok else "FAIL", "POST /commands (unknown name)",
               f"HTTP {resp.status_code} (expected 404), type={body.get('type')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands (unknown name)", f"exception: {exc}")

    # Missing required argument must be rejected with 400.
    if REQUIRED_ARGS:
        try:
            resp = client.post(f"/commands/{CMD}", json={})
            body = resp.json()
            ok = resp.status_code == 400 and "Required argument" in str(body.get("error", ""))
            record("PASS" if ok else "FAIL", f"POST /commands/{CMD} (no args)",
                   f"HTTP {resp.status_code} (expected 400), error={_short(body.get('error'), 100)}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", f"POST /commands/{CMD} (no args)", f"exception: {exc}")
    else:
        record("SKIP", f"POST /commands/{CMD} (no args)",
               "command has no required args — validation case not applicable")


# ──────────────────────────────────────────────────────────────────────
# Group 2 — File ops (FILE_OPS)
# ──────────────────────────────────────────────────────────────────────


def group_files(client: httpx.Client) -> None:
    if not _group_on("file_ops"):
        for test in ("POST /files/upload-stream", "GET /files/stat", "GET /files/list",
                     "POST /files/search", "GET /files/download-stream", "DELETE /files"):
            record("SKIP", test, "FILE_OPS capability group is disabled")
        return

    payload = f"{TEMPLATE} e2e probe {os.getpid()}\n".encode()
    encoded = base64.b64encode(payload).decode()

    # 1. Upload
    seeded = False
    try:
        resp = client.post("/files/upload-stream",
                           json={"path": PROBE_FILE, "content_base64": encoded})
        body = resp.json()
        seeded = (resp.status_code == 200 and body.get("bytes") == len(payload)
                  and str(body.get("path", "")).endswith("probe.txt"))
        record("PASS" if seeded else "FAIL", "POST /files/upload-stream",
               f"HTTP {resp.status_code}, bytes={body.get('bytes')}, path={body.get('path')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /files/upload-stream", f"exception: {exc}")

    if not seeded:
        for test in ("GET /files/stat", "GET /files/list", "POST /files/search",
                     "GET /files/download-stream", "DELETE /files"):
            record("SKIP", test, "probe file was not uploaded")
        return

    # 2. Stat
    try:
        resp = client.get("/files/stat", params={"path": PROBE_FILE})
        body = resp.json()
        ok = (resp.status_code == 200 and body.get("exists") is True
              and body.get("type") == "file" and body.get("size") == len(payload))
        record("PASS" if ok else "FAIL", "GET /files/stat",
               f"HTTP {resp.status_code}, exists={body.get('exists')}, "
               f"type={body.get('type')}, size={body.get('size')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /files/stat", f"exception: {exc}")

    # 3. List
    try:
        resp = client.get("/files/list", params={"path": PROBE_DIR})
        body = resp.json()
        entries = body.get("entries", [])
        names = [e.get("name") for e in entries if isinstance(e, dict)]
        ok = resp.status_code == 200 and "probe.txt" in names
        record("PASS" if ok else "FAIL", "GET /files/list",
               f"HTTP {resp.status_code}, {len(names)} entr(ies), probe.txt present={'probe.txt' in names}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /files/list", f"exception: {exc}")

    # 4. Search
    try:
        resp = client.post("/files/search", json={"path": PROBE_DIR, "pattern": "*.txt"})
        body = resp.json()
        results = body.get("results", [])
        names = [r.get("name") for r in results if isinstance(r, dict)]
        ok = resp.status_code == 200 and "probe.txt" in names
        record("PASS" if ok else "FAIL", "POST /files/search",
               f"HTTP {resp.status_code}, {len(names)} match(es)")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /files/search", f"exception: {exc}")

    # 5. Download round-trip
    try:
        resp = client.get("/files/download-stream", params={"path": PROBE_FILE})
        body = resp.json()
        decoded = base64.b64decode(body.get("content_base64", ""))
        ok = resp.status_code == 200 and decoded == payload
        record("PASS" if ok else "FAIL", "GET /files/download-stream",
               f"HTTP {resp.status_code}, content matches={decoded == payload}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /files/download-stream", f"exception: {exc}")

    # 6. Delete + verify gone
    try:
        resp = client.delete("/files", params={"path": PROBE_FILE})
        body = resp.json()
        follow = client.get("/files/stat", params={"path": PROBE_FILE}).json()
        ok = (resp.status_code == 200 and body.get("deleted") is True
              and follow.get("exists") is False)
        record("PASS" if ok else "FAIL", "DELETE /files",
               f"HTTP {resp.status_code}, deleted={body.get('deleted')}, "
               f"re-stat exists={follow.get('exists')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "DELETE /files", f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Group 3 — Shell & process (PROCESS)
# ──────────────────────────────────────────────────────────────────────


def group_shell_process(client: httpx.Client) -> None:
    if not _group_on("process"):
        for test in ("POST /shell", "POST /shell/stream", "POST /process/start",
                     "GET /process/list", "GET /process/{pid}", "POST /process/{pid}/signal"):
            record("SKIP", test, "PROCESS capability group is disabled")
        return

    marker = f"ebx-e2e-{TEMPLATE}"

    # 1. Plain shell execution
    try:
        resp = client.post("/shell", json={"command": f"echo {marker}"})
        body = resp.json()
        ok = (resp.status_code == 200 and body.get("exit_code") == 0
              and marker in str(body.get("stdout", "")))
        record("PASS" if ok else "FAIL", "POST /shell",
               f"HTTP {resp.status_code}, exit={body.get('exit_code')}, "
               f"stdout={str(body.get('stdout', '')).strip()!r}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell", f"exception: {exc}")

    # 2. Streaming shell (SSE)
    try:
        status = 0
        events: list[dict[str, Any]] = []
        with client.stream("POST", "/shell/stream",
                           json={"command": f"echo {marker}", "timeout": 30}) as resp:
            status = resp.status_code
            if status == 200:
                events = _read_sse(resp, 30.0)
            else:
                events = []
                raw = resp.read().decode("utf-8", "replace")
        stdout_text = "\n".join(str((e.get("data") or {}).get("data", ""))
                                for e in events if e.get("event") == "stdout")
        exits = [(e.get("data") or {}).get("exit_code")
                 for e in events if e.get("event") == "exit"]
        ok = status == 200 and marker in stdout_text and bool(exits) and exits[-1] == 0
        detail = f"HTTP {status}, {len(events)} events, exit={exits[-1] if exits else None}"
        if status != 200:
            detail += f", body={_short(raw, 120)}"
        record("PASS" if ok else "FAIL", "POST /shell/stream", detail)
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell/stream", f"exception: {exc}")

    # 3. Background process lifecycle
    pid: int | None = None
    try:
        resp = client.post("/process/start", json={"command": "sleep 60"})
        body = resp.json()
        pid = body.get("pid") if isinstance(body.get("pid"), int) else None
        ok = resp.status_code == 200 and pid is not None
        record("PASS" if ok else "FAIL", "POST /process/start",
               f"HTTP {resp.status_code}, pid={pid}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /process/start", f"exception: {exc}")

    if pid is None:
        for test in ("GET /process/list", "GET /process/{pid}", "POST /process/{pid}/signal"):
            record("SKIP", test, "no background process was started")
        return

    # 4. List contains the new pid
    try:
        resp = client.get("/process/list")
        body = resp.json()
        pids = [p.get("pid") for p in body.get("processes", []) if isinstance(p, dict)]
        ok = resp.status_code == 200 and pid in pids
        record("PASS" if ok else "FAIL", "GET /process/list",
               f"HTTP {resp.status_code}, {len(pids)} process(es), pid present={pid in pids}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /process/list", f"exception: {exc}")

    # 5. Detail reports "running"
    try:
        resp = client.get(f"/process/{pid}")
        body = resp.json()
        ok = resp.status_code == 200 and body.get("state") == "running"
        record("PASS" if ok else "FAIL", "GET /process/{pid}",
               f"HTTP {resp.status_code}, state={body.get('state')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /process/{pid}", f"exception: {exc}")

    # 6. Signal (SIGTERM) then wait for exit
    try:
        resp = client.post(f"/process/{pid}/signal", json={"signal": 15})
        ok = resp.status_code == 200
        state, code = "", None
        if ok:
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                detail_body = client.get(f"/process/{pid}").json()
                state, code = detail_body.get("state"), detail_body.get("exit_code")
                if state == "exited":
                    break
                time.sleep(0.3)
        ok = ok and state == "exited"
        record("PASS" if ok else "FAIL", "POST /process/{pid}/signal",
               f"HTTP {resp.status_code}, final state={state}, exit_code={code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /process/{pid}/signal", f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Group 4 — Template command (Codex CLI, LLM-gated)
# ──────────────────────────────────────────────────────────────────────


def group_command(client: httpx.Client) -> None:
    test = f"POST /commands/{CMD}"

    if RUN_LLM in {"0", "false", "no"}:
        record("SKIP", test, f"E2E_RUN_LLM={RUN_LLM!r} — forced skip")
        return
    if RUN_LLM not in {"1", "true", "yes"} and not any(os.environ.get(k) for k in KEY_ENVS):
        record("SKIP", test,
               f"no {'/'.join(KEY_ENVS)} on the host; set one or E2E_RUN_LLM=1 "
               f"to force — the key must also be present inside the sandbox")
        return

    payload: dict[str, Any] = {"prompt": LLM_PROMPT}
    if MODEL:
        payload["model"] = MODEL
    try:
        resp = client.post(f"/commands/{CMD}", json=payload, timeout=LLM_TIMEOUT)
        body = resp.json()
        result = body.get("result")
        ok = resp.status_code == 200 and isinstance(result, str) and bool(result.strip())
        detail = f"HTTP {resp.status_code}, {len(result) if isinstance(result, str) else 0} chars"
        if not ok:
            detail += f", error={_short(body.get('error') or body, 140)}"
        record("PASS" if ok else "FAIL", test, detail)
    except Exception as exc:  # noqa: BLE001
        record("FAIL", test, f"exception: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Cleanup & summary
# ──────────────────────────────────────────────────────────────────────


def cleanup(client: httpx.Client) -> None:
    """Best-effort removal of the probe directory."""
    try:
        resp = client.delete("/files", params={"path": PROBE_DIR})
        print(f"[cleanup] DELETE {PROBE_DIR} -> HTTP {resp.status_code}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] DELETE {PROBE_DIR} failed: {exc}", flush=True)


def summary() -> int:
    """Print the aggregate report and return the process exit code."""
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    print("\n" + "=" * 74, flush=True)
    print(f"SUMMARY — {TEMPLATE}", flush=True)
    print("=" * 74, flush=True)
    print(f"{passed} passed, {failed} failed, {skipped} skipped (total {len(RESULTS)})",
          flush=True)
    if failed:
        print("\nFailed tests:", flush=True)
        for s, t, d in RESULTS:
            if s == "FAIL":
                print(f"  - {t}: {d}", flush=True)
    print("=" * 74, flush=True)
    return 1 if failed else 0


def main() -> int:
    print(f"{TEMPLATE} end-to-end suite", flush=True)
    print(f"  base_url : {BASE_URL}", flush=True)
    print(f"  base_dir : {BASE_DIR}", flush=True)
    print(f"  llm case : " + ("forced" if RUN_LLM in {"1", "true", "yes"} else "auto"),
          flush=True)
    print("-" * 74, flush=True)
    with _client() as client:
        if not preflight(client):
            print("server unreachable — aborting", flush=True)
            return 2
        print("\n-- Built-in routes --", flush=True)
        group_builtin(client)
        print("\n-- File ops (FILE_OPS) --", flush=True)
        group_files(client)
        print("\n-- Shell & process (PROCESS) --", flush=True)
        group_shell_process(client)
        print("\n-- Template command --", flush=True)
        group_command(client)
        print("\n-- Cleanup --", flush=True)
        cleanup(client)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
