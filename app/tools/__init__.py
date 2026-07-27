"""
Tool Registry — typed, extensible tool registration with async handler support.

Replaces the flat TOOLS dict list with a proper ToolRegistry class that:
- Uses typed dataclasses for tool definitions
- Supports async lifecycle management (startup/shutdown)
- Provides middleware hooks: pre_execute / post_execute / on_error
- Validates handler signatures against declared input_schema
- Supports concurrent batch execution (execute_all)
- Exports OpenAI function-calling-compatible schemas
- Maintains backward compatibility with existing consumers
- Uses streaming-log-pattern tagged logging ([Tool] prefix)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.tools.list_databases import list_databases
from app.tools.select_database import select_database
from app.tools.describe_table import describe_table
from app.tools.query_database import query_database
from app.tools.execute_sql import execute_sql
from app.tools.find_table import find_table
from app.tools.formatters import format_as_markdown_table

logger = logging.getLogger(__name__)

# ============================================================================
# Type aliases
# ============================================================================

# An async tool handler: takes keyword arguments, returns a string result.
AsyncToolHandler = Callable[..., Awaitable[str]]

# A middleware wraps a handler and returns a new handler (chain pattern).
AsyncToolMiddleware = Callable[
    [AsyncToolHandler, "ToolDef"],
    AsyncToolHandler,
]

# Hook signatures for the explicit middleware pipeline.
PreHook = Callable[["ToolCallContext"], Awaitable[None]]
PostHook = Callable[["ToolCallContext", str], Awaitable[str | None]]
ErrorHook = Callable[["ToolCallContext", Exception], Awaitable[str | None]]

# ============================================================================
# Tool Definition
# ============================================================================


@dataclass
class ToolDef:
    """Typed definition of a single tool registered in the system.

    Attributes:
        name: Unique tool name (LLM calls tools by this name).
        description: Human-readable description (used in LLM system prompt).
        handler: Async callable that executes the tool logic.
        parameters: JSON Schema for the tool's input parameters.
        metadata: Optional extra metadata (tags, category, priority).
        enabled: Whether the tool is enabled for execution.
        default_timeout: Timeout in seconds for this tool's execution.
            None means use the registry default.
    """

    name: str
    description: str
    handler: AsyncToolHandler
    parameters: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    default_timeout: float | None = None

    def to_openai_function(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling tool format (with type wrapper)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI input_schema format (used by _build_tool_schemas)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def validate_handler_signature(self) -> tuple[bool, str]:
        """Validate that the handler's parameter names match the declared input_schema.

        Checks:
        1. Handler param names must be a subset of input_schema.properties keys.
        2. input_schema.required keys must exist as handler parameters.
        3. Handler must not have extra params not declared in schema.

        Returns:
            (is_valid, message)
        """
        sig = inspect.signature(self.handler)
        handler_params = set(sig.parameters.keys())

        schema_props = set(self.parameters.get("properties", {}).keys())
        schema_required = set(self.parameters.get("required", []))

        # Handler params not declared in schema
        extra = handler_params - schema_props
        if extra:
            return False, (
                f"Handler 参数 {extra} 未在 input_schema.properties 中声明"
            )

        # Schema required params missing from handler
        missing = schema_required - handler_params
        if missing:
            return False, (
                f"input_schema.required 参数 {missing} 在 handler 中不存在"
            )

        return True, "OK"

    def validate_schema(self) -> tuple[bool, str]:
        """Validate the basic structure of input_schema.

        Checks:
        1. type must be "object".
        2. properties must be a non-empty dict.
        3. required keys must exist in properties.
        """
        if self.parameters.get("type") != "object":
            return False, "input_schema.type 必须为 'object'"
        props = self.parameters.get("properties", {})
        if not isinstance(props, dict) or len(props) == 0:
            return False, "input_schema.properties 不能为空"
        required = set(self.parameters.get("required", []))
        missing = required - set(props.keys())
        if missing:
            return False, f"input_schema.required 中 {missing} 不在 properties 中"
        return True, "OK"


# ============================================================================
# Tool Call Context (per-invocation metadata)
# ============================================================================


@dataclass
class ToolCallContext:
    """Per-invocation context for a single tool call.

    Carries timing, trace, and input data for middleware hooks.

    Attributes:
        tool_name: Name of the tool being called.
        input_data: Arguments passed to the handler.
        start_time: Monotonic timestamp of invocation start.
        trace_id: Optional trace identifier for distributed tracing.
    """

    tool_name: str
    input_data: dict[str, Any]
    start_time: float = field(default_factory=time.monotonic)
    trace_id: str = ""

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time since invocation start, in milliseconds."""
        return (time.monotonic() - self.start_time) * 1000


