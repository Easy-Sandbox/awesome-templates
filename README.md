# Awesome Templates for Easy Sandbox

A curated collection of production-ready sandbox templates for the
[Easy Sandbox](https://pypi.org/project/easy-sandbox/) SDK & CLI (`ebx`).
Each template is a self-contained sandbox definition covering popular AI
coding agents, runtimes, and automation stacks.

> **New here?** See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full template
> anatomy, capability-group rules, local dev workflow, and PR process.

## Available Templates

| Template | Description | Capabilities | Install |
|----------|-------------|--------------|---------|
| [python-hello](./python-hello/) | Minimal Python hello-world template for testing | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//python-hello` |
| [browser-automation](./browser-automation/) | Playwright + Chromium for web scraping & UI testing | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//browser-automation` |
| [claude-code](./claude-code/) | Anthropic Claude-powered AI coding assistant | shell, files, code, terminal, ports | `ebx template install Easy-Sandbox/awesome-templates//claude-code` |
| [codex](./codex/) | OpenAI Codex CLI agent for code generation | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//codex` |
| [qoder](./qoder/) | Qoder AI coding assistant with Python + Node.js | shell, files, code, terminal, ports | `ebx template install Easy-Sandbox/awesome-templates//qoder` |
| [qwen-code](./qwen-code/) | Qwen Code — Dashscope-powered deployment agent | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//qwen-code` |
| [deepseek-harness](./deepseek-harness/) | DeepSeek model-driven AI coding agent | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//deepseek-harness` |
| [hermes-agent](./hermes-agent/) | NousResearch Hermes agent with tool calling | shell, files, code, ports | `ebx template install Easy-Sandbox/awesome-templates//hermes-agent` |
| [node-web](./node-web/) | Node.js web runtime for Express / Fastify | shell, files, ports | `ebx template install Easy-Sandbox/awesome-templates//node-web` |
| [openclaw](./openclaw/) | OpenClaw open-source AI coding agent gateway | shell, files, ports | `ebx template install Easy-Sandbox/awesome-templates//openclaw` |

## Usage

Templates are fetched from this repository's GitHub **Releases** (zipball), so
make sure a Release exists (e.g. `v1.0.0`) before installing.

```bash
# Install a template (downloads from the latest Release)
ebx template install Easy-Sandbox/awesome-templates//python-hello

# Pin to a specific release tag
ebx template install Easy-Sandbox/awesome-templates//codex@v1.0.0

# Inspect the local cache (~/.ebx/templates/)
ebx template cache

# Search this index by name, tag, or description
ebx template search python
ebx template search ai-agent --status official
```

## Template Structure

Each template directory contains four files:

```
<template-name>/
├── template.yaml    # Template metadata, capabilities, custom commands
├── Dockerfile       # Container image definition
├── commands.py      # SandboxServer command registry / custom routes
└── README.md        # Template-specific documentation
```

See [CONTRIBUTING.md](./CONTRIBUTING.md#template-anatomy) for a field-by-field
breakdown.

## Environment Variables

Most AI agents require API keys. Set them when creating a sandbox:

| Agent | Required Variable |
|-------|-------------------|
| codex | `OPENAI_API_KEY` |
| claude-code | `ANTHROPIC_API_KEY` |
| qwen-code | `DASHSCOPE_API_KEY` |
| deepseek-harness | `DEEPSEEK_API_KEY` |
| Others | Varies by model provider |

## Contributing

We welcome community templates! The short version:

1. Fork this repository.
2. Create a new top-level directory named after your template.
3. Add `template.yaml`, `Dockerfile`, `commands.py`, and `README.md`.
4. Register your template in [`awesome-templates.yaml`](./awesome-templates.yaml).
5. Validate locally with `ebx template install ./<your-template> --registry-type local`.
6. Open a Pull Request.

Full guidelines, capability-group rules, and quality standards live in
[CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT
