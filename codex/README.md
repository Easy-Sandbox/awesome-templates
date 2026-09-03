# Codex - OpenAI Coding Agent

Sandbox template for [OpenAI Codex CLI](https://github.com/openai/codex), a coding agent that runs locally in your terminal.

## What's Included

- **Ubuntu 22.04** base image
- **Node.js 22 LTS** (required by Codex CLI)
- **OpenAI Codex CLI** (`@openai/codex`) pre-installed globally
- Common development tools: git, curl, wget, build-essential

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key from [platform.openai.com](https://platform.openai.com) |

## Usage

```bash
# Install the template
sbox install Serverless-Sandbox/awesome-templates//codex

# Create a sandbox with your API key
sbox create codex --env OPENAI_API_KEY=sk-...

# Or set the key in your environment first
export OPENAI_API_KEY=sk-...
sbox create codex
```

## Runtime Requirements

- **Node.js**: 22+ (pre-installed in the image)
- **RAM**: 4 GB+ recommended
- **Network**: Internet access required for OpenAI API calls

## References

- [Codex CLI Documentation](https://learn.chatgpt.com/docs/codex/cli)
- [Codex GitHub Repository](https://github.com/openai/codex)
- [npm: @openai/codex](https://www.npmjs.com/package/@openai/codex)
