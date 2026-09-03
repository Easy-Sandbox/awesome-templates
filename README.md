# Awesome Templates for Serverless Sandbox

Pre-built sandbox templates for popular AI coding agents and assistants.

## Available Templates

| Template | Description | Runtime | Install |
|----------|-------------|---------|---------|
| [codex](./codex/) | OpenAI Codex coding agent | Node.js 22 | `sbox install Serverless-Sandbox/awesome-templates//codex` |
| [claude-code](./claude-code/) | Anthropic Claude Code agent | Native binary | `sbox install Serverless-Sandbox/awesome-templates//claude-code` |
| [openclaw](./openclaw/) | OpenClaw AI assistant | Node.js 22 | `sbox install Serverless-Sandbox/awesome-templates//openclaw` |
| [hermes-agent](./hermes-agent/) | Nous Research Hermes Agent | Python 3.11 + Node.js | `sbox install Serverless-Sandbox/awesome-templates//hermes-agent` |

## Usage

```bash
# Install a template
sbox install Serverless-Sandbox/awesome-templates//codex

# Create a sandbox using the installed template
sbox create codex

# Create with environment variables
sbox create codex --env OPENAI_API_KEY=sk-...
```

## Template Structure

Each template directory contains:

```
<template-name>/
├── sandbox-template.yaml   # Template metadata and configuration
├── Dockerfile              # Container image definition
└── README.md               # Template-specific documentation
```

## Environment Variables

Most AI agents require API keys. Set them when creating a sandbox:

| Agent | Required Variable | Where to Get |
|-------|-------------------|--------------|
| Codex | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| Claude Code | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| OpenClaw | Varies by provider | Depends on model provider |
| Hermes Agent | Varies by provider | Depends on model provider |

## Contributing

1. Create a new directory with your template name
2. Add `sandbox-template.yaml` and `Dockerfile`
3. Add a `README.md` describing the template, its requirements, and usage
4. Submit a Pull Request

### Template YAML Format

```yaml
name: my-template
version: "1.0.0"
description: "Short description of the template"
author: "Your Name"
tags:
  - ai-agent
  - coding

base: ubuntu:22.04

system_packages:
  - git
  - curl

env:
  LANG: C.UTF-8
```

## License

MIT