# ============================================================================
# Built-in Middleware (chain pattern)
# ============================================================================


def timeout_middleware(default_timeout: float = 60.0) -> AsyncToolMiddleware:
    """Middleware that applies an asyncio timeout to tool execution.

    Args:
        default_timeout: Default timeout in seconds.

    Returns:
        Middleware factory.
    """

    def _wrap(handler: AsyncToolHandler, tool: ToolDef) -> AsyncToolHandler:
        timeout_val = tool.default_timeout or default_timeout

        async def _timeout_handler(**kwargs: Any) -> str:
            try:
                return await asyncio.wait_for(
                    handler(**kwargs),
                    timeout=timeout_val,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[Tool] [WARN] %s 超时 %.1fs", tool.name, timeout_val
                )
                return f"工具执行超时（{timeout_val:.0f}秒）: {tool.name}"
            except Exception as exc:
                logger.error(
                    "[Tool] [ERROR] %s 失败: %s", tool.name, exc, exc_info=True
                )
                return f"工具执行异常: {tool.name}: {exc}"

        return _timeout_handler

    return _wrap


def error_normalize_middleware() -> AsyncToolMiddleware:
    """Middleware that normalizes all handler results to strings.

    Catches any unhandled exceptions and returns a user-friendly error string
    instead of letting the exception propagate to the agent loop.
    """

    def _wrap(handler: AsyncToolHandler, tool: ToolDef) -> AsyncToolHandler:
        async def _safe_handler(**kwargs: Any) -> str:
            try:
                result = await handler(**kwargs)
                return str(result)
            except TypeError as exc:
                logger.warning(
                    "[Tool] [WARN] %s 参数错误: %s", tool.name, exc
                )
                return f"工具参数错误: {tool.name}: {exc}"
            except Exception as exc:
                logger.error(
                    "[Tool] [ERROR] %s 未处理异常: %s", tool.name, exc, exc_info=True
                )
                return f"工具执行失败: {tool.name}: {exc}"

        return _safe_handler

    return _wrap


# ============================================================================
# Tool Registry
# ============================================================================


