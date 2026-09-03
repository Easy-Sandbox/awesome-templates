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

# Install Node.js 22 (OpenClaw requires Node 22.22.3+, 24.15+, or 25.9+)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally
RUN npm install -g openclaw@latest

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# OpenClaw supports multiple model providers
# Set the API key for your chosen provider at runtime
# Pass it via: docker run -e OPENAI_API_KEY=sk-... <image>
ENV OPENAI_API_KEY=""
ENV ANTHROPIC_API_KEY=""

CMD ["openclaw"]
