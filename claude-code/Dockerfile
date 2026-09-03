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
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code via the official native installer
# This downloads a standalone binary - no Node.js needed at runtime
RUN curl -fsSL https://claude.ai/install.sh | bash

# Ensure claude is in PATH
ENV PATH="/root/.local/bin:${PATH}"

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Claude Code requires ANTHROPIC_API_KEY at runtime
# Pass it via: docker run -e ANTHROPIC_API_KEY=sk-ant-... <image>
ENV ANTHROPIC_API_KEY=""

CMD ["claude"]