class ToolRegistry:
    """Central registry for tool definitions with async handler support.

    Features:
    - Register/unregister tools dynamically with schema/signature validation.
    - Async lifecycle management (startup/shutdown callbacks).
    - Two middleware mechanisms:
      * Chain middleware: wraps raw handler (timeout, error normalization).
      * Hook middleware: pre_execute/post_execute/on_error hooks (observability).
    - Concurrent batch execution (execute_all).
    - Export schemas for OpenAI function-calling format.
    - Streaming-log-pattern tagged output ([Tool] prefix).
    - Thread-safe registration via asyncio.Lock.

    Usage::

        registry = ToolRegistry()
        registry.register(
            name="my_tool",
            description="Does something useful",
            handler=my_async_handler,
            parameters={"type": "object", "properties": {...}},
        )
        registry.apply_middleware(timeout_middleware(default_timeout=60.0))
        registry.apply_middleware(error_normalize_middleware())

        await registry.startup()

        # Execute
        result = await registry.execute("my_tool", arg1="value")

        # Get schemas for LLM
        schemas = registry.get_openai_schemas()

        await registry.shutdown()
    """

    def __init__(self, log_prefix: str = "[Tool]") -> None:
        self._tools: dict[str, ToolDef] = {}
        self._lock = asyncio.Lock()
        self._started = False

        # Chain middleware: wraps raw handler → wrapped handler
        self._middleware_chain: list[AsyncToolMiddleware] = []

        # Hook middleware: explicit pre/post/error hooks (decorator-based)
        self._pre_hooks: list[PreHook] = []
        self._post_hooks: list[PostHook] = []
        self._error_hooks: list[ErrorHook] = []

        # Lifecycle callbacks
        self._startup_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []

        # Log prefix for streaming-log-pattern output
        self.log_prefix = log_prefix

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def tool_names(self) -> list[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())

    @property
    def tool_count(self) -> int:
        """Get the number of registered tools."""
        return len(self._tools)

    @property
    def is_started(self) -> bool:
        """Whether startup() has completed."""
        return self._started

    # ── Registration ──────────────────────────────────────────────────

    def _register_impl(
        self,
        name: str,
        description: str,
        handler: AsyncToolHandler,
        parameters: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
        default_timeout: float | None = None,
    ) -> ToolDef:
        """Internal synchronous registration logic (lock must be held by caller)."""
        if name in self._tools:
            raise ValueError(
                f"{self.log_prefix} 工具 '{name}' 已注册，请先调用 unregister()"
            )

        tool = ToolDef(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters,
            metadata=metadata or {},
            enabled=enabled,
            default_timeout=default_timeout,
        )

        # Validate schema structure
        valid, msg = tool.validate_schema()
        if not valid:
            raise ValueError(
                f"{self.log_prefix} 工具 '{name}' schema 无效: {msg}"
            )

        # Validate handler signature
        valid, msg = tool.validate_handler_signature()
        if not valid:
            raise ValueError(
                f"{self.log_prefix} 工具 '{name}' 签名不匹配: {msg}"
            )

        self._tools[name] = tool
        logger.debug(
            "%s [OK] 注册工具 '%s' (参数: %s)",
            self.log_prefix,
            name,
            list(parameters.get("properties", {}).keys()),
        )
        return tool

    def register_sync(
        self,
        name: str,
        description: str,
        handler: AsyncToolHandler,
        parameters: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
        default_timeout: float | None = None,
    ) -> ToolDef:
        """Synchronous registration for module-level init (no lock needed, startup phase only).

        For runtime registration from async contexts, use async register() instead.
        """
        return self._register_impl(
            name, description, handler, parameters, metadata, enabled, default_timeout
        )

    async def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to remove.

        Raises:
            KeyError: If the tool is not registered.
        """
        async with self._lock:
            if name not in self._tools:
                raise KeyError(
                    f"{self.log_prefix} 工具 '{name}' 不存在，无法注销"
                )
            del self._tools[name]
            logger.debug("%s [OK] 注销工具 '%s'", self.log_prefix, name)

    def get(self, name: str) -> ToolDef | None:
        """Get a tool definition by name (synchronous, lock-free).

        Args:
            name: Tool name.

        Returns:
            ToolDef if found, None otherwise.
        """
        return self._tools.get(name)

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Start the registry: validate all tools, invoke startup callbacks.

        Uses streaming-log-pattern phase-grouped output.

        --- Registry Startup ---
        [Tool] [INFO] 启动 N 个工具
        [Tool] [OK] 签名校验通过: N/N
        """
        if self._started:
            return

        print(f"\n--- Registry Startup ---")
        print(f"{self.log_prefix} [INFO] 启动 {len(self._tools)} 个工具")

        # Validate all registered tools
        failures: list[tuple[str, str]] = []
        async with self._lock:
            for name, tool in self._tools.items():
                valid, msg = tool.validate_handler_signature()
                if not valid:
                    failures.append((name, msg))

        if failures:
            print(
                f"{self.log_prefix} [WARN] 签名校验失败 {len(failures)} 个:"
            )
            for name, msg in failures:
                print(f"  - {name}: {msg}")
        else:
            print(
                f"{self.log_prefix} [OK] 签名校验通过: "
                f"{len(self._tools)}/{len(self._tools)}"
            )

        # Invoke startup callbacks
        for cb in self._startup_callbacks:
            await cb()

        self._started = True
        print(f"{self.log_prefix} [OK] Registry 启动完成\n")

    async def shutdown(self) -> None:
        """Shut down the registry: invoke shutdown callbacks.

        --- Registry Shutdown ---
        [Tool] [INFO] 关闭 N 个工具
        [Tool] [OK] Registry 已关闭
        """
        if not self._started:
            return

        print(f"\n--- Registry Shutdown ---")
        print(f"{self.log_prefix} [INFO] 关闭 {len(self._tools)} 个工具")

        for cb in self._shutdown_callbacks:
            await cb()

        self._started = False
        print(f"{self.log_prefix} [OK] Registry 已关闭\n")

    def on_startup(self, cb: Callable[[], Awaitable[None]]) -> None:
        """Register a startup lifecycle callback."""
        self._startup_callbacks.append(cb)

    def on_shutdown(self, cb: Callable[[], Awaitable[None]]) -> None:
        """Register a shutdown lifecycle callback."""
        self._shutdown_callbacks.append(cb)

    # ── Chain Middleware ──────────────────────────────────────────────

    def apply_middleware(self, middleware: AsyncToolMiddleware) -> None:
        """Append a middleware to the chain (wraps raw handler).

        Middleware are applied in registration order: the first middleware
        added wraps the raw handler, the second wraps the result of the first,
        and so on. The outermost middleware (last added) runs first at call time.

        Args:
            middleware: A middleware factory function.
        """
        self._middleware_chain.append(middleware)
        logger.debug(
            "%s [INFO] 添加中间件: %s", self.log_prefix, middleware.__name__
        )

    def _wrap_handler(self, tool: ToolDef) -> AsyncToolHandler:
        """Apply the middleware chain to a tool's raw handler.

        Args:
            tool: The tool definition.

        Returns:
            Wrapped handler with all chain middleware applied.
        """
        handler = tool.handler
        for mw in reversed(self._middleware_chain):
            handler = mw(handler, tool)
        return handler

    # ── Hook Middleware (decorator-based) ─────────────────────────────

    def pre_execute(self, hook: PreHook) -> PreHook:
        """Register a pre_execute hook (runs before handler).

        Use as decorator::

            @registry.pre_execute
            async def log_start(ctx: ToolCallContext) -> None:
                print(f"Starting {ctx.tool_name}")
        """
        self._pre_hooks.append(hook)
        return hook

    def post_execute(self, hook: PostHook) -> PostHook:
        """Register a post_execute hook (runs after handler, can replace result).

        Return None to keep the original result, or a string to replace it.

        Use as decorator::

            @registry.post_execute
            async def truncate(ctx: ToolCallContext, result: str) -> str | None:
                if len(result) > 10000:
                    return result[:10000] + "..."
                return None
        """
        self._post_hooks.append(hook)
        return hook

    def on_error(self, hook: ErrorHook) -> ErrorHook:
        """Register an error hook (runs on handler exception, can recover).

        Return None to let the exception propagate, or a string to return
        as the result instead.

        Use as decorator::

            @registry.on_error
            async def handle_timeout(ctx: ToolCallContext, exc: Exception) -> str | None:
                if isinstance(exc, asyncio.TimeoutError):
                    return f"超时: {ctx.tool_name}"
                return None
        """
        self._error_hooks.append(hook)
        return hook

    # ── Execution ─────────────────────────────────────────────────────

    async def execute(self, name: str, **kwargs: Any) -> str:
        """Execute a tool by name through the full middleware pipeline.

        Pipeline:
            pre_hooks[*] → wrapped_handler(**kwargs) → post_hooks[*]
            └─ on exception: error_hooks[*] → raise if unhandled

        Args:
            name: Tool name.
            **kwargs: Arguments passed to the tool handler.

        Returns:
            String result from the tool execution.
            Returns an error string if the tool is unknown or disabled.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"未知工具: {name}"
        if not tool.enabled:
            return f"工具已禁用: {name}"

        ctx = ToolCallContext(tool_name=name, input_data=kwargs)

        logger.debug(
            "%s [INFO] 开始执行 '%s' 参数: %s",
            self.log_prefix, name, list(kwargs.keys()),
        )

        # --- pre_execute hooks ---
        for hook in self._pre_hooks:
            try:
                await hook(ctx)
            except Exception as hook_err:
                logger.warning(
                    "%s [WARN] pre_execute hook 异常: %s",
                    self.log_prefix, hook_err,
                )

        # --- handler execution ---
        result: str
        try:
            wrapped = self._wrap_handler(tool)

            # 过滤 LLM 幻觉参数：只保留 handler 签名中声明的参数。
            # DeepSeek 有时会把 JSON Schema 的元字段名（如 "parameters"）
            # 误当作实际参数传入，导致 TypeError。过滤后这些幻影参数被静默丢弃。
            handler_params = set(inspect.signature(tool.handler).parameters.keys())
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in handler_params}
            if len(filtered_kwargs) < len(kwargs):
                dropped = set(kwargs.keys()) - set(filtered_kwargs.keys())
                logger.warning(
                    "%s [WARN] %s 过滤了 LLM 幻觉参数: %s",
                    self.log_prefix, name, dropped,
                )

            raw_result = await wrapped(**filtered_kwargs)
            result = str(raw_result)
        except Exception as exc:
            # --- error hooks ---
            for hook in self._error_hooks:
                try:
                    replacement = await hook(ctx, exc)
                    if replacement is not None:
                        logger.info(
                            "%s [OK] 错误被中间件处理: '%s' → %s",
                            self.log_prefix, name, type(exc).__name__,
                        )
                        result = replacement
                        break
                except Exception as hook_err:
                    logger.warning(
                        "%s [WARN] error hook 异常: %s",
                        self.log_prefix, hook_err,
                    )
            else:
                # No error hook handled it — re-raise
                logger.error(
                    "%s [ERROR] 工具执行异常 '%s': %s: %s",
                    self.log_prefix, name, type(exc).__name__, exc,
                )
                raise

        # --- post_execute hooks ---
        for hook in self._post_hooks:
            try:
                replacement = await hook(ctx, result)
                if replacement is not None:
                    result = replacement
            except Exception as hook_err:
                logger.warning(
                    "%s [WARN] post_execute hook 异常: %s",
                    self.log_prefix, hook_err,
                )

        elapsed = ctx.elapsed_ms
        logger.debug(
            "%s [OK] 完成 '%s' 耗时: %.0fms 结果长度: %d",
            self.log_prefix, name, elapsed, len(result),
        )

        return result

    # ── Batch Execution ───────────────────────────────────────────────

    async def execute_all(
        self, calls: list[tuple[str, dict[str, Any]]]
    ) -> list[tuple[str, str]]:
        """Execute multiple tool calls concurrently.

        Uses streaming-log-pattern batch phase output.

        --- Batch Tool Execution ---
        [Tool] [INFO] 并发执行 N 个工具
        [Tool] [OK] 批量执行完成: M/N 成功

        Args:
            calls: List of (tool_name, kwargs_dict) tuples.

        Returns:
            List of (tool_name, result_str) tuples in input order.
        """
        if not calls:
            return []

        print(f"\n--- Batch Tool Execution ---")
        print(
            f"{self.log_prefix} [INFO] 并发执行 {len(calls)} 个工具"
        )

        async def _execute_one(
            name: str, args: dict[str, Any]
        ) -> tuple[str, str]:
            try:
                result = await self.execute(name, **args)
                return (name, result)
            except Exception as exc:
                return (
                    name,
                    f"{self.log_prefix} [ERROR] {name}: {exc}",
                )

        tasks = [_execute_one(name, args) for name, args in calls]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        success_count = sum(
            1
            for _, r in results
            if not r.startswith(f"{self.log_prefix} [ERROR]")
        )
        print(
            f"{self.log_prefix} [OK] 批量执行完成: "
            f"{success_count}/{len(results)} 成功\n"
        )

        return results

    # ── Schema Export ─────────────────────────────────────────────────

    def get_openai_schemas(self) -> list[dict[str, Any]]:
        """Export tools as OpenAI input_schema format.

        Compatible with the existing _build_tool_schemas() output format.

        Returns:
            List of tool schemas.
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_openai_functions(self) -> list[dict[str, Any]]:
        """Export tools as OpenAI function-calling format.

        Returns:
            List of function definitions with type wrapper.
        """
        return [tool.to_openai_function() for tool in self._tools.values()]

    # ── Introspection ─────────────────────────────────────────────────

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())


