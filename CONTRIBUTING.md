# Contributing to Awesome Templates for Easy Sandbox

Thanks for helping grow the [Easy Sandbox](https://pypi.org/project/easy-sandbox/)
template ecosystem! This guide explains how a template is structured, how the
runtime capability model works, how to develop and test locally with the `ebx`
CLI, and the exact steps to land your contribution.

- [Template Anatomy](#template-anatomy)
- [Capability Groups](#capability-groups)
- [Local Development & Testing](#local-development--testing)
- [Contribution Workflow](#contribution-workflow)
- [Naming & Quality Standards](#naming--quality-standards)

---

## Template Anatomy

Every template is a **top-level directory** in this repository containing
exactly four files:

```
<template-name>/
├── template.yaml    # Metadata, capabilities, custom commands
├── Dockerfile       # Container image definition (optional if template.yaml describes the image)
├── commands.py      # SandboxServer route table + command registry
└── README.md        # What it is, required env vars, usage
```

### `template.yaml`

The canonical descriptor. Recognised fields:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique template identifier (matches the directory name). |
| `version` | ✅ | Semantic version string, e.g. `"1.0.0"`. |
| `description` | ✅ | One-line summary. |
| `author` | ✅ | GitHub handle or org (e.g. `Easy-Sandbox`). |
| `tags` | ✅ | List of search tags. |
| `base` | ✅ | Base image, e.g. `ubuntu:22.04`. |
| `system_packages` | | OS packages installed at build time. |
| `capabilities` | ✅ | Sandbox capabilities: `shell`, `files`, `code`, `terminal`, `ports`. |
| `ports` | | Ports the sandbox exposes. |
| `custom_commands` | | Named CLI commands with `cmd`, `description`, `cwd`, `timeout`, `args`. |
| `env` | | Default environment variables. |

Minimal example:

```yaml
name: my-template
version: "1.0.0"
description: "Short description of what this template does"
author: Easy-Sandbox
tags: [python, example]

base: ubuntu:22.04
system_packages: [python3, python3-pip]

capabilities: [shell, files, code, ports]
ports: [9000]

env:
  LANG: C.UTF-8
```

> `terminal` and `ports` must be declared **explicitly** — they are never
> granted implicitly.

### `Dockerfile`

Standard Dockerfile that produces the runtime image. Keep it minimal and
reproducible; pin versions where practical. `ebx` can also synthesize a
Dockerfile from `template.yaml`, but shipping an explicit one gives you full
control over the build.

### `commands.py` — RouteTable + CommandRegistry

This is where a template extends the sandbox HTTP server. Two building blocks:

- **`RouteTable`** — toggles capability groups and registers custom HTTP routes
  via the `@table.route(...)` decorator.
- **`CommandRegistry`** — registers named, callable commands exposed through the
  server's command API via `@registry.command(...)`.

```python
from easy_sandbox.server import (
    CapabilityGroup,
    CommandRegistry,
    SandboxServer,
    ServerResponse,
    default_table,
)

# 1. Route table — enable the capability groups this template needs
table = default_table()
table.enable_group(CapabilityGroup.FILE_OPS)   # upload/download + file ops
table.enable_group(CapabilityGroup.PROCESS)    # shell + process management
table.enable_group(CapabilityGroup.SYSTEM)     # system info + port detection

# 2. Command registry — custom commands
registry = CommandRegistry()


@registry.command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"


@registry.command(hidden=True)               # not listed in GET /commands
def _debug_info() -> dict:
    import platform
    return {"python": platform.python_version()}


# 3. Custom HTTP route via the RouteTable decorator
@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request: object) -> ServerResponse:
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})


# 4. Freeze the registry and serve
registry.freeze()
server = SandboxServer(registry=registry)
server.serve(port=9000)
```

### `README.md`

Document what the template is, which environment variables / API keys it needs,
and a copy-pasteable usage snippet. Keep the install command in the
`Easy-Sandbox/awesome-templates//<name>` form.

---

## Capability Groups

The sandbox server organises endpoints into **capability groups**. Enabling a
group activates its family of routes.

| Group | Default state | Purpose |
|-------|---------------|---------|
| `CORE` | **Always on** (cannot be disabled) | Health/status essentials. |
| `COMMANDS` | Enabled | List & run registered commands. |
| `FILE_OPS` | Enabled | Upload/download & file operations. |
| `PROCESS` | Enabled | Shell execution & process management. |
| `TERMINAL` | Enabled | Interactive PTY / terminal WebSocket. |
| `SYSTEM` | Enabled | System info & port detection. |
| `DEV_TOOLS` | **Disabled** | Developer tooling — must be enabled explicitly. |
| `BROWSER` | **Disabled** | Browser/DevTools automation — must be enabled explicitly. |

Rules of thumb:

- `CORE` is always active; calling `enable_group(CapabilityGroup.CORE)` is a
  no-op and `disable_group(CapabilityGroup.CORE)` raises.
- `DEV_TOOLS` and `BROWSER` are **off by default**. If your template needs them,
  enable them explicitly:

  ```python
  table.enable_group(CapabilityGroup.BROWSER)
  ```

- Only enable the groups you actually use — a smaller surface is safer and
  faster to start.

---

## Local Development & Testing

Install `ebx` and validate your template against a **local registry** before
opening a PR — no GitHub Release required:

```bash
# Install directly from a local directory
ebx template install ./my-template --registry-type local

# Inspect what got cached (~/.ebx/templates/)
ebx template cache

# Confirm your template shows up in the index search
ebx template search my-template
```

What to verify:

1. **Files present** — `template.yaml`, `Dockerfile`, `commands.py`, `README.md`.
2. **`commands.py` imports cleanly** — no syntax errors; only enable capability
   groups you use.
3. **Commands & routes resolve** — every `@registry.command` and `@table.route`
   is reachable and returns sensible output.
4. **Capabilities match reality** — the `capabilities` list in `template.yaml`
   reflects the groups your `commands.py` enables.

> The final `install` step submits a build to the platform (`POST /templates`).
> Without platform credentials it will fail at that submission stage — that is
> expected. Reaching fetch → parse → build-submission proves the template is
> structurally valid.

---

## Contribution Workflow

1. **Fork** this repository.
2. **Create** a new top-level directory named exactly after your template
   (kebab-case, e.g. `my-agent`).
3. **Add the four files** — `template.yaml`, `Dockerfile`, `commands.py`,
   `README.md`.
4. **Register** your template in [`awesome-templates.yaml`](./awesome-templates.yaml):

   ```yaml
   - name: my-agent
     description: "Brief description of what your template does"
     repo: https://github.com/Easy-Sandbox/awesome-templates
     path: my-agent
     tags: [ai-agent, your-tag]
     author: your-github-handle
     capabilities: [shell, files, code]
     status: community
   ```

5. **Validate locally** with
   `ebx template install ./my-agent --registry-type local`.
6. **Open a PR** and complete the checklist in the pull request template.

---

## Naming & Quality Standards

- **Brand:** Easy Sandbox. **CLI:** `ebx`. **PyPI:** `easy-sandbox`.
  **Python import:** `easy_sandbox`. **GitHub org:** `Easy-Sandbox`.
  Never reference legacy names in new contributions.
- **Directory name == `template.yaml` `name` == index `path`.** All three must
  match.
- **No secrets.** Never commit API keys, tokens, or passwords. Use placeholders
  like `REPLACE_ME` and document required env vars in the README.
- **No build junk.** `__pycache__/`, `*.pyc`, and `.DS_Store` are excluded by
  `.gitignore` — keep it that way.
- **Minimal & reproducible images.** Pin versions where practical; install only
  what the template needs.
- **Conventional Commits** for commit messages (`feat:`, `fix:`, `docs:`, …).

Thanks for contributing! 🎉
