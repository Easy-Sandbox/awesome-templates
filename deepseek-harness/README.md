# deepseek-harness

> [中文版](#中文) | [English](#english)

---

## English

Sandbox runtime for a DeepSeek model-driven AI coding agent, supporting code generation, completion, and intelligent programming assistance.

### Environment

This template comes preinstalled with the following tools and dependencies:

| Category | Details |
|----------|---------|
| **OS** | Ubuntu 22.04 |
| **Node.js** | Node.js 22.x + npm (core runtime) |
| **Python** | Python 3.11 + venv (at `/opt/venv`) |
| **Python packages** | `openai>=1.0`, `httpx`, `rich` |
| **System tools** | git, curl, build-essential |
| **Resources** | 2 CPU / 4096 MB memory |

### Installation

**Install from a local path:**

```bash
ebx install ./examples/templates/deepseek-harness --registry-type local
```

**Install from GitHub:**

```bash
ebx install Easy-Sandbox/awesome-templates//deepseek-harness
```

### Usage

Create a sandbox instance and pass in the API key:

```bash
ebx create --template deepseek-harness --env DEEPSEEK_API_KEY=sk-xxx
```

Call a DeepSeek model inside the sandbox via the OpenAI-compatible interface:

```bash
ebx exec <sandbox-id> -- python3 -c "
from openai import OpenAI
client = OpenAI(
    api_key='your-deepseek-key',
    base_url='https://api.deepseek.com'
)
response = client.chat.completions.create(
    model='deepseek-coder',
    messages=[{'role': 'user', 'content': 'Write a quicksort algorithm'}]
)
print(response.choices[0].message.content)
"
```

Using the Python SDK:

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="deepseek-harness",
    env={"DEEPSEEK_API_KEY": "sk-xxx"}
)

result = sandbox.commands.run("python3 --version && node --version")
print(result.stdout)
```

### Configuration

#### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | Yes |
| `WORKSPACE` | Working directory path, defaults to `/workspace` | No |

#### Manual Agent Plugin Installation

This template provides a base development runtime. To install a specific agent plugin or framework:

```bash
# Install a Python agent framework
ebx exec <sandbox-id> -- pip install langchain langgraph

# Install a Node.js agent tool
ebx exec <sandbox-id> -- npm install -g <agent-tool>
```

### Notes

- **API key security**: Never hardcode `DEEPSEEK_API_KEY` into the template; always inject it via the `--env` option or environment variables.
- **API compatibility**: DeepSeek offers an OpenAI-compatible interface with the base URL `https://api.deepseek.com`.
- **Network access**: The DeepSeek API must be reachable — make sure the sandbox has outbound internet connectivity.
- **Dual runtimes**: The environment supports both Python 3.11 and Node.js 22 — pick whichever fits your plugin needs.
- **Virtual environment**: Python packages are installed in `/opt/venv`; no manual activation is needed since `PATH` is preconfigured.

---

## 中文

DeepSeek 模型驱动的 AI 编程 Agent 沙箱运行环境，支持代码生成、补全和智能编程辅助。

### 环境说明

本模板预装以下工具和依赖：

| 类别 | 内容 |
|------|------|
| **操作系统** | Ubuntu 22.04 |
| **Node.js** | Node.js 22.x + npm（核心运行时） |
| **Python** | Python 3.11 + venv 虚拟环境（位于 `/opt/venv`） |
| **Python 包** | `openai>=1.0`、`httpx`、`rich` |
| **系统工具** | git、curl、build-essential |
| **资源配置** | 2 CPU / 4096 MB 内存 |

### 安装方式

**从本地安装：**

```bash
ebx install ./examples/templates/deepseek-harness --registry-type local
```

**从 GitHub 安装：**

```bash
ebx install Easy-Sandbox/awesome-templates//deepseek-harness
```

### 使用示例

创建沙箱实例并传入 API Key：

```bash
ebx create --template deepseek-harness --env DEEPSEEK_API_KEY=sk-xxx
```

在沙箱中通过 OpenAI 兼容接口调用 DeepSeek 模型：

```bash
ebx exec <sandbox-id> -- python3 -c "
from openai import OpenAI
client = OpenAI(
    api_key='your-deepseek-key',
    base_url='https://api.deepseek.com'
)
response = client.chat.completions.create(
    model='deepseek-coder',
    messages=[{'role': 'user', 'content': '编写一个快速排序算法'}]
)
print(response.choices[0].message.content)
"
```

使用 Python SDK：

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="deepseek-harness",
    env={"DEEPSEEK_API_KEY": "sk-xxx"}
)

result = sandbox.commands.run("python3 --version && node --version")
print(result.stdout)
```

### 配置说明

#### 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 是 |
| `WORKSPACE` | 工作目录路径，默认 `/workspace` | 否 |

#### 手动安装 Agent 插件

本模板提供基础开发运行时，如需安装特定 Agent 插件或框架：

```bash
# 安装 Python Agent 框架
ebx exec <sandbox-id> -- pip install langchain langgraph

# 安装 Node.js Agent 工具
ebx exec <sandbox-id> -- npm install -g <agent-tool>
```

### 注意事项

- **API Key 安全**：请勿将 `DEEPSEEK_API_KEY` 硬编码到模板中，始终通过 `--env` 参数或环境变量注入。
- **API 兼容性**：DeepSeek 提供 OpenAI 兼容接口，base URL 为 `https://api.deepseek.com`。
- **网络访问**：需要访问 DeepSeek API，确保沙箱具备外网连接能力。
- **双运行时**：环境同时支持 Python 3.11 和 Node.js 22，可根据插件需求选择。
- **虚拟环境**：Python 包安装在 `/opt/venv` 中，使用时无需手动激活，`PATH` 已自动配置。
