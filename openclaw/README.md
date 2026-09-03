# OpenClaw - AI Assistant

Sandbox template for [OpenClaw](https://github.com/openclaw/openclaw), an open-source AI assistant that runs on your devices and meets you in the channels you already use.

## What's Included

- **Ubuntu 22.04** base image
- **Node.js 22** (OpenClaw requires Node 22.22.3+, 24.15+, or 25.9+)
- **OpenClaw** (`openclaw@latest`) pre-installed globally
- Common development tools: git, curl, wget, build-essential

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Depends on provider | API key for OpenAI models |
| `ANTHROPIC_API_KEY` | Depends on provider | API key for Anthropic models |

OpenClaw supports multiple model providers. Set the API key for your chosen provider.

## Usage

```bash
# Install the template
sbox install Serverless-Sandbox/awesome-templates//openclaw

# Create a sandbox with your API key
sbox create openclaw --env OPENAI_API_KEY=sk-...

# Or set the key in your environment first
export OPENAI_API_KEY=sk-...
sbox create openclaw
```

## Runtime Requirements

- **Node.js**: 22.22.3+ (pre-installed in the image)
- **RAM**: 6 GB+ recommended
- **Network**: Internet access required for model API calls

## Features

- Gateway-based architecture connecting models, tools, and messaging channels
- Supports WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, and more
- Tools, skills, and plugins for extensibility
- Works with hosted and local model providers

## References

- [OpenClaw Documentation](https://docs.openclaw.ai)
- [OpenClaw GitHub Repository](https://github.com/openclaw/openclaw)
- [OpenClaw Website](https://openclaw.ai)
