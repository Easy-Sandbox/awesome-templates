# Awesome Templates for Serverless Sandbox

A curated collection of production-ready sandbox templates for the
[Serverless Sandbox](https://pypi.org/project/serverless-sandbox/) SDK & CLI
(`sbox`). Each template is a self-contained sandbox definition covering popular
AI coding agents, runtimes, and automation stacks.

## Available Templates

| Template | Description | Capabilities | Install |
|----------|-------------|--------------|---------|
| [python-hello](./python-hello/) | Minimal Python hello-world template for testing | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//python-hello` |
| [browser-automation](./browser-automation/) | Playwright + Chromium for web scraping & UI testing | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//browser-automation` |
| [claude-code](./claude-code/) | Anthropic Claude-powered AI coding assistant | shell, files, code, terminal, ports | `sbox template install Easy-Sandbox/awesome-templates//claude-code` |
| [codex](./codex/) | OpenAI Codex CLI agent for code generation | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//codex` |
| [qoder](./qoder/) | Qoder AI coding assistant with Python + Node.js | shell, files, code, terminal, ports | `sbox template install Easy-Sandbox/awesome-templates//qoder` |
| [qwen-code](./qwen-code/) | Qwen Code — Dashscope-powered deployment agent | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//qwen-code` |
| [deepseek-harness](./deepseek-harness/) | DeepSeek model-driven AI coding agent | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//deepseek-harness` |
| [hermes-agent](./hermes-agent/) | NousResearch Hermes agent with tool calling | shell, files, code, ports | `sbox template install Easy-Sandbox/awesome-templates//hermes-agent` |
| [node-web](./node-web/) | Node.js web runtime for Express / Fastify | shell, files, ports | `sbox template install Easy-Sandbox/awesome-templates//node-web` |
| [openclaw](./openclaw/) | OpenClaw open-source AI coding agent gateway | shell, files, ports | `sbox template install Easy-Sandbox/awesome-templates//openclaw` |

## Usage

Templates are fetched from this repository's GitHub **Releases** (zipball), so
make sure a Release exists (e.g. `v1.0.0`) before installing.

```bash
# Install a template (downloads from the latest Release)
sbox template install Easy-Sandbox/awesome-templates//python-hello

# Pin to a specific release tag
sbox template install Easy-Sandbox/awesome-templates//codex@v1.0.0

# Inspect the local cache (~/.sbox/templates/)
sbox template cache

# Search this index by name, tag, or description
sbox template search python
sbox template search ai-agent --status official
```

## Template Structure

Each template directory contains:

```
<template-name>/
├── template.yaml    # Template metadata, capabilities, custom commands
├── Dockerfile       # Container image definition
├── commands.py      # SandboxServer command registry / custom routes
└── README.md        # Template-specific documentation
```

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

1. Create a new top-level directory named after your template.
2. Add `template.yaml`, `Dockerfile`, `commands.py`, and `README.md`.
3. Register your template in [`awesome-templates.yaml`](./awesome-templates.yaml).
4. Open a Pull Request.

## License

MIT
