FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS (required by Codex CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install OpenAI Codex CLI globally
RUN npm install -g @openai/codex

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Codex requires OPENAI_API_KEY at runtime
# Pass it via: docker run -e OPENAI_API_KEY=sk-... <image>
ENV OPENAI_API_KEY=""

CMD ["codex"]
