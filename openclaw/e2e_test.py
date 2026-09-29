#!/usr/bin/env python3
"""End-to-end test suite for the ``openclaw`` template.

Exercises built-in routes (/health, /commands), the custom ``gateway``
command, FILE_OPS round-trip and PROCESS shell execution against a
running server.

The ``gateway`` command manages the OpenClaw gateway binary, which
requires ``OPENCLAW_GATEWAY_TOKEN`` in the sandbox environment. Without
the token the gateway tests are marked ``[SKIP]`` instead of failing.

Usage::

    python3 e2e_test.py                                # http://localhost:9000
    E2E_BASE_URL=http://host:9000 python3 e2e_test.py
    OPENCLAW_GATEWAY_TOKEN=... python3 e2e_test.py     # enable gateway tests
"""
from __future__ import annotations

import base64
import json
import os
import sys

import httpx

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:9000").rstrip("/")
WORKSPACE = os.environ.get("E2E_WORKSPACE", "")  # empty → auto-detect
HAS_GATEWAY_TOKEN = bool(os.environ.get("OPENCLAW_GATEWAY_TOKEN"))
TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)

RESULTS: list[tuple[str, str, str]] = []


def record(status: str, test: str, detail: str = "") -> None:
    RESULTS.append((status, test, detail))
    line = f"[{status}] {test}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)


def _short(value: object, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def detect_workspace(client: httpx.Client) -> str:
    """Find a writable directory accepted by the server's path guard."""
    candidates = ([WORKSPACE] if WORKSPACE else []) + ["/home/user", "/workspace"]
    for candidate in candidates:
        probe = f"{candidate}/.e2e_probe"
        try:
            resp = client.post("/files/upload-stream", json={
                "path": probe,
                "content_base64": base64.b64encode(b"probe").decode(),
            })
            if resp.status_code == 200:
                client.delete("/files", params={"path": probe})
                return candidate
        except Exception:  # noqa: BLE001
            continue
    return ""


def preflight(client: httpx.Client) -> bool:
    try:
        resp = client.get("/health")
        ok = resp.status_code == 200 and resp.json().get("status") == "ok"
        print(f"[{'PASS' if ok else 'FAIL'}] preflight GET /health — HTTP {resp.status_code}",
              flush=True)
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] preflight GET /health — {exc}", flush=True)
        return False


def group_builtin(client: httpx.Client) -> None:
    try:
        resp = client.get("/commands")
        body = resp.json()
        entries = body.get("commands", body if isinstance(body, list) else [])
        names = {c.get("name") for c in entries}
        ok = resp.status_code == 200 and "gateway" in names
        record("PASS" if ok else "FAIL", "GET /commands",
               f"HTTP {resp.status_code}, listed={sorted(n for n in names if n)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /commands", f"exception: {exc}")


def group_commands(client: httpx.Client) -> None:
    # Missing-argument robustness: unknown action must surface a clean error
    # rather than hanging (subprocess timeout is 60s server-side).
    try:
        resp = client.post("/commands/gateway", json={"action": "__e2e_no_such_action__"})
        body = resp.json()
        # Either the CLI rejects the action (500 with error) or handles it —
        # both are acceptable as long as the server answers in time.
        ok = resp.status_code in (200, 500) and (
            resp.status_code == 200 or "error" in body
        )
        record("PASS" if ok else "FAIL", "POST /commands/gateway (invalid action)",
               f"HTTP {resp.status_code}, {_short(body, 120)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/gateway (invalid action)", f"exception: {exc}")

    # Real gateway management requires OPENCLAW_GATEWAY_TOKEN.
    ep = "POST /commands/gateway (start)"
    if not HAS_GATEWAY_TOKEN:
        record("SKIP", ep,
               "OPENCLAW_GATEWAY_TOKEN not set — gateway start not exercised")
    else:
        try:
            resp = client.post("/commands/gateway", json={"action": "start"})
            body = resp.json()
            ok = resp.status_code == 200
            record("PASS" if ok else "FAIL", ep,
                   f"HTTP {resp.status_code}, {_short(body.get('result', body), 140)}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", ep, f"exception: {exc}")


def group_files(client: httpx.Client) -> None:
    if not WORKSPACE:
        record("SKIP", "files upload/download round-trip",
               "no writable workspace detected — set E2E_WORKSPACE")
        return
    path = f"{WORKSPACE}/e2e_openclaw.txt"
    encoded = base64.b64encode(b"openclaw e2e file round-trip\n").decode()
    try:
        up = client.post("/files/upload-stream",
                         json={"path": path, "content_base64": encoded})
        down = client.get("/files/download-stream", params={"path": path})
        ok = up.status_code == 200 and down.status_code == 200 \
            and down.json().get("content_base64") == encoded
        record("PASS" if ok else "FAIL", "files upload/download round-trip",
               f"upload HTTP {up.status_code}, download HTTP {down.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "files upload/download round-trip", f"exception: {exc}")
    try:
        resp = client.get("/files/list", params={"path": WORKSPACE})
        ok = resp.status_code == 200
        record("PASS" if ok else "FAIL", "GET /files/list", f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /files/list", f"exception: {exc}")


def group_shell(client: httpx.Client) -> None:
    try:
        resp = client.post("/shell", json={"command": "which openclaw"})
        body = resp.json()
        stdout = str(body.get("stdout", "")).strip()
        # The binary may legitimately be absent in a minimal sandbox — report
        # presence as PASS and absence as SKIP so the suite stays actionable.
        if resp.status_code == 200 and stdout:
            record("PASS", "POST /shell which openclaw", f"found: {stdout}")
        elif resp.status_code == 200:
            record("SKIP", "POST /shell which openclaw",
                   "openclaw binary not on PATH in this environment")
        else:
            record("FAIL", "POST /shell which openclaw",
                   f"HTTP {resp.status_code}, {_short(body, 120)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell which openclaw", f"exception: {exc}")
    try:
        resp = client.post("/shell", json={"command": "echo hello"})
        ok = resp.status_code == 200 and "hello" in str(resp.json().get("stdout", ""))
        record("PASS" if ok else "FAIL", "POST /shell echo", f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell echo", f"exception: {exc}")


def summary() -> int:
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    print("\n" + "=" * 74, flush=True)
    print("SUMMARY — openclaw", flush=True)
    print("=" * 74, flush=True)
    print(f"{passed} passed, {failed} failed, {skipped} skipped "
          f"(total {len(RESULTS)})", flush=True)
    if failed:
        print("\nFailed tests:", flush=True)
        for s, t, d in RESULTS:
            if s == "FAIL":
                print(f"  - {t}: {d}", flush=True)
    print("=" * 74, flush=True)
    return 1 if failed else 0


def main() -> int:
    print("openclaw end-to-end suite", flush=True)
    print(f"  base_url         : {BASE_URL}", flush=True)
    print(f"  gateway token    : {'set' if HAS_GATEWAY_TOKEN else 'not set'}", flush=True)
    print("-" * 74, flush=True)
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        if not preflight(client):
            print("server unreachable — aborting", flush=True)
            return 2
        print("\n-- Built-in routes --", flush=True)
        group_builtin(client)
        print("\n-- Custom commands (gateway) --", flush=True)
        group_commands(client)
        print("\n-- File ops --", flush=True)
        global WORKSPACE
        WORKSPACE = detect_workspace(client)
        group_files(client)
        print("\n-- Shell --", flush=True)
        group_shell(client)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
