# Claude Code - Anthropic Coding Agent

Sandbox template for [Claude Code](https://code.claude.com/), Anthropic's agentic coding tool that lives in your terminal.

## What's Included

- **Ubuntu 22.04** base image
- **Claude Code CLI** installed via the official native installer (standalone binary)
- **ripgrep** for fast code search (used by Claude Code internally)
- Common development tools: git, curl, wget, build-essential

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key from [console.anthropic.com](https://console.anthropic.com) |

## Usage

```bash
# Install the template
sbox install Serverless-Sandbox/awesome-templates//claude-code

# Create a sandbox with your API key
sbox create claude-code --env ANTHROPIC_API_KEY=sk-ant-...

# Or set the key in your environment first
export ANTHROPIC_API_KEY=sk-ant-...
sbox create claude-code
```

## Runtime Requirements

- **RAM**: 4 GB+ recommended
- **Network**: Internet access required for Anthropic API calls
- **OS**: Ubuntu 20.04+ (pre-configured in the image)

## Notes

- Claude Code now ships as a **standalone native binary** — no Node.js runtime is required
- The native installer (`curl -fsSL https://claude.ai/install.sh | bash`) is the recommended installation method
- Alternatively, you can install via npm: `npm install -g @anthropic-ai/claude-code` (requires Node.js 22+)
- Claude Code requires a Pro, Max, Team, Enterprise, or Console account (the free plan does not include Claude Code access)

## References

- [Claude Code Documentation](https://code.claude.com/docs/en/setup)
- [npm: @anthropic-ai/claude-code](https://www.npmjs.com/package/@anthropic-ai/claude-code)
