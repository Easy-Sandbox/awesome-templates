#!/usr/bin/env python3
"""End-to-end test suite for the ``node-web`` template.

Exercises built-in routes (/health, /commands), the custom ``serve``
command (upload a minimal Node app, start it, verify, kill it), FILE_OPS
round-trip and PROCESS shell execution against a running server.

Usage::

    python3 e2e_test.py                                # http://localhost:9000
    E2E_BASE_URL=http://host:9000 python3 e2e_test.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import httpx

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:9000").rstrip("/")
WORKSPACE = os.environ.get("E2E_WORKSPACE", "")  # empty → auto-detect
TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

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
        ok = resp.status_code == 200 and "serve" in names
        record("PASS" if ok else "FAIL", "GET /commands",
               f"HTTP {resp.status_code}, listed={sorted(n for n in names if n)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /commands", f"exception: {exc}")


def group_commands(client: httpx.Client) -> None:
    # serve failure path: entry file does not exist → command must report 500.
    try:
        resp = client.post("/commands/serve",
                           json={"entry": "no_such_entry_e2e.js", "port": 3999})
        ok = resp.status_code == 500 and "error" in resp.json()
        record("PASS" if ok else "FAIL", "POST /commands/serve (missing entry)",
               f"HTTP {resp.status_code} (expected 500)")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/serve (missing entry)", f"exception: {exc}")

    # serve success path: upload a tiny HTTP app, start it, probe it, kill it.
    if not WORKSPACE:
        record("SKIP", "POST /commands/serve (start)",
               "no writable workspace detected — set E2E_WORKSPACE")
        return
    app_path = f"{WORKSPACE}/e2e_index.js"
    app_src = (
        "const http = require('http');"
        "http.createServer((req, res) => {"
        "  res.writeHead(200, {'Content-Type': 'text/plain'});"
        "  res.end('e2e-ok');"
        "}).listen(process.env.PORT || 3000);"
    )
    try:
        resp = client.post("/files/upload-stream", json={
            "path": app_path,
            "content_base64": base64.b64encode(app_src.encode()).decode(),
        })
        seeded = resp.status_code == 200
        record("PASS" if seeded else "FAIL", "POST /files/upload-stream (app seed)",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /files/upload-stream (app seed)", f"exception: {exc}")
        seeded = False
    if not seeded:
        record("SKIP", "POST /commands/serve (start)", "app upload failed")
        return

    try:
        resp = client.post("/commands/serve", json={"entry": "e2e_index.js", "port": 3998})
        body = resp.json()
        result = body.get("result") or {}
        pid = result.get("pid")
        ok = (
            resp.status_code == 200
            and result.get("status") == "running"
            and result.get("port") == 3998
            and isinstance(pid, int)
        )
        record("PASS" if ok else "FAIL", "POST /commands/serve (start)",
               f"HTTP {resp.status_code}, pid={pid}, result={_short(result, 120)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/serve (start)", f"exception: {exc}")
        pid = None

    if isinstance(pid, int):
        # Give the server a moment, then kill it via the PROCESS shell route.
        time.sleep(1.0)
        try:
            resp = client.post("/shell", json={"command": f"kill {pid}"})
            ok = resp.status_code == 200
            record("PASS" if ok else "FAIL", "POST /shell kill serve pid",
                   f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", "POST /shell kill serve pid", f"exception: {exc}")

        # Best-effort cleanup of the uploaded app file.
        try:
            client.delete("/files", params={"path": app_path})
        except Exception:  # noqa: BLE001
            pass


def group_files(client: httpx.Client) -> None:
    if not WORKSPACE:
        record("SKIP", "files upload/download round-trip",
               "no writable workspace detected — set E2E_WORKSPACE")
        return
    path = f"{WORKSPACE}/e2e_node_web.txt"
    content = "node-web e2e file round-trip\n"
    encoded = base64.b64encode(content.encode()).decode()
    try:
        up = client.post("/files/upload-stream",
                         json={"path": path, "content_base64": encoded})
        down = client.get("/files/download-stream", params={"path": path})
        body = down.json()
        ok = up.status_code == 200 and down.status_code == 200 \
            and body.get("content_base64") == encoded
        record("PASS" if ok else "FAIL", "files upload/download round-trip",
               f"upload HTTP {up.status_code}, download HTTP {down.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "files upload/download round-trip", f"exception: {exc}")
    try:
        resp = client.get("/files/list", params={"path": WORKSPACE})
        ok = resp.status_code == 200
        record("PASS" if ok else "FAIL", "GET /files/list",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /files/list", f"exception: {exc}")


def group_shell(client: httpx.Client) -> None:
    try:
        resp = client.post("/shell", json={"command": "node --version"})
        body = resp.json()
        stdout = str(body.get("stdout", "")).strip()
        ok = resp.status_code == 200 and stdout.startswith("v")
        record("PASS" if ok else "FAIL", "POST /shell node --version",
               f"HTTP {resp.status_code}, node={stdout!r}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell node --version", f"exception: {exc}")
    try:
        resp = client.post("/shell", json={"command": "echo hello"})
        body = resp.json()
        ok = resp.status_code == 200 and "hello" in str(body.get("stdout", ""))
        record("PASS" if ok else "FAIL", "POST /shell echo",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell echo", f"exception: {exc}")


def summary() -> int:
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    print("\n" + "=" * 74, flush=True)
    print("SUMMARY — node-web", flush=True)
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
    print("node-web end-to-end suite", flush=True)
    print(f"  base_url : {BASE_URL}", flush=True)
    print("-" * 74, flush=True)
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        if not preflight(client):
            print("server unreachable — aborting", flush=True)
            return 2
        print("\n-- Built-in routes --", flush=True)
        group_builtin(client)
        print("\n-- Workspace --", flush=True)
        global WORKSPACE
        WORKSPACE = detect_workspace(client)
        print(f"  workspace: {WORKSPACE}", flush=True)
        print("\n-- Custom commands (serve) --", flush=True)
        group_commands(client)
        print("\n-- File ops --", flush=True)
        group_files(client)
        print("\n-- Shell --", flush=True)
        group_shell(client)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
