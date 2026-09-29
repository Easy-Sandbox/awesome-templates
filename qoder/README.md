# qoder

> [中文版](#中文) | [English](#english)

---

## English

Sandbox runtime for the Qoder AI coding assistant — an intelligent development sandbox combining Python 3.11 and Node.js 22.

### Environment

This template comes preinstalled with the following tools and dependencies:

| Category | Details |
|----------|---------|
| **OS** | Ubuntu 22.04 |
| **Python** | Python 3.11 + venv (at `/opt/venv`) |
| **Node.js** | Node.js 22.x + npm |
| **Python packages** | `httpx`, `rich`, `pyyaml` |
| **System tools** | git, curl, wget, ripgrep, jq, build-essential, openssh-client |
| **Resources** | 2 CPU / 4096 MB memory |

### Installation

**Install from a local path:**

```bash
ebx install ./examples/templates/qoder --registry-type local
```

**Install from GitHub:**

```bash
ebx install Easy-Sandbox/awesome-templates//qoder
```

### Usage

Create a sandbox instance and pass in the API key:

```bash
ebx create --template qoder --env E2B_API_KEY=your-api-key
```

Run development tasks inside the sandbox:

```bash
ebx exec <sandbox-id> -- python3 -c "print('Hello from Qoder sandbox')"
ebx exec <sandbox-id> -- node -e "console.log('Node.js ready')"
```

Using the Python SDK:

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="qoder",
    env={"E2B_API_KEY": "your-api-key"}
)

result = sandbox.commands.run("python3 --version && node --version")
print(result.stdout)
```

### Configuration

#### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `E2B_API_KEY` | Sandbox API key | Yes |
| `WORKSPACE` | Working directory path, defaults to `/workspace` | No |

#### Custom Configuration

To install extra dependencies on top of this template, run the following after the sandbox is created:

```bash
ebx exec <sandbox-id> -- pip install <package-name>
ebx exec <sandbox-id> -- npm install -g <package-name>
```

### Notes

- **API key security**: Never hardcode `E2B_API_KEY` into the template; always inject it via the `--env` option or environment variables.
- **Dual runtimes**: The environment supports both Python 3.11 and Node.js 22 — pick whichever fits your project.
- **Virtual environment**: Python packages are installed in `/opt/venv`; no manual activation is needed since `PATH` is preconfigured.
- **SSH support**: `openssh-client` is preinstalled, enabling Git-over-SSH operations.

---

## 中文

Qoder AI 编程助手的沙箱运行环境，集成 Python 3.11 与 Node.js 22 的智能开发沙箱。

### 环境说明

本模板预装以下工具和依赖：

| 类别 | 内容 |
|------|------|
| **操作系统** | Ubuntu 22.04 |
| **Python** | Python 3.11 + venv 虚拟环境（位于 `/opt/venv`） |
| **Node.js** | Node.js 22.x + npm |
| **Python 包** | `httpx`、`rich`、`pyyaml` |
| **系统工具** | git、curl、wget、ripgrep、jq、build-essential、openssh-client |
| **资源配置** | 2 CPU / 4096 MB 内存 |

### 安装方式

**从本地安装：**

```bash
ebx install ./examples/templates/qoder --registry-type local
```

**从 GitHub 安装：**

```bash
ebx install Easy-Sandbox/awesome-templates//qoder
```

### 使用示例

创建沙箱实例并传入 API Key：

```bash
ebx create --template qoder --env E2B_API_KEY=your-api-key
```

在沙箱中执行开发任务：

```bash
ebx exec <sandbox-id> -- python3 -c "print('Hello from Qoder sandbox')"
ebx exec <sandbox-id> -- node -e "console.log('Node.js ready')"
```

使用 Python SDK：

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(
    template="qoder",
    env={"E2B_API_KEY": "your-api-key"}
)

result = sandbox.commands.run("python3 --version && node --version")
print(result.stdout)
```

### 配置说明

#### 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `E2B_API_KEY` | 沙箱 API 密钥 | 是 |
| `WORKSPACE` | 工作目录路径，默认 `/workspace` | 否 |

#### 自定义配置

如需在模板基础上安装额外依赖，可在创建沙箱后执行：

```bash
ebx exec <sandbox-id> -- pip install <package-name>
ebx exec <sandbox-id> -- npm install -g <package-name>
```

### 注意事项

- **API Key 安全**：请勿将 `E2B_API_KEY` 硬编码到模板中，始终通过 `--env` 参数或环境变量注入。
- **双运行时**：环境同时支持 Python 3.11 和 Node.js 22，可根据项目需求选择。
- **虚拟环境**：Python 包安装在 `/opt/venv` 中，使用时无需手动激活，`PATH` 已自动配置。
- **SSH 支持**：已安装 `openssh-client`，支持 Git SSH 协议操作。
