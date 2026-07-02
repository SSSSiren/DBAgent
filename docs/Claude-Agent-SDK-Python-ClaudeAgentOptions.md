# Claude Agent SDK Python — ClaudeAgentOptions 完整参考文档

> 本文档基于 [Claude Code 官方文档 - Agent SDK Python](https://code.claude.com/docs/zh-CN/agent-sdk/python) 整理，涵盖 `ClaudeAgentOptions` 所有配置项及其关联类型定义。

---

## 目录

1. [概述](#概述)
2. [ClaudeAgentOptions 完整字段列表](#claudeagentoptions-完整字段列表)
3. [关联类型定义](#关联类型定义)
   - [PermissionMode](#permissionmode)
   - [EffortLevel](#effortlevel)
   - [SettingSource](#settingsource)
   - [SystemPromptPreset](#systempromptpreset)
   - [ToolsPreset](#toolspreset)
   - [ThinkingConfig](#thinkingconfig)
   - [ThinkingDisplay](#thinkingdisplay)
   - [SdkBeta](#sdkbeta)
   - [SdkPluginConfig](#sdkpluginconfig)
   - [OutputFormat](#outputformat)
   - [AgentDefinition](#agentdefinition)
   - [McpServerConfig](#mcpserverconfig)
   - [McpStatusResponse / McpServerStatus](#mcpstatusresponse--mcpserverstatus)
   - [CanUseTool](#canusetool)
   - [ToolPermissionContext](#toolpermissioncontext)
   - [PermissionResult / PermissionResultAllow / PermissionResultDeny](#permissionresult)
   - [PermissionUpdate / PermissionRuleValue](#permissionupdate)
   - [HookEvent](#hookevent)
   - [HookMatcher](#hookmatcher)
   - [HookCallback](#hookcallback)
   - [HookContext](#hookcontext)
   - [HookInput 及其子类型](#hookinput)
   - [HookJSONOutput / SyncHookJSONOutput / AsyncHookJSONOutput](#hookjsonoutput)
   - [HookSpecificOutput 及其子类型](#hookspecificoutput)
   - [SessionStore](#sessionstore)
   - [SessionStoreFlushMode](#sessionstoreflushmode)
   - [SessionKey](#sessionkey)
   - [Message 类型](#message-类型)
   - [ContentBlock 类型](#contentblock-类型)
   - [错误类型](#错误类型)
   - [SdkMcpTool / ToolAnnotations](#sdkmcptool)
   - [Transport](#transport)
   - [McpStatusResponse / McpServerStatus](#mcpstatusresponse--mcpserverstatus)
   - [ClaudeSDKClient 类](#claudesdkclient-类)
   - [query() 函数](#query-函数)
   - [tool() 装饰器](#tool-装饰器)
   - [create_sdk_mcp_server()](#create_sdk_mcp_server)
   - [Session 类型与工具函数](#session-类型与工具函数)
4. [代码示例](#代码示例)
   - [基础用法](#基础用法)
   - [自定义权限处理器](#自定义权限处理器)
   - [Setting Sources 配置](#setting-sources-配置)
   - [环境变量配置](#环境变量配置)
   - [Thinking 配置](#thinking-配置)
   - [MCP 服务器配置](#mcp-服务器配置)
   - [可中断任务](#可中断任务)
   - [Hooks 拦截工具调用](#hooks-拦截工具调用)
   - [Session 持久化](#session-持久化)
5. [Env 环境变量参考](#env-环境变量参考)
6. [注意事项](#注意事项)

---

## 概述

`ClaudeAgentOptions` 是一个 `@dataclass` 配置类，用于配置 Claude Code 查询的行为。它作为 `options` 参数传递给 `query()` 函数和 `ClaudeSDKClient` 构造函数。

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ClaudeSDKClient

# 方式一：使用 query()
async for message in query(prompt="...", options=ClaudeAgentOptions(...)):
    print(message)

# 方式二：使用 ClaudeSDKClient
async with ClaudeSDKClient(options=ClaudeAgentOptions(...)) as client:
    await client.query("...")
    async for message in client.receive_response():
        print(message)
```

---

## ClaudeAgentOptions 完整字段列表

```python
@dataclass
class ClaudeAgentOptions:
    # 工具配置
    tools: list[str] | ToolsPreset | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    # 提示词与系统配置
    system_prompt: str | SystemPromptPreset | None = None
    permission_mode: PermissionMode | None = None
    permission_prompt_tool_name: str | None = None

    # MCP 服务器
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)
    strict_mcp_config: bool = False

    # 会话管理
    continue_conversation: bool = False
    resume: str | None = None
    fork_session: bool = False

    # 限制
    max_turns: int | None = None
    max_budget_usd: float | None = None

    # 模型
    model: str | None = None
    fallback_model: str | None = None
    betas: list[SdkBeta] = field(default_factory=list)

    # 输出格式
    output_format: dict[str, Any] | None = None

    # 路径与工作目录
    cwd: str | Path | None = None
    cli_path: str | Path | None = None
    settings: str | None = None
    add_dirs: list[str | Path] = field(default_factory=list)

    # 环境变量
    env: dict[str, str] = field(default_factory=dict)
    extra_args: dict[str, str | None] = field(default_factory=dict)

    # 缓冲区
    max_buffer_size: int | None = None

    # 调试（已弃用）
    debug_stderr: Any = sys.stderr  # Deprecated: 使用 stderr 回调替代

    # 回调
    stderr: Callable[[str], None] | None = None
    can_use_tool: CanUseTool | None = None

    # Hooks
    hooks: dict[HookEvent, list[HookMatcher]] | None = None

    # 用户标识
    user: str | None = None

    # 消息流控制
    include_partial_messages: bool = False
    include_hook_events: bool = False

    # 子代理与插件
    agents: dict[str, AgentDefinition] | None = None
    plugins: list[SdkPluginConfig] = field(default_factory=list)

    # 设置来源
    setting_sources: list[SettingSource] | None = None

    # 技能
    skills: list[str] | Literal["all"] | None = None

    # 沙箱
    sandbox: SandboxSettings | None = None

    # 思考（Thinking）
    max_thinking_tokens: int | None = None  # Deprecated: 使用 thinking 替代
    thinking: ThinkingConfig | None = None
    effort: EffortLevel | None = None

    # 文件检查点
    enable_file_checkpointing: bool = False

    # 会话存储
    session_store: SessionStore | None = None
    session_store_flush: SessionStoreFlushMode = "batched"
```

### 字段详解

| # | 字段 | 类型 | 默认值 | 描述 |
|---|------|------|--------|------|
| 1 | `tools` | `list[str] \| ToolsPreset \| None` | `None` | 工具配置。使用 `{"type": "preset", "preset": "claude_code"}` 获取 Claude Code 的默认工具集。 |
| 2 | `allowed_tools` | `list[str]` | `[]` | 无需提示即可自动批准的工具列表。**注意**：这不会限制 Claude 只能使用这些工具；未列出的工具通过 `permission_mode` 和 `can_use_tool` 处理。使用 `disallowed_tools` 来阻止工具。 |
| 3 | `disallowed_tools` | `list[str]` | `[]` | 要拒绝的工具列表。裸名称如 `"Bash"` 会从 Claude 上下文中移除该工具。作用域规则如 `"Bash(rm *)"` 保留工具可用但拒绝匹配的调用，在所有权限模式（包括 `bypassPermissions`）下都生效。 |
| 4 | `system_prompt` | `str \| SystemPromptPreset \| None` | `None` | 系统提示词配置。传入字符串作为自定义提示词，或传入 `{"type": "preset", "preset": "claude_code"}` 使用 Claude Code 的系统提示词。可添加 `"append"` 字段来扩展预设。 |
| 5 | `mcp_servers` | `dict[str, McpServerConfig] \| str \| Path` | `{}` | MCP 服务器配置或配置文件路径。 |
| 6 | `strict_mcp_config` | `bool` | `False` | 当为 `True` 时，仅使用 `mcp_servers` 中传入的服务器，忽略项目 `.mcp.json`、用户设置、插件提供的 MCP 服务器和 claude.ai 连接器。对应 CLI 的 `--strict-mcp-config` 标志。 |
| 7 | `permission_mode` | `PermissionMode \| None` | `None` | 工具使用的权限模式。详见 [PermissionMode](#permissionmode)。 |
| 8 | `continue_conversation` | `bool` | `False` | 继续最近的对话。 |
| 9 | `resume` | `str \| None` | `None` | 要恢复的会话 ID。 |
| 10 | `fork_session` | `bool` | `False` | 当使用 `resume` 恢复时，分叉到新的会话 ID 而不是继续原始会话。 |
| 11 | `max_turns` | `int \| None` | `None` | 最大代理轮次（工具使用的往返次数）。 |
| 12 | `max_budget_usd` | `float \| None` | `None` | 当客户端成本估算达到此 USD 值时停止查询。 |
| 13 | `model` | `str \| None` | `None` | Claude 模型别名或完整模型名称。 |
| 14 | `fallback_model` | `str \| None` | `None` | 主模型失败时的回退模型。 |
| 15 | `betas` | `list[SdkBeta]` | `[]` | 要启用的 Beta 功能。`SdkBeta = Literal["context-1m-2025-08-07"]`（自 2026 年 4 月 30 日起已弃用）。 |
| 16 | `output_format` | `dict[str, Any] \| None` | `None` | 结构化响应的输出格式，例如 `{"type": "json_schema", "schema": {...}}`。 |
| 17 | `permission_prompt_tool_name` | `str \| None` | `None` | 用于权限提示的 MCP 工具名称。 |
| 18 | `cwd` | `str \| Path \| None` | `None` | 当前工作目录。 |
| 19 | `cli_path` | `str \| Path \| None` | `None` | Claude Code CLI 可执行文件的自定义路径。 |
| 20 | `settings` | `str \| None` | `None` | 设置文件路径。 |
| 21 | `add_dirs` | `list[str \| Path]` | `[]` | Claude 可以访问的额外目录。 |
| 22 | `env` | `dict[str, str]` | `{}` | 环境变量，合并到继承的进程环境之上。 |
| 23 | `extra_args` | `dict[str, str \| None]` | `{}` | 直接传递给 CLI 的额外参数。 |
| 24 | `max_buffer_size` | `int \| None` | `None` | 缓冲 CLI stdout 时的最大字节数。 |
| 25 | `debug_stderr` | `Any` | `sys.stderr` | **已弃用** — 使用 `stderr` 回调替代。 |
| 26 | `stderr` | `Callable[[str], None] \| None` | `None` | 来自 CLI 的 stderr 输出的回调函数。 |
| 27 | `can_use_tool` | `CanUseTool \| None` | `None` | 工具权限回调函数，仅在权限流程落到提示阶段时调用。已被 `allowed_tools`、allow 规则或 `permission_mode` 自动批准的操作不会触发此回调。详见 [CanUseTool](#canusetool)。 |
| 28 | `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | `None` | 用于拦截事件的 Hooks 配置。 |
| 29 | `user` | `str \| None` | `None` | 用户标识符。 |
| 30 | `include_partial_messages` | `bool` | `False` | 包含部分消息流事件。启用时产生 `StreamEvent` 消息。 |
| 31 | `include_hook_events` | `bool` | `False` | 在消息流中包含 hooks 生命周期事件作为 `HookEventMessage` 对象。 |
| 32 | `agents` | `dict[str, AgentDefinition] \| None` | `None` | 以编程方式定义的子代理（subagents）。 |
| 33 | `setting_sources` | `list[SettingSource] \| None` | `None`（CLI 默认：所有来源） | 控制加载哪些文件系统设置。传入 `[]` 禁用用户、项目和本地设置。托管策略设置始终加载；服务器管理的设置在会话使用组织凭据进行身份验证时获取。 |
| 34 | `skills` | `list[str] \| Literal["all"] \| None` | `None` | 会话可用的技能。传入 `"all"` 启用所有发现的技能，或传入技能名称列表。当设置时，SDK 自动将 Skill 工具添加到 `allowed_tools`。 |
| 35 | `sandbox` | `SandboxSettings \| None` | `None` | 以编程方式配置沙箱行为。 |
| 36 | `plugins` | `list[SdkPluginConfig]` | `[]` | 从本地路径加载自定义插件。 |
| 37 | `max_thinking_tokens` | `int \| None` | `None` | **已弃用** — 使用 `thinking` 替代。 |
| 38 | `thinking` | `ThinkingConfig \| None` | `None` | 控制扩展思考行为。优先于 `max_thinking_tokens`。 |
| 39 | `effort` | `EffortLevel \| None` | `None` | 思考深度的努力级别。 |
| 40 | `enable_file_checkpointing` | `bool` | `False` | 启用文件更改跟踪以支持回滚。 |
| 41 | `session_store` | `SessionStore \| None` | `None` | 将会话记录镜像到外部后端，以便任何主机都可以恢复它们。 |
| 42 | `session_store_flush` | `Literal["batched", "eager"]` | `"batched"` | 何时将镜像记录刷新到 `session_store`。`"batched"` 每轮刷新一次或缓冲区满时刷新；`"eager"` 每帧后触发后台刷新。当 `session_store` 为 `None` 时忽略。 |

---

## 关联类型定义

### PermissionMode

```python
PermissionMode = Literal[
    "default",            # 标准权限行为
    "acceptEdits",        # 自动接受文件编辑
    "plan",               # 规划模式 - 探索但不编辑
    "dontAsk",            # 拒绝任何未预先批准的操作
    "bypassPermissions",  # 绕过权限检查（谨慎使用）
]
```

| 值 | 描述 |
|----|------|
| `"default"` | 标准权限行为，根据操作类型提示用户 |
| `"acceptEdits"` | 自动接受文件编辑操作（Write、Edit），其他操作仍需确认 |
| `"plan"` | 规划模式，允许探索但不允许编辑文件 |
| `"dontAsk"` | 拒绝任何未在 `allowed_tools` 中列出的操作 |
| `"bypassPermissions"` | 绕过权限检查，但显式的 ask 规则仍会触发提示（需谨慎使用） |

---

### EffortLevel

```python
EffortLevel = Literal[
    "low",     # 最小思考，最快响应
    "medium",  # 中等思考
    "high",    # 深度推理
    "xhigh",   # 扩展推理（Opus 4.8/4.7；在其他模型上回退到 "high"）
    "max",     # 最大努力
]
```

| 值 | 描述 |
|----|------|
| `"low"` | 最小思考量，适合简单任务，响应最快 |
| `"medium"` | 中等思考量，平衡速度与质量 |
| `"high"` | 深度推理，适合复杂任务 |
| `"xhigh"` | 扩展推理，仅 Opus 4.7/4.8 支持，其他模型回退到 `"high"` |
| `"max"` | 最大推理努力，适合最复杂的任务 |

---

### SettingSource

```python
SettingSource = Literal["user", "project", "local"]
```

| 值 | 描述 | 位置 |
|----|------|------|
| `"user"` | 全局用户设置 | `~/.claude/settings.json` |
| `"project"` | 共享项目设置（版本控制） | `.claude/settings.json` |
| `"local"` | 本地项目设置（gitignored） | `.claude/settings.local.json` |

**设置优先级**（从高到低）：
1. 本地设置（`.claude/settings.local.json`）
2. 项目设置（`.claude/settings.json`）
3. 用户设置（`~/.claude/settings.json`）

程序化选项（如 `agents`、`allowed_tools`）覆盖文件系统设置。托管策略设置覆盖程序化选项。

**默认行为**：当 `setting_sources` 省略或为 `None` 时，SDK 加载所有三个来源。

> **⚠️ 版本注意**：在 Python SDK 0.1.59 及更早版本中，`setting_sources=[]` 被等同于省略该选项，因此**不会**禁用文件系统设置。如需空列表生效，请升级到更新版本。

---

### SystemPromptPreset

```python
class SystemPromptPreset(TypedDict):
    type: Literal["preset"]
    preset: Literal["claude_code"]
    append: NotRequired[str]
    exclude_dynamic_sections: NotRequired[bool]
```

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["preset"]` | 是 | 必须为 `"preset"` |
| `preset` | `Literal["claude_code"]` | 是 | 必须为 `"claude_code"` |
| `append` | `str` | 否 | 追加到预设提示词末尾的自定义内容 |
| `exclude_dynamic_sections` | `bool` | 否 | 将每会话上下文（cwd、git 状态、memory 路径）从系统提示词移到第一条用户消息中，改善跨用户/机器的提示缓存 |

---

### ToolsPreset

```python
class ToolsPreset(TypedDict):
    type: Literal["preset"]
    preset: Literal["claude_code"]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `Literal["preset"]` | 必须为 `"preset"` |
| `preset` | `Literal["claude_code"]` | 必须为 `"claude_code"` |

**用法**：传入 `{"type": "preset", "preset": "claude_code"}` 到 `tools` 字段以获取 Claude Code 的默认工具集。

---

### ThinkingConfig

```python
ThinkingDisplay = Literal["summarized", "omitted"]

class ThinkingConfigEnabled(TypedDict):
    type: Literal["enabled"]
    budget_tokens: int
    display: NotRequired[ThinkingDisplay]

class ThinkingConfigAdaptive(TypedDict):
    type: Literal["adaptive"]
    display: NotRequired[ThinkingDisplay]

class ThinkingConfigDisabled(TypedDict):
    type: Literal["disabled"]

ThinkingConfig = ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled
```

#### ThinkingConfigEnabled

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["enabled"]` | 是 | 启用扩展思考 |
| `budget_tokens` | `int` | 是 | 思考预算令牌数 |
| `display` | `ThinkingDisplay` | 否 | 控制思考文本的返回方式 |

#### ThinkingConfigAdaptive

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["adaptive"]` | 是 | 自适应思考模式 |
| `display` | `ThinkingDisplay` | 否 | 控制思考文本的返回方式 |

#### ThinkingConfigDisabled

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["disabled"]` | 是 | 禁用扩展思考 |

---

### ThinkingDisplay

```python
ThinkingDisplay = Literal["summarized", "omitted"]
```

| 值 | 描述 |
|----|------|
| `"summarized"` | 返回思考内容的摘要 |
| `"omitted"` | 省略思考内容，不返回 |

> **注意**：在 Claude Opus 4.7+ 上，API 默认值为 `"omitted"`，因此需要设置 `"summarized"` 才能在 `ThinkingBlock` 输出中接收思考内容。

---

### SdkBeta

```python
SdkBeta = Literal["context-1m-2025-08-07"]
```

> **警告**：自 2026 年 4 月 30 日起已弃用。请改用 Claude Sonnet 5、Claude Sonnet 4.6、Opus 4.6、Opus 4.7 或 Opus 4.8，这些模型以标准定价包含 1M 上下文，无需 beta 头。

---

### SdkPluginConfig

```python
class SdkPluginConfig(TypedDict):
    type: Literal["local"]
    path: str
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `Literal["local"]` | 必须为 `"local"`（目前仅支持本地插件） |
| `path` | `str` | 插件目录的绝对或相对路径 |

**示例**：
```python
plugins = [
    {"type": "local", "path": "./my-plugin"},
    {"type": "local", "path": "/absolute/path/to/plugin"},
]
```

---

### OutputFormat

用于结构化输出验证的配置。作为 `dict` 传递给 `ClaudeAgentOptions.output_format`：

```python
{
    "type": "json_schema",
    "schema": {...},  # 你的 JSON Schema 定义
}
```

| 字段 | 必需 | 描述 |
|------|------|------|
| `type` | 是 | 必须为 `"json_schema"` |
| `schema` | 是 | 用于输出验证的 JSON Schema 定义 |

**示例**：
```python
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
        },
    }
)
```

---

### AgentDefinition

用于以编程方式定义子代理的 `@dataclass`。

> **⚠️ 注意**：字段名使用 **camelCase**（不是 snake_case）。传入 snake_case 关键字会引发 `TypeError`。

```python
@dataclass
class AgentDefinition:
    description: str                                  # 必需
    prompt: str                                        # 必需
    tools: list[str] | None = None
    disallowedTools: list[str] | None = None
    model: str | None = None
    skills: list[str] | None = None
    memory: Literal["user", "project", "local"] | None = None
    mcpServers: list[str | dict[str, Any]] | None = None
    initialPrompt: str | None = None
    maxTurns: int | None = None
    background: bool | None = None
    effort: EffortLevel | int | None = None
    permissionMode: PermissionMode | None = None
```

| 字段 | 必需 | 描述 |
|------|------|------|
| `description` | 是 | 自然语言描述，说明何时使用此代理 |
| `prompt` | 是 | 代理的系统提示词 |
| `tools` | 否 | 允许的工具名称列表。如果省略，继承所有工具 |
| `disallowedTools` | 否 | 要从代理工具集中移除的工具名称。接受 MCP 服务器级模式：`mcp__server`、`mcp__server__*`、`mcp__*` |
| `model` | 否 | 模型覆盖。接受别名（`"sonnet"`、`"opus"`、`"haiku"`、`"inherit"`）或完整模型 ID |
| `skills` | 否 | 此代理可用的技能名称 |
| `memory` | 否 | 记忆来源：`"user"`、`"project"` 或 `"local"` |
| `mcpServers` | 否 | 可用的 MCP 服务器。每个条目是服务器名称或内联 `{name: config}` 字典 |
| `initialPrompt` | 否 | 当代理作为主线程代理运行时自动提交的第一个用户轮次 |
| `maxTurns` | 否 | 代理停止前的最大轮次 |
| `background` | 否 | 调用时作为非阻塞后台任务运行 |
| `effort` | 否 | 推理努力级别。接受命名级别或整数 |
| `permissionMode` | 否 | 此代理内工具执行的权限模式 |

---

### McpServerConfig

```python
McpServerConfig = (
    McpStdioServerConfig | McpSSEServerConfig | McpHttpServerConfig | McpSdkServerConfig
)
```

#### McpStdioServerConfig

```python
class McpStdioServerConfig(TypedDict):
    type: NotRequired[Literal["stdio"]]  # 可选，为了向后兼容
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]
```

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["stdio"]` | 否 | 连接类型，可选用于向后兼容 |
| `command` | `str` | 是 | 要执行的命令 |
| `args` | `list[str]` | 否 | 命令行参数列表 |
| `env` | `dict[str, str]` | 否 | 环境变量 |

#### McpSSEServerConfig

```python
class McpSSEServerConfig(TypedDict):
    type: Literal["sse"]
    url: str
    headers: NotRequired[dict[str, str]]
```

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["sse"]` | 是 | 连接类型 |
| `url` | `str` | 是 | SSE 服务器 URL |
| `headers` | `dict[str, str]` | 否 | 自定义 HTTP 头 |

#### McpHttpServerConfig

```python
class McpHttpServerConfig(TypedDict):
    type: Literal["http"]
    url: str
    headers: NotRequired[dict[str, str]]
```

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `type` | `Literal["http"]` | 是 | 连接类型 |
| `url` | `str` | 是 | HTTP 服务器 URL |
| `headers` | `dict[str, str]` | 否 | 自定义 HTTP 头 |

#### McpSdkServerConfig

进程内 MCP 服务器，通过 `create_sdk_mcp_server()` 创建。

```python
class McpSdkServerConfig(TypedDict):
    type: Literal["sdk"]
    name: str
    instance: Any  # MCP Server 实例
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `Literal["sdk"]` | 连接类型 |
| `name` | `str` | 服务器名称 |
| `instance` | `Any` | MCP Server 实例 |

---

### CanUseTool

```python
CanUseTool = Callable[
    [str, dict[str, Any], ToolPermissionContext], Awaitable[PermissionResult]
]
```

回调函数签名：接收 `tool_name`（工具名称）、`input_data`（输入数据）和 `context`（`ToolPermissionContext`），返回 `PermissionResultAllow` 或 `PermissionResultDeny`。

---

### ToolPermissionContext

传递给工具权限回调（`CanUseTool`）的上下文 `@dataclass`。

```python
@dataclass
class ToolPermissionContext:
    signal: Any | None = None
    suggestions: list[PermissionUpdate] = field(default_factory=list)
    blocked_path: str | None = None
    decision_reason: str | None = None
    title: str | None = None
    display_name: str | None = None
    description: str | None = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `signal` | `Any \| None` | 保留用于未来的中止信号支持 |
| `suggestions` | `list[PermissionUpdate]` | 来自 CLI 的权限更新建议。Bash 提示包含带有 `localSettings` 目标的建议以持久化 |
| `blocked_path` | `str \| None` | 触发权限请求的文件路径（例如，当 Bash 访问允许目录之外的路径时） |
| `decision_reason` | `str \| None` | 触发此权限请求的原因。当 hooks 返回 `"ask"` 时从 PreToolUse hooks 的 `permissionDecisionReason` 转发 |
| `title` | `str \| None` | 完整权限提示句子（例如 `"Claude wants to read foo.txt"`） |
| `display_name` | `str \| None` | 工具操作的简短名词短语（例如 `"Read file"`），适用于按钮标签 |
| `description` | `str \| None` | 人类可读的权限 UI 副标题 |

---

### PermissionResult

```python
PermissionResult = PermissionResultAllow | PermissionResultDeny
```

#### PermissionResultAllow

```python
@dataclass
class PermissionResultAllow:
    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = None
    updated_permissions: list[PermissionUpdate] | None = None
```

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `behavior` | `Literal["allow"]` | `"allow"` | 必须为 `"allow"` |
| `updated_input` | `dict[str, Any] \| None` | `None` | 用于替代原始输入的修改后输入 |
| `updated_permissions` | `list[PermissionUpdate] \| None` | `None` | 要应用的权限更新 |

#### PermissionResultDeny

```python
@dataclass
class PermissionResultDeny:
    behavior: Literal["deny"] = "deny"
    message: str = ""
    interrupt: bool = False
```

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `behavior` | `Literal["deny"]` | `"deny"` | 必须为 `"deny"` |
| `message` | `str` | `""` | 解释为何拒绝工具调用的消息 |
| `interrupt` | `bool` | `False` | 是否中断当前执行 |

---

### PermissionUpdate

```python
@dataclass
class PermissionUpdate:
    type: Literal[
        "addRules",
        "replaceRules",
        "removeRules",
        "setMode",
        "addDirectories",
        "removeDirectories",
    ]
    rules: list[PermissionRuleValue] | None = None
    behavior: Literal["allow", "deny", "ask"] | None = None
    mode: PermissionMode | None = None
    directories: list[str] | None = None
    destination: (
        Literal["userSettings", "projectSettings", "localSettings", "session"] | None
    ) = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `Literal[...]` | 权限更新操作类型 |
| `rules` | `list[PermissionRuleValue] \| None` | 用于 add/replace/remove 操作的规则 |
| `behavior` | `Literal["allow", "deny", "ask"] \| None` | 基于规则操作的行为 |
| `mode` | `PermissionMode \| None` | 用于 setMode 操作的模式 |
| `directories` | `list[str] \| None` | 用于 add/remove 目录操作的目录列表 |
| `destination` | `Literal[...] \| None` | 应用权限更新的位置 |

#### PermissionRuleValue

```python
@dataclass
class PermissionRuleValue:
    tool_name: str
    rule_content: str | None = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `tool_name` | `str` | 工具名称 |
| `rule_content` | `str \| None` | 规则内容 |

---

### HookEvent

```python
HookEvent = Literal[
    "PreToolUse",           # 工具执行前调用
    "PostToolUse",          # 工具执行后调用
    "PostToolUseFailure",   # 工具执行失败时调用
    "UserPromptSubmit",     # 用户提交提示词时调用
    "Stop",                 # 停止执行时调用
    "SubagentStop",         # 子代理停止时调用
    "PreCompact",           # 消息压缩前调用
    "Notification",         # 通知事件
    "SubagentStart",        # 子代理启动时调用
    "PermissionRequest",    # 需要权限决策时调用
]
```

> **注意**：TypeScript SDK 支持额外的事件，Python 中尚不可用：`SessionStart`、`SessionEnd`、`Setup`、`TeammateIdle`、`TaskCompleted`、`ConfigChange`、`WorktreeCreate`、`WorktreeRemove`、`PostToolBatch`、`MessageDisplay`。

| Hook 事件 | Python SDK | TypeScript SDK | 触发条件 | 示例用例 |
|-----------|-----------|---------------|---------|---------|
| `PreToolUse` | ✅ | ✅ | 工具调用请求（可阻止或修改） | 阻止危险的 shell 命令 |
| `PostToolUse` | ✅ | ✅ | 工具执行结果 | 将所有文件更改记录到审计跟踪 |
| `PostToolUseFailure` | ✅ | ✅ | 工具执行失败 | 处理或记录工具错误 |
| `PostToolBatch` | ❌ | ✅ | 一批工具调用全部解决 | 为整批注入约定 |
| `UserPromptSubmit` | ✅ | ✅ | 用户提示词提交 | 向提示词注入额外上下文 |
| `MessageDisplay` | ❌ | ✅ | 助手消息文本完成 | 在不改变转录的情况下编辑显示文本 |
| `Stop` | ✅ | ✅ | 代理执行停止 | 退出前保存会话状态 |
| `SubagentStart` | ✅ | ✅ | 子代理初始化 | 跟踪并行任务生成 |
| `SubagentStop` | ✅ | ✅ | 子代理完成 | 聚合并行任务结果 |
| `PreCompact` | ✅ | ✅ | 对话压缩请求 | 摘要前存档完整转录 |
| `PermissionRequest` | ✅ | ✅ | 将显示权限对话框 | 自定义权限处理 |
| `SessionStart` | ❌ | ✅ | 会话初始化 | 初始化日志和遥测 |
| `SessionEnd` | ❌ | ✅ | 会话终止 | 清理临时资源 |
| `Notification` | ✅ | ✅ | 代理状态消息 | 向 Slack 或 PagerDuty 发送状态更新 |
| `Setup` | ❌ | ✅ | 会话设置/维护 | 运行初始化任务 |
| `TeammateIdle` | ❌ | ✅ | 队友变为空闲 | 重新分配工作或通知 |
| `TaskCompleted` | ❌ | ✅ | 后台任务完成 | 聚合并行任务结果 |
| `ConfigChange` | ❌ | ✅ | 配置文件更改 | 动态重新加载设置 |
| `WorktreeCreate` | ❌ | ✅ | Git 工作树创建 | 跟踪隔离工作区 |
| `WorktreeRemove` | ❌ | ✅ | Git 工作树移除 | 清理工作区资源 |

---

### HookMatcher

```python
@dataclass
class HookMatcher:
    matcher: str | None = None           # 工具名称或模式（例如 "Bash"、"Write|Edit"）
    hooks: list[HookCallback] = field(default_factory=list)  # 要执行的回调
    timeout: float | None = None         # 超时时间（秒），默认 60
```

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `matcher` | `str \| None` | `None` | 工具名称或模式匹配（例如 `"Bash"`、`"Write\|Edit"`）。`*`、空字符串或省略匹配所有事件。 |
| `hooks` | `list[HookCallback]` | `[]` | 匹配时要执行的回调函数列表 |
| `timeout` | `float \| None` | `None` | 超时时间（秒），默认 60 秒 |

**匹配器规则**：
- 仅包含字母、数字、`_`、`-`、空格、`,` 和 `|` 的匹配器作为精确字符串比较，使用 `|` 或 `,` 分隔替代项
- 包含任何其他字符的匹配器作为未锚定的正则表达式评估
- 使用 `^` 和 `$` 包裹正则表达式以进行完整字符串匹配
- MCP 工具使用模式 `mcp__<server>__<action>`

---

### HookCallback

```python
HookCallback = Callable[[HookInput, str | None, HookContext], Awaitable[HookJSONOutput]]
```

**参数**：
- `input`：强类型 hook 输入，基于 `hook_event_name` 的判别联合（见 `HookInput`）
- `tool_use_id`：可选的工具使用标识符（用于工具相关 hooks）
- `context`：带有额外信息的 hook 上下文

**返回**：`HookJSONOutput`，包含 `decision`、`systemMessage` 和 `hookSpecificOutput`。

---

### HookContext

```python
class HookContext(TypedDict):
    signal: Any | None  # 保留用于未来的中止信号支持
```

---

### HookInput

```python
HookInput = (
    PreToolUseHookInput
    | PostToolUseHookInput
    | PostToolUseFailureHookInput
    | UserPromptSubmitHookInput
    | StopHookInput
    | SubagentStopHookInput
    | PreCompactHookInput
    | NotificationHookInput
    | SubagentStartHookInput
    | PermissionRequestHookInput
)
```

#### BaseHookInput（所有 Hook 输入的基类）

```python
class BaseHookInput(TypedDict):
    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `session_id` | `str` | 会话标识符 |
| `transcript_path` | `str` | 转录文件路径 |
| `cwd` | `str` | 当前工作目录 |
| `permission_mode` | `str` | 权限模式（可选） |

#### PreToolUseHookInput

```python
class PreToolUseHookInput(BaseHookInput):
    hook_event_name: Literal["PreToolUse"]
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    agent_id: NotRequired[str]
    agent_type: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["PreToolUse"]` | 事件名称 |
| `tool_name` | `str` | 工具名称 |
| `tool_input` | `dict[str, Any]` | 工具输入参数 |
| `tool_use_id` | `str` | 工具使用 ID |
| `agent_id` | `str` | 代理 ID（在子代理中触发时） |
| `agent_type` | `str` | 代理类型（在子代理中触发时） |

#### PostToolUseHookInput

```python
class PostToolUseHookInput(BaseHookInput):
    hook_event_name: Literal["PostToolUse"]
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: Any
    tool_use_id: str
    agent_id: NotRequired[str]
    agent_type: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["PostToolUse"]` | 事件名称 |
| `tool_name` | `str` | 工具名称 |
| `tool_input` | `dict[str, Any]` | 工具输入参数 |
| `tool_response` | `Any` | 工具响应 |
| `tool_use_id` | `str` | 工具使用 ID |
| `agent_id` | `str` | 代理 ID |
| `agent_type` | `str` | 代理类型 |

#### PostToolUseFailureHookInput

```python
class PostToolUseFailureHookInput(BaseHookInput):
    hook_event_name: Literal["PostToolUseFailure"]
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    error: str
    is_interrupt: NotRequired[bool]
    agent_id: NotRequired[str]
    agent_type: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["PostToolUseFailure"]` | 事件名称 |
| `tool_name` | `str` | 工具名称 |
| `tool_input` | `dict[str, Any]` | 工具输入参数 |
| `tool_use_id` | `str` | 工具使用 ID |
| `error` | `str` | 错误信息 |
| `is_interrupt` | `bool` | 是否为中断 |
| `agent_id` | `str` | 代理 ID |
| `agent_type` | `str` | 代理类型 |

#### UserPromptSubmitHookInput

```python
class UserPromptSubmitHookInput(BaseHookInput):
    hook_event_name: Literal["UserPromptSubmit"]
    prompt: str
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["UserPromptSubmit"]` | 事件名称 |
| `prompt` | `str` | 用户提交的提示词 |

#### StopHookInput

```python
class StopHookInput(BaseHookInput):
    hook_event_name: Literal["Stop"]
    stop_hook_active: bool
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["Stop"]` | 事件名称 |
| `stop_hook_active` | `bool` | stop hook 是否活跃 |

#### SubagentStopHookInput

```python
class SubagentStopHookInput(BaseHookInput):
    hook_event_name: Literal["SubagentStop"]
    stop_hook_active: bool
    agent_id: str
    agent_transcript_path: str
    agent_type: str
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["SubagentStop"]` | 事件名称 |
| `stop_hook_active` | `bool` | stop hook 是否活跃 |
| `agent_id` | `str` | 代理 ID |
| `agent_transcript_path` | `str` | 代理转录文件路径 |
| `agent_type` | `str` | 代理类型 |

#### PreCompactHookInput

```python
class PreCompactHookInput(BaseHookInput):
    hook_event_name: Literal["PreCompact"]
    trigger: Literal["manual", "auto"]
    custom_instructions: str | None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["PreCompact"]` | 事件名称 |
| `trigger` | `Literal["manual", "auto"]` | 触发方式 |
| `custom_instructions` | `str \| None` | 自定义指令 |

#### NotificationHookInput

```python
class NotificationHookInput(BaseHookInput):
    hook_event_name: Literal["Notification"]
    message: str
    title: NotRequired[str]
    notification_type: str
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["Notification"]` | 事件名称 |
| `message` | `str` | 通知消息 |
| `title` | `str` | 通知标题（可选） |
| `notification_type` | `str` | 通知类型 |

#### SubagentStartHookInput

```python
class SubagentStartHookInput(BaseHookInput):
    hook_event_name: Literal["SubagentStart"]
    agent_id: str
    agent_type: str
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["SubagentStart"]` | 事件名称 |
| `agent_id` | `str` | 代理 ID |
| `agent_type` | `str` | 代理类型 |

#### PermissionRequestHookInput

```python
class PermissionRequestHookInput(BaseHookInput):
    hook_event_name: Literal["PermissionRequest"]
    tool_name: str
    tool_input: dict[str, Any]
    permission_suggestions: NotRequired[list[Any]]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hook_event_name` | `Literal["PermissionRequest"]` | 事件名称 |
| `tool_name` | `str` | 工具名称 |
| `tool_input` | `dict[str, Any]` | 工具输入参数 |
| `permission_suggestions` | `list[Any]` | 权限建议列表 |

---

### HookJSONOutput

```python
HookJSONOutput = AsyncHookJSONOutput | SyncHookJSONOutput
```

#### SyncHookJSONOutput

```python
class SyncHookJSONOutput(TypedDict):
    # 控制字段
    continue_: NotRequired[bool]          # 是否继续执行（默认 True）
    suppressOutput: NotRequired[bool]     # 从转录中隐藏 stdout
    stopReason: NotRequired[str]          # continue 为 False 时的消息

    # 决策字段
    decision: NotRequired[Literal["block"]]
    systemMessage: NotRequired[str]       # 给用户的警告消息
    reason: NotRequired[str]              # 给 Claude 的反馈

    # Hook 特定输出
    hookSpecificOutput: NotRequired[HookSpecificOutput]
```

> **注意**：在 Python 代码中使用 `continue_`（带下划线），发送到 CLI 时自动转换为 `continue`。

| 字段 | 类型 | 描述 |
|------|------|------|
| `continue_` | `bool` | 是否继续执行（默认 `True`） |
| `suppressOutput` | `bool` | 是否从转录中隐藏 stdout |
| `stopReason` | `str` | 当 `continue` 为 `False` 时的停止原因 |
| `decision` | `Literal["block"]` | 阻止决策 |
| `systemMessage` | `str` | 显示给用户的系统消息 |
| `reason` | `str` | 给 Claude 的反馈原因 |
| `hookSpecificOutput` | `HookSpecificOutput` | 特定于 hook 类型的输出 |

#### AsyncHookJSONOutput

```python
class AsyncHookJSONOutput(TypedDict):
    async_: bool  # 必须为 True（Python 中使用 async_ 避免保留关键字冲突）
    asyncTimeout: NotRequired[int]  # 可选超时（毫秒）
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `async_` | `bool` | 必须为 `True`，表示异步模式 |
| `asyncTimeout` | `int` | 可选超时时间（毫秒） |

> **注意**：异步输出不能阻止、修改或向操作注入上下文，因为代理已经继续运行。仅用于副作用，如日志记录、指标或通知。

---

### HookSpecificOutput

```python
HookSpecificOutput = (
    PreToolUseHookSpecificOutput
    | PostToolUseHookSpecificOutput
    | PostToolUseFailureHookSpecificOutput
    | UserPromptSubmitHookSpecificOutput
    | NotificationHookSpecificOutput
    | SubagentStartHookSpecificOutput
    | PermissionRequestHookSpecificOutput
)
```

#### PreToolUseHookSpecificOutput

```python
class PreToolUseHookSpecificOutput(TypedDict):
    hookEventName: Literal["PreToolUse"]
    permissionDecision: NotRequired[Literal["allow", "deny", "ask", "defer"]]
    permissionDecisionReason: NotRequired[str]
    updatedInput: NotRequired[dict[str, Any]]
    additionalContext: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hookEventName` | `Literal["PreToolUse"]` | 事件名称 |
| `permissionDecision` | `Literal["allow", "deny", "ask", "defer"]` | 权限决策 |
| `permissionDecisionReason` | `str` | 权限决策原因 |
| `updatedInput` | `dict[str, Any]` | 更新后的工具输入 |
| `additionalContext` | `str` | 额外上下文 |

**权限决策优先级**：`deny` > `defer` > `ask` > `allow`

#### PostToolUseHookSpecificOutput

```python
class PostToolUseHookSpecificOutput(TypedDict):
    hookEventName: Literal["PostToolUse"]
    additionalContext: NotRequired[str]
    updatedToolOutput: NotRequired[Any]
    updatedMCPToolOutput: NotRequired[Any]  # 已弃用
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `hookEventName` | `Literal["PostToolUse"]` | 事件名称 |
| `additionalContext` | `str` | 追加到工具结果的额外上下文 |
| `updatedToolOutput` | `Any` | 替换工具输出（Claude 看到此内容） |
| `updatedMCPToolOutput` | `Any` | **已弃用** — 仅替换 MCP 工具输出 |

#### PostToolUseFailureHookSpecificOutput

```python
class PostToolUseFailureHookSpecificOutput(TypedDict):
    hookEventName: Literal["PostToolUseFailure"]
    additionalContext: NotRequired[str]
```

#### UserPromptSubmitHookSpecificOutput

```python
class UserPromptSubmitHookSpecificOutput(TypedDict):
    hookEventName: Literal["UserPromptSubmit"]
    additionalContext: NotRequired[str]
```

#### NotificationHookSpecificOutput

```python
class NotificationHookSpecificOutput(TypedDict):
    hookEventName: Literal["Notification"]
    additionalContext: NotRequired[str]
```

#### SubagentStartHookSpecificOutput

```python
class SubagentStartHookSpecificOutput(TypedDict):
    hookEventName: Literal["SubagentStart"]
    additionalContext: NotRequired[str]
```

#### PermissionRequestHookSpecificOutput

```python
class PermissionRequestHookSpecificOutput(TypedDict):
    hookEventName: Literal["PermissionRequest"]
    decision: dict[str, Any]
```

---

### SessionStore

`SessionStore` 是一个 Protocol，用于将会话记录镜像到外部后端（如 S3、Redis 或数据库），以便任何主机都可以恢复会话。

```python
class SessionStore(Protocol):
    # 必需方法
    async def append(
        self, key: SessionKey, entries: list[SessionStoreEntry]
    ) -> None: ...
    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None: ...

    # 可选方法 — 省略或引发 NotImplementedError
    async def list_sessions(
        self, project_key: str
    ) -> list[SessionStoreListEntry]: ...
    async def delete(self, key: SessionKey) -> None: ...
    async def list_subkeys(self, key: SessionListSubkeysKey) -> list[str]: ...
```

| 方法 | 必需 | 调用时机 |
|------|------|---------|
| `append` | 是 | 每批记录条目本地写入后。条目是 JSON 安全的对象，本地 JSONL 中每行一个。 |
| `load` | 是 | 在子进程生成之前一次，当设置 `resume` 时。如果会话未知，返回 `null`。 |
| `list_sessions` | 否 | 由 `listSessions()` 和 `query()`/`startup()` 与 `continue: True` 调用。如果未定义，这些调用会抛出异常。 |
| `delete` | 否 | 由 `deleteSession()` 调用。删除主密钥（无 `subpath`）必须级联到该会话的所有子密钥。如果未定义，删除是无操作的。 |
| `list_subkeys` | 否 | 在恢复期间，发现子代理记录。如果未定义，仅恢复主记录。 |

**重要说明**：
- 存储是**镜像**，不是替代品。Claude Code 子进程始终首先写入本地磁盘；SDK 然后将每批转发到 `append()`。
- 镜像写入是**尽力而为**的。如果 `append()` 失败，错误会被记录，查询继续，不会丢失本地数据。
- SDK 永远不会自行从存储中删除。保留是适配器的责任。
- `sessionStore` 不能与 `persistSession: False` 或 `enableFileCheckpointing` 结合使用。

---

### SessionStoreFlushMode

```python
SessionStoreFlushMode = Literal["batched", "eager"]
```

| 值 | 描述 |
|----|------|
| `"batched"` | 每轮刷新一次或缓冲区满时刷新 |
| `"eager"` | 每帧后触发后台刷新 |

---

### SessionKey

```python
class SessionKey(TypedDict):
    project_key: str
    session_id: str
    subpath: NotRequired[str]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `project_key` | `str` | 工作目录的稳定的、文件系统安全的编码 |
| `session_id` | `str` | 会话 UUID |
| `subpath` | `str` | 子代理记录或边车文件的子路径（可选） |

---

### Message 类型

```python
Message = (
    UserMessage
    | AssistantMessage
    | SystemMessage
    | ResultMessage
    | StreamEvent
    | RateLimitEvent
)
```

#### UserMessage

```python
@dataclass
class UserMessage:
    content: str | list[ContentBlock]
    uuid: str | None = None
    parent_tool_use_id: str | None = None
    tool_use_result: dict[str, Any] | None = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `content` | `str \| list[ContentBlock]` | 用户消息内容 |
| `uuid` | `str \| None` | 唯一标识符 |
| `parent_tool_use_id` | `str \| None` | 父工具使用 ID |
| `tool_use_result` | `dict[str, Any] \| None` | 工具使用结果 |

#### AssistantMessage

```python
@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    model: str
    parent_tool_use_id: str | None = None
    error: AssistantMessageError | None = None
    usage: dict[str, Any] | None = None
    message_id: str | None = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `content` | `list[ContentBlock]` | 助手消息内容块列表 |
| `model` | `str` | 使用的模型 |
| `parent_tool_use_id` | `str \| None` | 父工具使用 ID |
| `error` | `AssistantMessageError \| None` | 错误信息 |
| `usage` | `dict[str, Any] \| None` | 令牌使用情况 |
| `message_id` | `str \| None` | 消息 ID |

**AssistantMessageError**：
```python
AssistantMessageError = Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "max_output_tokens",
    "unknown",
]
```

#### SystemMessage

```python
@dataclass
class SystemMessage:
    subtype: str
    data: dict[str, Any]
```

#### ResultMessage

```python
@dataclass
class ResultMessage:
    subtype: str  # "success" | "error_during_execution" | "error_max_turns" | "error_max_budget_usd" | "error_max_structured_output_retries"
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    stop_reason: str | None = None
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None
    structured_output: Any = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[Any] | None = None
    deferred_tool_use: DeferredToolUse | None = None
    errors: list[str] | None = None
    api_error_status: int | None = None
    uuid: str | None = None
```
**`subtype` 取值**：`"success"`、`"error_during_execution"`、`"error_max_turns"`、`"error_max_budget_usd"`、`"error_max_structured_output_retries"`。

**错误诊断字段**：

| 字段 | 说明 |
|------|------|
| `is_error` | 对话以错误状态结束时为 `True`。在 `error_*` 子类型上始终为 `True`。在 `subtype="success"` 上，如果最终模型请求失败，也为 `True` |
| `api_error_status` | 终止 API 错误的 HTTP 状态码。仅在 `subtype="success"` 时填充，非错误轮次为 `None` |
| `result` | 最终助手消息的文本。仅在 `subtype="success"` 时填充，`error_*` 子类型上为 `None` |
| `errors` | 循环级错误字符串列表（如 max turns 消息）。仅在 `error_*` 子类型上填充 |

**`usage` 字典键**：

| 键 | 类型 | 描述 |
|----|------|------|
| `input_tokens` | `int` | 总输入令牌数 |
| `output_tokens` | `int` | 总输出令牌数 |
| `cache_creation_input_tokens` | `int` | 新缓存条目的令牌数 |
| `cache_read_input_tokens` | `int` | 来自现有缓存条目的令牌数 |

**`model_usage` 字典键（camelCase）**：

| 键 | 类型 | 描述 |
|----|------|------|
| `inputTokens` | `int` | 此模型的输入令牌数 |
| `outputTokens` | `int` | 此模型的输出令牌数 |
| `cacheReadInputTokens` | `int` | 缓存读取令牌数 |
| `cacheCreationInputTokens` | `int` | 缓存创建令牌数 |
| `webSearchRequests` | `int` | Web 搜索请求数 |
| `costUSD` | `float` | 估算成本（USD） |
| `contextWindow` | `int` | 上下文窗口大小 |
| `maxOutputTokens` | `int` | 最大输出令牌限制 |

**DeferredToolUse**（当 PreToolUse hook 返回 `permissionDecision: "defer"` 时设置）：
```python
# 内联类型
{
    "id": str,      # 工具调用的唯一标识符
    "name": str,    # 延迟工具的名称
    "input": dict   # 待处理工具的输入参数
}
```

#### StreamEvent

```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]  # 原始 Claude API 流事件
    parent_tool_use_id: str | None = None
```

仅在 `include_partial_messages=True` 时接收。

#### RateLimitEvent

```python
@dataclass
class RateLimitEvent:
    rate_limit_info: RateLimitInfo
    uuid: str
    session_id: str
```

#### RateLimitInfo

```python
RateLimitStatus = Literal["allowed", "allowed_warning", "rejected"]
RateLimitType = Literal[
    "five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "overage"
]

@dataclass
class RateLimitInfo:
    status: RateLimitStatus
    resets_at: int | None = None
    rate_limit_type: RateLimitType | None = None
    utilization: float | None = None
    overage_status: RateLimitStatus | None = None
    overage_resets_at: int | None = None
    overage_disabled_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
```

#### TaskStartedMessage（继承 SystemMessage）

```python
@dataclass
class TaskStartedMessage(SystemMessage):
    task_id: str
    description: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    task_type: str | None = None  # "local_bash" | "local_agent" | "remote_agent"
```

#### TaskProgressMessage（继承 SystemMessage）

```python
@dataclass
class TaskProgressMessage(SystemMessage):
    task_id: str
    description: str
    usage: TaskUsage
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    last_tool_name: str | None = None
```

#### TaskNotificationMessage（继承 SystemMessage）

```python
@dataclass
class TaskNotificationMessage(SystemMessage):
    task_id: str
    status: TaskNotificationStatus  # "completed" | "failed" | "stopped"
    output_file: str
    summary: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    usage: TaskUsage | None = None
```

#### TaskUsage

```python
class TaskUsage(TypedDict):
    total_tokens: int
    tool_uses: int
    duration_ms: int
```

---

### ContentBlock 类型

```python
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock
```

#### TextBlock

```python
@dataclass
class TextBlock:
    text: str
```

#### ThinkingBlock

```python
@dataclass
class ThinkingBlock:
    thinking: str
    signature: str
```

#### ToolUseBlock

```python
@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
```

#### ToolResultBlock

```python
@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict[str, Any]] | None = None
    is_error: bool | None = None
```

---

### 错误类型

#### ClaudeSDKError

```python
class ClaudeSDKError(Exception):
    """Claude SDK 的基础错误类。"""
```

#### CLINotFoundError

```python
class CLINotFoundError(CLIConnectionError):
    def __init__(self, message: str = "Claude Code not found", cli_path: str | None = None):
        ...
```

#### CLIConnectionError

```python
class CLIConnectionError(ClaudeSDKError):
    """无法连接到 Claude Code。"""
```

#### ProcessError

```python
class ProcessError(ClaudeSDKError):
    def __init__(self, message: str, exit_code: int | None = None, stderr: str | None = None):
        self.exit_code = exit_code
        self.stderr = stderr
```

#### CLIJSONDecodeError

```python
class CLIJSONDecodeError(ClaudeSDKError):
    def __init__(self, line: str, original_error: Exception):
        self.line = line
        self.original_error = original_error
```

---

### SdkMcpTool

```python
@dataclass
class SdkMcpTool(Generic[T]):
    name: str
    description: str
    input_schema: type[T] | dict[str, Any]
    handler: Callable[[T], Awaitable[dict[str, Any]]]
    annotations: ToolAnnotations | None = None
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 工具名称 |
| `description` | `str` | 工具描述 |
| `input_schema` | `type[T] \| dict[str, Any]` | 输入模式 |
| `handler` | `Callable[[T], Awaitable[dict[str, Any]]]` | 处理函数 |
| `annotations` | `ToolAnnotations \| None` | 工具注解 |

#### ToolAnnotations

从 `mcp.types` 重新导出。所有字段均为可选提示。

```python
class ToolAnnotations:
    title: str | None = None
    readOnlyHint: bool | None = False
    destructiveHint: bool | None = True
    idempotentHint: bool | None = False
    openWorldHint: bool | None = True
```

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `title` | `str \| None` | `None` | 人类可读的标题 |
| `readOnlyHint` | `bool \| None` | `False` | 若为 `True`，工具不会修改其环境 |
| `destructiveHint` | `bool \| None` | `True` | 若为 `True`，工具可能执行破坏性更新（仅在 `readOnlyHint` 为 `False` 时有意义） |
| `idempotentHint` | `bool \| None` | `False` | 若为 `True`，相同参数重复调用无额外效果（仅在 `readOnlyHint` 为 `False` 时有意义） |
| `openWorldHint` | `bool \| None` | `True` | 若为 `True`，工具与外部实体交互（如 Web 搜索）。若为 `False`，工具域是封闭的（如 memory 工具） |

**示例**：
```python
from claude_agent_sdk import tool, ToolAnnotations
from typing import Any

@tool(
    "search",
    "Search the web",
    {"query": str},
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def search(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Results for: {args['query']}"}]}
```

---

### Transport

```python
class Transport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def write(self, data: str) -> None: ...
    @abstractmethod
    def read_messages(self) -> AsyncIterator[dict[str, Any]]: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    def is_ready(self) -> bool: ...
    @abstractmethod
    async def end_input(self) -> None: ...
```

| 方法 | 描述 |
|------|------|
| `connect()` | 连接传输层并准备通信 |
| `write(data)` | 写入原始数据（JSON + 换行符）到传输层 |
| `read_messages()` | 异步迭代器，产出已解析的 JSON 消息 |
| `close()` | 关闭连接并清理资源 |
| `is_ready()` | 如果传输层可以发送和接收则返回 `True` |
| `end_input()` | 关闭输入流（例如，关闭子进程传输的 stdin） |

> **⚠️ 警告**：这是低级内部 API，接口可能在未来版本中变更。自定义实现必须适配任何接口变更。

---

### McpStatusResponse / McpServerStatus

用于查询 MCP 服务器状态的返回类型。

#### McpStatusResponse

```python
class McpStatusResponse(TypedDict):
    mcpServers: list[McpServerStatus]
```

**`McpServerStatus`**：

```python
class McpServerStatus(TypedDict):
    name: str
    status: McpServerConnectionStatus  # "connected" | "failed" | "needs-auth" | "pending" | "disabled"
    serverInfo: NotRequired[McpServerInfo]
    error: NotRequired[str]
    config: NotRequired[McpServerStatusConfig]
    scope: NotRequired[str]
    tools: NotRequired[list[McpToolInfo]]
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 服务器名称 |
| `status` | `str` | `"connected"`、`"failed"`、`"needs-auth"`、`"pending"` 或 `"disabled"` 之一 |
| `serverInfo` | `dict`（可选） | 服务器名称和版本 (`{"name": str, "version": str}`) |
| `error` | `str`（可选） | 服务器连接失败时的错误消息 |
| `config` | `McpServerStatusConfig`（可选） | 服务器配置 |
| `scope` | `str`（可选） | 配置作用域 |
| `tools` | `list`（可选） | 该服务器提供的工具列表，每个工具包含 `name`、`description` 和 `annotations` 字段 |

**`McpServerStatusConfig`**：可序列化的服务器配置联合类型，包含：

```python
McpServerStatusConfig = (
    McpStdioServerConfig
    | McpSSEServerConfig
    | McpHttpServerConfig
    | McpSdkServerConfigStatus
    | McpClaudeAIProxyServerConfig
)
```

其中 `McpSdkServerConfigStatus` 是 `McpSdkServerConfig` 的可序列化形式，仅保留 `type`（`"sdk"`）和 `name`（`str`）字段，省略进程内 `instance`。`McpClaudeAIProxyServerConfig` 包含 `type`（`"claudeai-proxy"`）、`url`（`str`）和 `id`（`str`）字段。

---

### ClaudeSDKClient 类

`ClaudeSDKClient` 是 SDK 的主要客户端类，管理连接和交互。

```python
class ClaudeSDKClient:
    def __init__(
        self,
        options: ClaudeAgentOptions | None = None,
        transport: Transport | None = None
    )
    async def connect(
        self, prompt: str | AsyncIterable[dict] | None = None
    ) -> None
    async def query(
        self, prompt: str | AsyncIterable[dict], session_id: str = "default"
    ) -> None
    async def receive_messages(self) -> AsyncIterator[Message]
    async def receive_response(self) -> AsyncIterator[Message]
    async def interrupt(self) -> None
    async def set_permission_mode(self, mode: str) -> None
    async def set_model(self, model: str | None = None) -> None
    async def rewind_files(self, user_message_id: str) -> None
    async def get_mcp_status(self) -> McpStatusResponse
    async def reconnect_mcp_server(self, server_name: str) -> None
    async def toggle_mcp_server(self, server_name: str, enabled: bool) -> None
    async def stop_task(self, task_id: str) -> None
    async def get_server_info(self) -> dict[str, Any] | None
    async def disconnect(self) -> None
```

#### 方法详解

| 方法 | 描述 |
|------|------|
| `__init__(options, transport)` | 使用可选配置初始化客户端 |
| `connect(prompt)` | 连接到 Claude，可选传入初始提示词或消息流 |
| `query(prompt, session_id)` | 以流式模式发送新请求 |
| `receive_messages()` | 以异步迭代器方式接收 Claude 的所有消息 |
| `receive_response()` | 接收消息直至并包含 `ResultMessage` |
| `interrupt()` | 发送中断信号（仅在流式模式下有效） |
| `set_permission_mode(mode)` | 更改当前会话的权限模式 |
| `set_model(model)` | 更改当前会话的模型。传入 `None` 重置为默认值 |
| `rewind_files(user_message_id)` | 将文件恢复到指定用户消息时的状态。需要 `enable_file_checkpointing=True` |
| `get_mcp_status()` | 获取所有已配置 MCP 服务器的状态，返回 `McpStatusResponse` |
| `reconnect_mcp_server(server_name)` | 重试连接失败或断开连接的 MCP 服务器 |
| `toggle_mcp_server(server_name, enabled)` | 启用或禁用会话中的 MCP 服务器。禁用会移除其工具 |
| `stop_task(task_id)` | 停止正在运行的后台任务。随后会在消息流中出现状态为 `"stopped"` 的 `TaskNotificationMessage` |
| `get_server_info()` | 获取服务器信息，包括会话 ID 和功能 |
| `disconnect()` | 断开与 Claude 的连接 |

#### 上下文管理器支持

```python
async with ClaudeSDKClient() as client:
    await client.query("Hello Claude")
    async for message in client.receive_response():
        print(message)
```

> **⚠️ 重要**：迭代消息时，避免使用 `break` 提前退出，这可能导致 asyncio 清理问题。应让迭代自然完成，或使用标志跟踪是否已找到所需内容。

---

### query() 函数

便捷函数，无需显式管理 `ClaudeSDKClient` 即可发送查询。

```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None
) -> AsyncIterator[Message]
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `prompt` | `str \| AsyncIterable[dict[str, Any]]` | 要发送的提示词（仅关键字参数） |
| `options` | `ClaudeAgentOptions \| None` | 可选配置 |
| `transport` | `Transport \| None` | 可选自定义传输层 |

---

### tool() 装饰器

将异步函数转换为 SDK MCP 工具，可注册到 `create_sdk_mcp_server()`。

```python
def tool(
    name: str,
    description: str,
    input_schema: type | dict[str, Any],
    annotations: ToolAnnotations | None = None
) -> Callable[[Callable[[Any], Awaitable[dict[str, Any]]]], SdkMcpTool[Any]]
```

**`input_schema` 两种用法**：

1. **简单类型映射（推荐）**：`{"text": str, "count": int, "enabled": bool}`
2. **JSON Schema 格式**（用于复杂验证）：`{"type": "object", "properties": {...}, "required": [...]}`

**示例**：

```python
from claude_agent_sdk import tool
from typing import Any

# 方式一：简单类型映射
@tool("greet", "Greet a user", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}

# 方式二：JSON Schema 格式
@tool("search", "Search with filters", {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "default": 10},
    },
    "required": ["query"],
})
async def search(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Results for: {args['query']}"}]}
```

---

### create_sdk_mcp_server()

将多个 SDK 工具打包为一个进程内 MCP 服务器。

```python
def create_sdk_mcp_server(
    name: str,
    version: str = "1.0.0",
    tools: list[SdkMcpTool[Any]] | None = None
) -> McpSdkServerConfig
```

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | — | 服务器名称 |
| `version` | `str` | `"1.0.0"` | 服务器版本 |
| `tools` | `list[SdkMcpTool[Any]] \| None` | `None` | 要注册的工具列表 |

返回 `McpSdkServerConfig`，可直接传入 `ClaudeAgentOptions.mcp_servers`。

---

### Session 类型与工具函数

#### SDKSessionInfo

```python
@dataclass
class SDKSessionInfo:
    session_id: str
    summary: str
    last_modified: int
    file_size: int | None
    custom_title: str | None
    first_prompt: str | None
    git_branch: str | None
    cwd: str | None
    tag: str | None
    created_at: int | None
```

| 属性 | 类型 | 描述 |
|------|------|------|
| `session_id` | `str` | 唯一会话标识符 |
| `summary` | `str` | 显示标题：自定义标题、自动生成的摘要或首个提示词 |
| `last_modified` | `int` | 最后修改时间（毫秒时间戳） |
| `file_size` | `int \| None` | 会话文件大小（字节），远程存储后端为 `None` |
| `custom_title` | `str \| None` | 用户设置的会话标题 |
| `first_prompt` | `str \| None` | 第一个有意义的用户提示词 |
| `git_branch` | `str \| None` | 会话结束时的 Git 分支 |
| `cwd` | `str \| None` | 工作目录 |
| `tag` | `str \| None` | 用户设置的会话标签 |
| `created_at` | `int \| None` | 创建时间（毫秒时间戳） |

#### SessionMessage

```python
@dataclass
class SessionMessage:
    type: Literal["user", "assistant"]
    uuid: str
    session_id: str
    message: Any
    parent_tool_use_id: None
```

| 属性 | 类型 | 描述 |
|------|------|------|
| `type` | `Literal["user", "assistant"]` | 消息角色 |
| `uuid` | `str` | 唯一消息标识符 |
| `session_id` | `str` | 会话标识符 |
| `message` | `Any` | 原始消息内容 |
| `parent_tool_use_id` | `None` | 保留供将来使用 |

#### Session 工具函数

以下函数用于管理会话，均为同步函数，立即返回。

##### `list_sessions()`

列出历史会话及其元数据。

```python
def list_sessions(
    directory: str | None = None,
    limit: int | None = None,
    include_worktrees: bool = True
) -> list[SDKSessionInfo]
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `directory` | `str \| None` | 会话目录路径，默认使用标准路径 |
| `limit` | `int \| None` | 返回的最大会话数 |
| `include_worktrees` | `bool` | 是否包含工作树会话 |

##### `get_session_messages()`

获取指定会话的消息列表。

```python
def get_session_messages(
    session_id: str,
    directory: str | None = None,
    limit: int | None = None,
    offset: int = 0
) -> list[SessionMessage]
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `session_id` | `str` | 会话 ID |
| `directory` | `str \| None` | 会话目录路径 |
| `limit` | `int \| None` | 返回的最大消息数 |
| `offset` | `int` | 分页偏移量 |

##### `get_session_info()`

获取单个会话的元数据。

```python
def get_session_info(
    session_id: str,
    directory: str | None = None,
) -> SDKSessionInfo | None
```

如果会话不存在，返回 `None`。

##### `rename_session()`

通过追加自定义标题条目来重命名会话。

```python
def rename_session(
    session_id: str,
    title: str,
    directory: str | None = None,
) -> None
```

##### `tag_session()`

为会话添加标签。传入 `None` 清除标签。

```python
def tag_session(
    session_id: str,
    tag: str | None,
    directory: str | None = None,
) -> None
```

---

### 基础用法

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    options = ClaudeAgentOptions(
        system_prompt="You are an expert Python developer",
        permission_mode="acceptEdits",
        cwd="/home/user/project",
    )

    async for message in query(prompt="Create a Python web server", options=options):
        print(message)

asyncio.run(main())
```

### 自定义权限处理器

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    PermissionResultAllow, PermissionResultDeny, ToolPermissionContext,
)

async def custom_permission_handler(
    tool_name: str, input_data: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    # 阻止写入系统目录
    if tool_name == "Write" and input_data.get("file_path", "").startswith("/system/"):
        return PermissionResultDeny(message="System directory write not allowed", interrupt=True)

    # 将配置文件写入重定向到沙箱目录
    if tool_name in ["Write", "Edit"] and "config" in input_data.get("file_path", ""):
        safe_path = f"./sandbox/{input_data['file_path']}"
        return PermissionResultAllow(updated_input={**input_data, "file_path": safe_path})

    return PermissionResultAllow(updated_input=input_data)

async def main():
    options = ClaudeAgentOptions(
        can_use_tool=custom_permission_handler,
        allowed_tools=["Read", "Write", "Edit"],
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Update the system config file")
        async for message in client.receive_response():
            print(message)
```

### Setting Sources 配置

```python
# 禁用所有文件系统设置
options = ClaudeAgentOptions(setting_sources=[])

# 显式加载所有文件系统设置
options = ClaudeAgentOptions(setting_sources=["user", "project", "local"])

# 仅加载项目设置
options = ClaudeAgentOptions(setting_sources=["project"])

# CI 环境（排除本地设置，绕过权限）
options = ClaudeAgentOptions(
    setting_sources=["project"],
    permission_mode="bypassPermissions",
)

# SDK-only 模式：全部以编程方式定义
options = ClaudeAgentOptions(
    setting_sources=[],
    agents={...},
    mcp_servers={...},
    allowed_tools=["Read", "Grep", "Glob"],
)

# 加载项目设置以包含 CLAUDE.md 文件
options = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"},
    setting_sources=["project"],
    allowed_tools=["Read", "Write", "Edit"],
)
```

### 环境变量配置

```python
options = ClaudeAgentOptions(
    env={
        "API_TIMEOUT_MS": "120000",
        "CLAUDE_CODE_MAX_RETRIES": "2",
        "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS": "120000",
    },
)
```

### Thinking 配置

```python
from claude_agent_sdk import ClaudeAgentOptions, ThinkingConfigEnabled

# 字典字面量方式（推荐）
options = ClaudeAgentOptions(thinking={"type": "enabled", "budget_tokens": 20000})

# 使用带摘要显示的扩展思考
options = ClaudeAgentOptions(
    thinking={"type": "enabled", "budget_tokens": 20000, "display": "summarized"}
)

# 自适应思考
options = ClaudeAgentOptions(thinking={"type": "adaptive"})

# 禁用思考
options = ClaudeAgentOptions(thinking={"type": "disabled"})

# 使用构造函数方式
config = ThinkingConfigEnabled(type="enabled", budget_tokens=20000)
print(config["budget_tokens"])  # 20000 — 键访问，不是属性访问
```

### MCP 服务器配置

#### 基础用法

```python
options = ClaudeAgentOptions(
    mcp_servers={"calc": calculator},
    allowed_tools=["mcp__calc__add", "mcp__calc__multiply"],
)
```

#### 使用 `@tool` 装饰器定义工具

```python
from claude_agent_sdk import tool
from typing import Any

@tool("greet", "Greet a user", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}
```

#### 使用 `create_sdk_mcp_server` 创建多工具服务器

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("add", "Add two numbers", {"a": float, "b": float})
async def add(args):
    return {"content": [{"type": "text", "text": f"Sum: {args['a'] + args['b']}"}]}

@tool("multiply", "Multiply two numbers", {"a": float, "b": float})
async def multiply(args):
    return {"content": [{"type": "text", "text": f"Product: {args['a'] * args['b']}"}]}

calculator = create_sdk_mcp_server(
    name="calculator",
    version="2.0.0",
    tools=[add, multiply],
)

options = ClaudeAgentOptions(
    mcp_servers={"calc": calculator},
    allowed_tools=["mcp__calc__add", "mcp__calc__multiply"],
)
```

### 可中断任务

```python
options = ClaudeAgentOptions(allowed_tools=["Bash"], permission_mode="acceptEdits")
async with ClaudeSDKClient(options=options) as client:
    await client.query("Count from 1 to 100 slowly, using the bash sleep command")
    await asyncio.sleep(2)
    await client.interrupt()
```

### Hooks 拦截工具调用

#### 保护 .env 文件

```python
import asyncio
from claude_agent_sdk import (
    AssistantMessage, ClaudeSDKClient, ClaudeAgentOptions,
    HookMatcher, ResultMessage,
)

async def protect_env_files(input_data, tool_use_id, context):
    file_path = input_data["tool_input"].get("file_path", "")
    file_name = file_path.split("/")[-1]

    if file_name == ".env":
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify .env files",
            }
        }
    return {}

async def main():
    options = ClaudeAgentOptions(
        hooks={
            "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[protect_env_files])]
        }
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Update the database configuration")
        async for message in client.receive_response():
            if isinstance(message, (AssistantMessage, ResultMessage)):
                print(message)

asyncio.run(main())
```

#### 阻止写入 /etc 目录

```python
async def block_etc_writes(input_data, tool_use_id, context):
    file_path = input_data["tool_input"].get("file_path", "")

    if file_path.startswith("/etc"):
        return {
            "systemMessage": "Remember: system directories like /etc are protected.",
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": "Writing to /etc is not allowed",
            },
        }
    return {}
```

#### 自动批准只读工具

```python
async def auto_approve_read_only(input_data, tool_use_id, context):
    if input_data["hook_event_name"] != "PreToolUse":
        return {}

    read_only_tools = ["Read", "Glob", "Grep"]
    if input_data["tool_name"] in read_only_tools:
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "allow",
                "permissionDecisionReason": "Read-only tool auto-approved",
            }
        }
    return {}
```

#### 修改工具输入（重定向到沙箱）

```python
async def redirect_to_sandbox(input_data, tool_use_id, context):
    if input_data["hook_event_name"] != "PreToolUse":
        return {}

    if input_data["tool_name"] == "Write":
        original_path = input_data["tool_input"].get("file_path", "")
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "allow",
                "updatedInput": {
                    **input_data["tool_input"],
                    "file_path": f"/sandbox{original_path}",
                },
            }
        }
    return {}
```

#### 注册多个 Hooks

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(hooks=[authorization_check]),
            HookMatcher(hooks=[input_validator]),
            HookMatcher(hooks=[audit_logger]),
        ]
    }
)
```

#### 多工具匹配器

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            # 匹配文件修改工具
            HookMatcher(matcher="Write|Edit|Delete", hooks=[file_security_hook]),
            # 匹配所有 MCP 工具
            HookMatcher(matcher="^mcp__", hooks=[mcp_audit_hook]),
            # 匹配所有工具
            HookMatcher(hooks=[global_logger]),
        ]
    }
)
```

#### 异步 Hook

```python
async def async_hook(input_data, tool_use_id, context):
    asyncio.create_task(send_to_logging_service(input_data))
    return {"async_": True, "asyncTimeout": 30000}
```

#### 子代理跟踪

```python
async def subagent_tracker(input_data, tool_use_id, context):
    print(f"[SUBAGENT] Completed: {input_data['agent_id']}")
    print(f"  Transcript: {input_data['agent_transcript_path']}")
    return {}

options = ClaudeAgentOptions(
    hooks={"SubagentStop": [HookMatcher(hooks=[subagent_tracker])]}
)
```

#### 通知转发

```python
async def notification_handler(input_data, tool_use_id, context):
    try:
        await asyncio.to_thread(send_slack_notification, input_data.get("message", ""))
    except Exception as e:
        print(f"Failed to send notification: {e}")
    return {}

options = ClaudeAgentOptions(
    hooks={"Notification": [HookMatcher(hooks=[notification_handler])]},
)
```

### Session 持久化

#### 使用 InMemorySessionStore

```python
import asyncio
from claude_agent_sdk import (
    ClaudeAgentOptions, InMemorySessionStore, ResultMessage, query,
)

store = InMemorySessionStore()

async def main():
    session_id = None
    async for message in query(
        prompt="List the Python files under src/",
        options=ClaudeAgentOptions(session_store=store),
    ):
        if isinstance(message, ResultMessage):
            session_id = message.session_id

    # 从存储恢复
    async for message in query(
        prompt="Summarize what those files do",
        options=ClaudeAgentOptions(session_store=store, resume=session_id),
    ):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result)

asyncio.run(main())
```

#### 编写自定义 SessionStore 适配器

```python
from claude_agent_sdk import SessionStore, SessionKey

class MyRedisStore:
    """自定义 Redis SessionStore 实现"""

    async def append(self, key: SessionKey, entries: list) -> None:
        # 将条目持久化到 Redis
        pass

    async def load(self, key: SessionKey) -> list | None:
        # 从 Redis 加载条目
        pass

    async def list_sessions(self, project_key: str) -> list:
        # 列出所有会话
        pass

    async def delete(self, key: SessionKey) -> None:
        # 删除会话
        pass

    async def list_subkeys(self, key) -> list[str]:
        # 列出子代理记录
        pass
```

#### 验证 SessionStore 适配器

```python
import pytest
from claude_agent_sdk.testing import run_session_store_conformance

@pytest.mark.asyncio
async def test_my_store_conformance():
    await run_session_store_conformance(MyRedisStore)
```

---

## Env 环境变量参考

以下环境变量可以通过 `ClaudeAgentOptions.env` 字典配置：

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `API_TIMEOUT_MS` | 每个请求的超时时间（毫秒），适用于主循环和所有子代理 | `600000`（10 分钟） |
| `CLAUDE_CODE_MAX_RETRIES` | API 最大重试次数。最坏情况 wall time 为 `API_TIMEOUT_MS × (CLAUDE_CODE_MAX_RETRIES + 1)` 加上退避时间 | `10`，上限 `15` |
| `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS` | 通过 `run_in_background` 启动的子代理的停滞监控超时。每次流事件重置计时器；超时后中止子代理、标记任务失败、向父代理呈现带部分结果的错误。不适用于同步子代理 | `600000` |
| `CLAUDE_ENABLE_STREAM_WATCHDOG` | 设为 `0` 禁用流看门狗；当响应头到达但响应体停止流式传输时中止请求。对所有 provider 默认启用 | 已启用 |
| `CLAUDE_STREAM_IDLE_TIMEOUT_MS` | 流看门狗的空闲超时，最小值被限制为 `300000` | `300000`（最小值） |
| `CLAUDE_CODE_RETRY_WATCHDOG` | 设为 `1` 无限重试容量错误（适用于无人值守运行） | 未启用 |

**示例**：
```python
options = ClaudeAgentOptions(
    env={
        "API_TIMEOUT_MS": "120000",
        "CLAUDE_CODE_MAX_RETRIES": "2",
        "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS": "120000",
    },
)
```

---

## 注意事项

### 设置优先级

程序化选项（如 `agents`、`allowed_tools`）覆盖文件系统设置。托管策略设置覆盖程序化选项。

完整优先级链（从高到低）：
1. 托管策略设置
2. 程序化选项（`ClaudeAgentOptions`）
3. 本地设置（`.claude/settings.local.json`）
4. 项目设置（`.claude/settings.json`）
5. 用户设置（`~/.claude/settings.json`）

### 默认工具集

当 `tools` 为 `None`（默认值）时，SDK 使用 Claude Code 的默认工具集。可以通过设置 `tools={"type": "preset", "preset": "claude_code"}` 显式指定。

### 已弃用字段

- `debug_stderr`：使用 `stderr` 回调替代
- `max_thinking_tokens`：使用 `thinking` 替代
- `betas` 中的 `context-1m-2025-08-07`：自 2026 年 4 月 30 日起已弃用
- `updatedMCPToolOutput`（在 `PostToolUseHookSpecificOutput` 中）：使用 `updatedToolOutput` 替代

### Python SDK 与 TypeScript SDK 的差异

- Python SDK 的 `HookEvent` 不包含 `SessionStart`、`SessionEnd`、`Setup`、`TeammateIdle`、`TaskCompleted`、`ConfigChange`、`WorktreeCreate`、`WorktreeRemove`、`PostToolBatch`、`MessageDisplay`
- `AgentDefinition` 字段使用 camelCase（如 `disallowedTools`、`permissionMode`），而 `ClaudeAgentOptions` 使用 snake_case
- Python 中使用 `continue_` 和 `async_`（带下划线）以避免与保留关键字冲突

### Hooks 最佳实践

- 当多个 hooks 或权限规则适用时，优先级：`deny` > `defer` > `ask` > `allow`
- 使用 `updatedInput` 时必须同时包含 `permissionDecision: 'allow'` 或 `'ask'`
- 异步输出不能阻止、修改或向操作注入上下文
- 在 hook 内部捕获异常，避免未处理的异常中断代理
- 匹配器仅匹配工具名称，不匹配文件路径或其他参数

### Session 存储注意事项

- 存储是镜像，不是替代品。本地磁盘始终先写入
- `sessionStore` 不能与 `persistSession: False` 或 `enableFileCheckpointing` 结合使用
- 镜像写入是尽力而为的，失败不会中断代理
- SDK 永远不会自行从存储中删除数据
- 子代理记录在 `subpath: "subagents/agent-<id>"` 下镜像

### 类型约定：@dataclass vs TypedDict

Python SDK 中使用了两种类型模式，理解它们的区别对正确使用 API 很重要：

**`@dataclass` 类**（运行时为对象实例，支持属性访问 `obj.field`）：

- `ClaudeAgentOptions`、`ResultMessage`、`AgentDefinition`、`HookMatcher`
- `PermissionResultAllow`、`PermissionResultDeny`、`PermissionUpdate`、`PermissionRuleValue`、`ToolPermissionContext`
- `SdkMcpTool`、`StreamEvent`、`RateLimitEvent`、`RateLimitInfo`
- `TaskStartedMessage`、`TaskProgressMessage`、`TaskNotificationMessage`
- `UserMessage`、`AssistantMessage`、`SystemMessage`
- `ToolUseBlock`、`ToolResultBlock`、`ThinkingBlock`、`TextBlock`
- `SDKSessionInfo`、`SessionMessage`

**`TypedDict` 类**（运行时为纯字典，需要键访问 `d["key"]`）：

- `ThinkingConfigEnabled`、`ThinkingConfigAdaptive`、`ThinkingConfigDisabled`
- `McpStdioServerConfig`、`McpSSEServerConfig`、`McpHttpServerConfig`、`McpSdkServerConfig`
- `SyncHookJSONOutput`、`AsyncHookJSONOutput`
- `SystemPromptPreset`、`ToolsPreset`、`SdkPluginConfig`
- `McpStatusResponse`、`McpServerStatus`
- `TaskUsage`、`HookContext`
- `BaseHookInput` 及其所有子类型（`PreToolUseHookInput` 等）
- 所有 `HookSpecificOutput` 子类型

> **示例**：`config["budget_tokens"]`（TypedDict）vs `msg.result`（@dataclass）

---

> **文档版本**：基于 2026 年 6 月 Claude Code 官方文档整理
> **原始来源**：https://code.claude.com/docs/zh-CN/agent-sdk/python