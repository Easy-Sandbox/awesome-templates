#!/usr/bin/env python3
"""End-to-end test suite for the ``browser-automation`` template.

Exercises built-in routes (/health, /commands), the 8 built-in BROWSER
endpoints (navigate / screenshot / content / click / type / evaluate /
pdf / console), the high-level commands (browse, scrape, fill_form) and
FILE_OPS + PROCESS routes against a running server.

Browser-dependent checks are probed first via ``POST /browser/navigate``
to a ``data:`` URL; if the Playwright/Chromium runtime is unavailable the
browser groups degrade to ``[SKIP]`` instead of failing.

Usage::

    python3 e2e_test.py                                # http://localhost:9000
    E2E_BASE_URL=http://host:9000 python3 e2e_test.py
"""
from __future__ import annotations

import base64
import json
import os
import sys

import httpx

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:9000").rstrip("/")
WORKSPACE = os.environ.get("E2E_WORKSPACE", "")  # empty → auto-detect
TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)

# Standalone page — no external network required.
PROBE_HTML = (
    "data:text/html,<html><head><title>E2E</title></head><body>"
    "<h1 id='main'>hello-e2e</h1>"
    "<a href='http://example.com'>a-link</a>"
    "<form><input id='email' type='text'/></form>"
    "</body></html>"
)

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


def browser_available(client: httpx.Client) -> bool:
    """Probe whether the Playwright runtime can launch Chromium."""
    try:
        resp = client.post("/browser/navigate",
                           json={"url": PROBE_HTML, "wait_until": "load", "timeout": 20000})
        if resp.status_code == 200:
            return True
        print(f"[info] browser probe failed: HTTP {resp.status_code} "
              f"{_short(resp.text, 140)}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[info] browser probe exception: {exc}", flush=True)
    return False


def group_builtin(client: httpx.Client) -> None:
    try:
        resp = client.get("/commands")
        body = resp.json()
        entries = body.get("commands", body if isinstance(body, list) else [])
        names = {c.get("name") for c in entries}
        ok = resp.status_code == 200 and {"browse", "scrape", "fill_form"} <= names
        record("PASS" if ok else "FAIL", "GET /commands",
               f"HTTP {resp.status_code}, listed={sorted(n for n in names if n)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /commands", f"exception: {exc}")