# ============================================================================
# Default Registry Instance
# ============================================================================

# Create and configure the default registry with built-in tools.
_default_registry = ToolRegistry(log_prefix="[Tool]")

# Apply default chain middleware: timeout first, then error normalization.
# Order: timeout wraps raw handler → error_normalize wraps timeout
# → caller sees error_normalize (outermost).
_default_registry.apply_middleware(timeout_middleware(default_timeout=120.0))
_default_registry.apply_middleware(error_normalize_middleware())

# Register built-in tools
_default_registry.register_sync(
    name="list_databases",
    description=(
        "列出当前用户有权限访问的数据库。"
        "仅在用户想了解'有哪些数据库'时使用，找表请用 find_table。"
    ),
    handler=list_databases,
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜索关键词，用于过滤数据库名称",
            },
            "env_type": {
                "type": "string",
                "description": "环境类型，默认 test",
            },
        },
    },
)

_default_registry.register_sync(
    name="select_database",
    description="选择当前数据库，设置后续查询的默认上下文。",
    handler=select_database,
    parameters={
        "type": "object",
        "properties": {
            "schema_id": {
                "type": "integer",
                "description": "数据库的 schemaId（从 list_databases 结果中获取）",
            },
        },
        "required": ["schema_id"],
    },
)

_default_registry.register_sync(
    name="find_table",
    description=(
        "在所有可访问数据库中搜索匹配的表名（自动覆盖所有环境）。"
        "正常搜索：keyword 支持逗号分隔的多关键词（最多5个），取并集。"
        "兜底模式：3-4 次关键词搜索仍找不到目标表时，keyword 留空调用，"
        "返回所有环境的所有表（每环境最多 500 条）。"
        "结果包含 (schemaId, 数据库名, 环境, 表名, 表注释)，"
        "请根据表注释与用户问题的语义匹配，选择最合适的表。"
    ),
    handler=find_table,
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": (
                    "搜索关键词，支持逗号分隔多个（如'order,ticket,task'），"
                    "最多5个，取并集。留空则返回所有表（兜底模式）。"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数，默认 200，上限 500",
            },
        },
        "required": ["keyword"],
    },
)

