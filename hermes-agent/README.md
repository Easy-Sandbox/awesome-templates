# Hermes Agent - Nous Research AI Agent

Sandbox template for [Hermes Agent](https://github.com/NousResearch/hermes-agent), the self-improving AI agent built by Nous Research with a built-in learning loop.

## What's Included

- **Ubuntu 22.04** base image
- **Python 3.11** (required by Hermes Agent)
- **Node.js 22** (used by Hermes for some tools)
- **uv** - fast Python package manager used by Hermes
- **Hermes Agent** installed via the official installer
- **ripgrep** for fast code search
- **ffmpeg** for audio/video processing (voice features)
- Common development tools: git, curl, wget, build-essential

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Depends on provider | API key for OpenRouter (300+ models) |
| `OPENAI_API_KEY` | Depends on provider | API key for OpenAI models |
| `ANTHROPIC_API_KEY` | Depends on provider | API key for Anthropic models |

Hermes Agent supports multiple model providers. You can also use Nous Portal for a unified experience: `hermes setup --portal`.

## Usage

```bash
# Install the template
sbox install Serverless-Sandbox/awesome-templates//hermes-agent

# Create a sandbox with your API key
sbox create hermes-agent --env OPENROUTER_API_KEY=sk-or-...

# Or set the key in your environment first
export OPENROUTER_API_KEY=sk-or-...
sbox create hermes-agent
```

## Runtime Requirements

- **Python**: 3.11 (pre-installed in the image)
- **Node.js**: 22 (pre-installed in the image)
- **RAM**: 4 GB+ recommended
- **Network**: Internet access required for model API calls

## Features

- Built-in learning loop: creates skills from experience and improves them during use
- Multi-platform: Telegram, Discord, Slack, WhatsApp, Signal, and CLI
- Multiple terminal backends: local, Docker, SSH, Singularity, Modal, Daytona, Vercel Sandbox
- Scheduled automations with built-in cron
- Subagent delegation for parallel workstreams

## References

- [Hermes Agent Documentation](https://hermes-agent.nousresearch.com/docs)
- [Hermes Agent GitHub Repository](https://github.com/NousResearch/hermes-agent)
- [Nous Research](https://nousresearch.com)