def group_browser_endpoints(client: httpx.Client, available: bool) -> None:
    if not available:
        for ep in ("POST /browser/navigate", "POST /browser/screenshot",
                   "GET /browser/content", "POST /browser/evaluate",
                   "GET /browser/console"):
            record("SKIP", ep, "Playwright/Chromium runtime unavailable")
        return

    # navigate
    try:
        resp = client.post("/browser/navigate",
                           json={"url": PROBE_HTML, "wait_until": "load", "timeout": 20000})
        body = resp.json()
        ok = resp.status_code == 200 and body.get("title") == "E2E"
        record("PASS" if ok else "FAIL", "POST /browser/navigate",
               f"HTTP {resp.status_code}, title={body.get('title')!r}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/navigate", f"exception: {exc}")

    # evaluate
    try:
        resp = client.post("/browser/evaluate",
                           json={"script": "document.getElementById('main').innerText"})
        body = resp.json()
        ok = resp.status_code == 200 and "hello-e2e" in str(body.get("result"))
        record("PASS" if ok else "FAIL", "POST /browser/evaluate",
               f"HTTP {resp.status_code}, result={_short(body.get('result'), 60)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/evaluate", f"exception: {exc}")

    # content
    try:
        resp = client.get("/browser/content")
        body = resp.json()
        text = str(body.get("content") or body.get("html") or body)
        ok = resp.status_code == 200 and "hello-e2e" in text
        record("PASS" if ok else "FAIL", "GET /browser/content",
               f"HTTP {resp.status_code}, contains marker={ok}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /browser/content", f"exception: {exc}")

    # screenshot
    try:
        resp = client.post("/browser/screenshot", json={})
        body = resp.json()
        ok = resp.status_code == 200 and ("base64" in json.dumps(body).lower()
                                          or "path" in json.dumps(body))
        record("PASS" if ok else "FAIL", "POST /browser/screenshot",
               f"HTTP {resp.status_code}, {_short(body, 100)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/screenshot", f"exception: {exc}")

    # console (empty is fine)
    try:
        resp = client.get("/browser/console")
        ok = resp.status_code == 200
        record("PASS" if ok else "FAIL", "GET /browser/console",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "GET /browser/console", f"exception: {exc}")

    # click + type against the probe page (best-effort smoke).
    try:
        resp = client.post("/browser/click", json={"selector": "#main"})
        record("PASS" if resp.status_code == 200 else "FAIL", "POST /browser/click",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/click", f"exception: {exc}")
    try:
        resp = client.post("/browser/type",
                           json={"selector": "#email", "text": "e2e@test.dev"})
        record("PASS" if resp.status_code == 200 else "FAIL", "POST /browser/type",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/type", f"exception: {exc}")

    # pdf (Chromium print-to-PDF on the probe page)
    try:
        resp = client.post("/browser/pdf", json={})
        ok = resp.status_code == 200
        record("PASS" if ok else "FAIL", "POST /browser/pdf",
               f"HTTP {resp.status_code}, {_short(resp.json(), 80)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /browser/pdf", f"exception: {exc}")


def group_commands(client: httpx.Client, available: bool) -> None:
    if not available:
        for ep in ("POST /commands/browse", "POST /commands/scrape",
                   "POST /commands/fill_form"):
            record("SKIP", ep, "Playwright/Chromium runtime unavailable")
        return

    try:
        resp = client.post("/commands/browse",
                           json={"url": PROBE_HTML, "action": "extract"})
        body = resp.json()
        result = body.get("result") or {}
        ok = resp.status_code == 200 and "hello-e2e" in str(result.get("text"))
        record("PASS" if ok else "FAIL", "POST /commands/browse (extract)",
               f"HTTP {resp.status_code}, title={result.get('title')!r}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/browse (extract)", f"exception: {exc}")

    try:
        resp = client.post("/commands/browse",
                           json={"url": PROBE_HTML, "action": "links"})
        body = resp.json()
        result = body.get("result") or {}
        ok = resp.status_code == 200 and result.get("count", 0) >= 1
        record("PASS" if ok else "FAIL", "POST /commands/browse (links)",
               f"HTTP {resp.status_code}, {result.get('count')} link(s)")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/browse (links)", f"exception: {exc}")

    try:
        resp = client.post("/commands/scrape",
                           json={"url": PROBE_HTML, "selector": "h1"})
        body = resp.json()
        result = body.get("result") or {}
        texts = result.get("texts") or []
        ok = resp.status_code == 200 and result.get("count") == 1 \
            and "hello-e2e" in texts[0]
        record("PASS" if ok else "FAIL", "POST /commands/scrape",
               f"HTTP {resp.status_code}, texts={_short(texts, 80)}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/scrape", f"exception: {exc}")

    try:
        resp = client.post("/commands/fill_form", json={
            "url": PROBE_HTML,
            "fields_json": '[{"selector": "#email", "value": "e2e@test.dev"}]',
        })
        body = resp.json()
        result = body.get("result") or {}
        ok = resp.status_code == 200 and result.get("fields_filled") == 1
        record("PASS" if ok else "FAIL", "POST /commands/fill_form",
               f"HTTP {resp.status_code}, filled={result.get('fields_filled')}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /commands/fill_form", f"exception: {exc}")


def group_files_shell(client: httpx.Client) -> None:
    if not WORKSPACE:
        record("SKIP", "files upload/download round-trip",
               "no writable workspace detected — set E2E_WORKSPACE")
    else:
        path = f"{WORKSPACE}/e2e_browser_automation.txt"
        encoded = base64.b64encode(b"browser-automation e2e\n").decode()
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
        resp = client.post("/shell", json={"command": "echo hello"})
        ok = resp.status_code == 200 and "hello" in str(resp.json().get("stdout", ""))
        record("PASS" if ok else "FAIL", "POST /shell echo",
               f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "POST /shell echo", f"exception: {exc}")


def summary() -> int:
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    print("\n" + "=" * 74, flush=True)
    print("SUMMARY — browser-automation", flush=True)
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
    print("browser-automation end-to-end suite", flush=True)
    print(f"  base_url : {BASE_URL}", flush=True)
    print("-" * 74, flush=True)
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        if not preflight(client):
            print("server unreachable — aborting", flush=True)
            return 2
        print("\n-- Built-in routes --", flush=True)
        group_builtin(client)
        available = browser_available(client)
        print(f"\n-- Built-in BROWSER endpoints (runtime available={available}) --",
              flush=True)
        group_browser_endpoints(client, available)
        print("\n-- High-level commands --", flush=True)
        group_commands(client, available)
        print("\n-- File ops & shell --", flush=True)
        global WORKSPACE
        WORKSPACE = detect_workspace(client)
        group_files_shell(client)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