_default_registry.register_sync(
    name="describe_table",
    description=(
        "查看表结构，获取字段名、类型等信息。"
        "仅在用户明确要求'看看表结构'时使用，找表、查询数据时不要调用此工具。"
    ),
    handler=describe_table,
    parameters={
        "type": "object",
        "properties": {
            "schema_id": {
                "type": "integer",
                "description": "数据库的 schemaId",
            },
            "table_name": {
                "type": "string",
                "description": "表名",
            },
        },
        "required": ["schema_id", "table_name"],
    },
)

_default_registry.register_sync(
    name="query_database",
    description=(
        "【首选】自然语言查询数据库，根据用户问题自动生成 SQL 并执行。"
        "当用户用自然语言描述查询需求时优先使用此工具，不要自己写 SQL 用 execute_sql 试错。"
        "追问时也使用此工具，在 question 参数中包含完整需求。"
        "涉及多表 JOIN 时，table_name 用逗号分隔传入所有表名（如 \"order_record, account\"），"
        "工具会自动获取各表结构。"
    ),
    handler=query_database,
    parameters={
        "type": "object",
        "properties": {
            "schema_id": {
                "type": "integer",
                "description": "数据库的 schemaId",
            },
            "question": {
                "type": "string",
                "description": "用户的自然语言问题（包含完整需求，追问时也包含修改点）",
            },
            "table_name": {
                "type": "string",
                "description": (
                    "目标表名，涉及多表 JOIN 时用逗号分隔（如 \"order_record, account\"），最多 5 个"
                ),
            },
            "summary": {
                "type": "string",
                "description": "对话摘要（可选），用于理解上下文",
            },
        },
        "required": ["schema_id", "question", "table_name"],
    },
)

