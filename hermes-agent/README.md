# hermes-agent

> [中文版](#中文) | [English](#english)

---

## English

Sandbox runtime for AI agents driven by NousResearch Hermes models, supporting tool calling and multimodal tasks.

### Environment

This template comes preinstalled with the following tools and dependencies:

| Category | Details |
|----------|---------|
| **OS** | Ubuntu 22.04 |
| **Python** | Python 3.11 + venv (at `/opt/venv`) |
| **Node.js** | Node.js 22.x + npm |
| **Python packages** | `uv`, `openai>=1.0`, `httpx`, `rich`, `pyyaml` |
| **System tools** | git, curl, xz-utils, build-essential, ripgrep, ffmpeg |
| **Resources** | 2 CPU / 4096 MB memory (8192 MB recommended for browser scenarios) |

### Installation

**Install from a local path:**

```bash
ebx install ./examples/templates/hermes-agent --registry-type local
```

**Install from GitHub:**

```bash
ebx install Easy-Sandbox/awesome-templates//hermes-agent
```

### Usage

Create a sandbox instance and pass in the LLM configuration:

```bash
ebx create --template hermes-agent \
    --env OPENAI_API_KEY=sk-xxx \
    --env OPENAI_BASE_URL=https://api.your-provider.com/v1
```

Quickly install agent frameworks with uv:

```bash
ebx exec <sandbox-id> -- uv pip install langchain langgraph
```

Call a Hermes model via the OpenAI-compatible interface:

```bash
ebx exec <sandbox-id> -- python3 -c "
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model='NousResearch/Hermes-3-Llama-3.1-8B',
    messages=[{'role': 'user', 'content': 'Write a file search tool'}],
    tools=[{
        'type': 'function',
        'function': {
            'name': 'search_files',
            'description': 'Search files',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}}
        }
    }]
)
print(response.choices[0].message)
"
```

Using the Python SDK:

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="hermes-agent",
    env={
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_BASE_URL": "https://api.your-provider.com/v1"
    }
)

result = sandbox.commands.run("python3 --version && uv --version")
print(result.stdout)
```

### Configuration

#### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | LLM provider API key | Yes |
| `OPENAI_BASE_URL` | LLM API base URL (for self-hosted or third-party hosting) | No |
| `WORKSPACE` | Working directory path, defaults to `/workspace` | No |

#### Managing Dependencies with uv

This template ships with `uv`, a high-performance Python package manager. Using `uv` instead of `pip` is recommended:

```bash
# Install packages with uv (much faster than pip)
ebx exec <sandbox-id> -- uv pip install <package-name>

# Create a project with uv
ebx exec <sandbox-id> -- uv init my-agent-project
```

### Notes

- **API key security**: Never hardcode API keys into the template; always inject them via the `--env` option or environment variables.
- **Model compatibility**: Hermes models are accessed via the OpenAI-compatible interface; configure `OPENAI_BASE_URL` to point at the actual hosting address.
- **Resource recommendations**: 4096 MB of memory is sufficient for basic agent tasks; 8192 MB is recommended for browser automation or multimedia processing.
- **ffmpeg support**: ffmpeg is preinstalled for audio/video processing tasks.
- **Virtual environment**: Python packages are installed in `/opt/venv`; no manual activation is needed since `PATH` is preconfigured.

---

## 中文

NousResearch Hermes 系列模型驱动的 AI Agent 沙箱运行环境，支持工具调用（Tool Calling）和多模态任务。

### 环境说明

本模板预装以下工具和依赖：

| 类别 | 内容 |
|------|------|
| **操作系统** | Ubuntu 22.04 |
| **Python** | Python 3.11 + venv 虚拟环境（位于 `/opt/venv`） |
| **Node.js** | Node.js 22.x + npm |
| **Python 包** | `uv`、`openai>=1.0`、`httpx`、`rich`、`pyyaml` |
| **系统工具** | git、curl、xz-utils、build-essential、ripgrep、ffmpeg |
| **资源配置** | 2 CPU / 4096 MB 内存（建议 8192 MB 带浏览器场景） |

### 安装方式

**从本地安装：**

```bash
ebx install ./examples/templates/hermes-agent --registry-type local
```

**从 GitHub 安装：**

```bash
ebx install Easy-Sandbox/awesome-templates//hermes-agent
```

### 使用示例

创建沙箱实例并传入 LLM 配置：

```bash
ebx create --template hermes-agent \
    --env OPENAI_API_KEY=sk-xxx \
    --env OPENAI_BASE_URL=https://api.your-provider.com/v1
```

使用 uv 快速安装 Agent 框架：

```bash
ebx exec <sandbox-id> -- uv pip install langchain langgraph
```

通过 OpenAI 兼容接口调用 Hermes 模型：

```bash
ebx exec <sandbox-id> -- python3 -c "
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model='NousResearch/Hermes-3-Llama-3.1-8B',
    messages=[{'role': 'user', 'content': '编写一个文件搜索工具'}],
    tools=[{
        'type': 'function',
        'function': {
            'name': 'search_files',
            'description': '搜索文件',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}}
        }
    }]
)
print(response.choices[0].message)
"
```

使用 Python SDK：

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="hermes-agent",
    env={
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_BASE_URL": "https://api.your-provider.com/v1"
    }
)

result = sandbox.commands.run("python3 --version && uv --version")
print(result.stdout)
```

### 配置说明

#### 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `OPENAI_API_KEY` | LLM 提供商 API 密钥 | 是 |
| `OPENAI_BASE_URL` | LLM API 基础 URL（用于自部署或第三方托管） | 否 |
| `WORKSPACE` | 工作目录路径，默认 `/workspace` | 否 |

#### 使用 uv 管理依赖

本模板预装 `uv` 作为高性能 Python 包管理器，建议使用 `uv` 替代 `pip`：

```bash
# 使用 uv 安装包（速度远快于 pip）
ebx exec <sandbox-id> -- uv pip install <package-name>

# 使用 uv 创建项目
ebx exec <sandbox-id> -- uv init my-agent-project
```

### 注意事项

- **API Key 安全**：请勿将 API Key 硬编码到模板中，始终通过 `--env` 参数或环境变量注入。
- **模型兼容**：Hermes 模型通过 OpenAI 兼容接口访问，需配置 `OPENAI_BASE_URL` 指向实际托管地址。
- **资源建议**：基础 Agent 任务使用 4096 MB 内存即可；涉及浏览器自动化或多媒体处理时建议 8192 MB。
- **ffmpeg 支持**：已预装 ffmpeg，支持音视频处理任务。
- **虚拟环境**：Python 包安装在 `/opt/venv` 中，使用时无需手动激活，`PATH` 已自动配置。
