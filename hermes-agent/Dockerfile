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
    ffmpeg \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 (required by Hermes Agent)
RUN add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install Node.js (used by Hermes Agent for some tools)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager used by Hermes)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Install Hermes Agent via the official installer
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Ensure hermes is in PATH
ENV PATH="/root/.hermes/bin:${PATH}"
ENV HERMES_HOME="/root/.hermes"

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Hermes Agent supports multiple model providers
# Set the API key for your chosen provider at runtime
# Pass it via: docker run -e OPENROUTER_API_KEY=... <image>
ENV OPENAI_API_KEY=""
ENV ANTHROPIC_API_KEY=""
ENV OPENROUTER_API_KEY=""

CMD ["hermes"]