_default_registry.register_sync(
    name="execute_sql",
    description=(
        "直接执行 SQL 查询。仅在用户提供了明确 SQL 语句时使用。"
        "不要用此工具搜索表名——找表请用 find_table，不要执行 SHOW TABLES。"
        "只允许 SELECT/SHOW/DESCRIBE。"
    ),
    handler=execute_sql,
    parameters={
        "type": "object",
        "properties": {
            "schema_id": {
                "type": "integer",
                "description": "数据库的 schemaId",
            },
            "sql": {
                "type": "string",
                "description": "SQL 语句（只允许 SELECT/SHOW/DESCRIBE）",
            },
        },
        "required": ["schema_id", "sql"],
    },
)


# ============================================================================
# Public API (backward-compatible exports)
# ============================================================================

# Module-level registry instance (the single source of truth).
registry = _default_registry


def get_registry() -> ToolRegistry:
    """Get the default tool registry instance."""
    return registry


def get_tool_handler(name: str) -> AsyncToolHandler | None:
    """Get the raw handler for a tool by name (backward-compatible).

    Note: Prefer using registry.execute() which applies middleware,
    rather than calling the raw handler directly.

    Args:
        name: Tool name.

    Returns:
        The handler callable, or None if not found.
    """
    tool = registry.get(name)
    return tool.handler if tool else None


# ============================================================================
# Backward-compatible TOOLS list and TOOL_HANDLERS dict
# ============================================================================

# TOOLS: list of dicts in the old format, for code that still uses it.
TOOLS: list[dict[str, Any]] = [
    {
        "name": t.name,
        "description": t.description,
        "handler": t.handler,
        "parameters": t.parameters,
    }
    for t in registry
]

# TOOL_HANDLERS: name -> raw handler mapping.
TOOL_HANDLERS: dict[str, AsyncToolHandler] = {
    t.name: t.handler for t in registry
}


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    # Core classes
    "ToolDef",
    "ToolRegistry",
    "ToolCallContext",
    # Type aliases
    "AsyncToolHandler",
    "AsyncToolMiddleware",
    "PreHook",
    "PostHook",
    "ErrorHook",
    # Middleware
    "timeout_middleware",
    "error_normalize_middleware",
    # Default registry
    "registry",
    "get_registry",
    # Backward-compatible API
    "TOOLS",
    "TOOL_HANDLERS",
    "get_tool_handler",
    # Individual tool handlers (for direct imports)
    "list_databases",
    "select_database",
    "find_table",
    "describe_table",
    "query_database",
    "execute_sql",
    "format_as_markdown_table",
]
