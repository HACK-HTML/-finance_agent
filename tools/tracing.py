"""
LangFuse 可观测性基础设施 —— 零侵入包装层
==========================================

统一管理 LangFuse 客户端初始化，提供装饰器和上下文管理器。
如果环境变量未配置，所有追踪自动跳过（零性能开销）。

用法::

    from tools.tracing import get_langfuse_client, traced, TraceContext

    # 装饰器 —— 无 LangFuse 时透传
    @traced(name="my_function")
    def my_function():
        ...

    # 上下文管理器 —— 循环内的内联包裹
    with TraceContext(name="tool.execute", metadata={"tool": "calculate"}) as span:
        result = fn()
        span.update(output=str(result)[:500])

    # 创建顶级 observation（Session 级别）
    lf = get_langfuse_client()
    if lf:
        obs = lf.start_observation(name="agent.chat", as_type="span", ...)
"""
from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Any

LANGFUSE_SECRET_KEY="sk-lf-c31251b3-e52a-479c-8e7a-c1d1875a37ad"
LANGFUSE_PUBLIC_KEY="pk-lf-b086c3d9-ef66-4606-acb7-dcedec6dea02"
LANGFUSE_BASE_URL="https://jp.cloud.langfuse.com"
# ── PII scrubbing ─────────────────────────────────────────────────────────────

# Patterns to redact before sending content to observability platforms
_SCRUB_PATTERNS: list[tuple[str, str]] = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),      # email
    (r'\b1[3-9]\d{9}\b', '[PHONE]'),                                              # Chinese mobile
    (r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b', '[ID_NUMBER]'),  # Chinese ID
    (r'\b[sm]0-[a-zA-Z0-9_-]{20,}\b', '[API_KEY]'),                              # Mem0 / service keys
    (r'\bsk-[a-zA-Z0-9_-]{20,}\b', '[API_KEY]'),                                 # OpenAI/DeepSeek keys
]


def scrub_content(text: str) -> str:
    """Redact PII patterns from text before sending to observability platforms."""
    for pattern, replacement in _SCRUB_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


# ── 模块级惰性单例 ──────────────────────────────────────────────────────────

_client: Any = None         # Langfuse | None
_checked: bool = False      # 是否已检查过环境变量


def get_langfuse_client() -> Any | None:
    """
    返回全局 LangFuse 客户端。
    未配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST 时返回 None。
    惰性初始化：只在第一次调用时检查环境变量。
    """
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    pk = LANGFUSE_PUBLIC_KEY
    sk = LANGFUSE_SECRET_KEY
    host = LANGFUSE_BASE_URL
    if pk and sk and host:
        from langfuse import Langfuse
        _client = Langfuse(public_key=pk, secret_key=sk, base_url=host)
    return _client


def _is_enabled() -> bool:
    """追踪是否已启用（快捷检查，不触发惰性初始化）。"""
    if _checked:
        return _client is not None
    return bool(
       LANGFUSE_PUBLIC_KEY
        and LANGFUSE_SECRET_KEY
        and LANGFUSE_BASE_URL
    )


# ── 条件装饰器 ─────────────────────────────────────────────────────────────

def traced(name: str | None = None, *, capture_input: bool = True, **span_kwargs):
    """
    LangFuse @observe() 的条件包装。

    当 LangFuse 未配置时，返回透传装饰器（直接返回原函数，零开销）。
    已配置时，委托给 ``langfuse.decorators.observe``。

    Usage::

        @traced(name="my_span")
        def my_function():
            ...

        @traced(name="router.classify", capture_input=False)  # 不捕获原始输入
        def classify(cls, query: str) -> str:
            ...
    """
    if not _is_enabled():
        return lambda fn: fn
    from langfuse import observe
    kwargs = {**span_kwargs, "capture_input": capture_input}
    if name:
        return observe(name=name, **kwargs)
    return observe(**kwargs)


# ── 内联 Span 上下文管理器 ─────────────────────────────────────────────────

class _SpanHandle:
    """轻量 span handle —— 封装 LangFuse observation 对象，提供 update() 便捷方法。"""

    def __init__(self, lf_observation: Any):
        self._span = lf_observation
        self._start = time.time()

    @property
    def trace_context(self) -> dict[str, str] | None:
        """暴露 trace_context dict，供子 observation 的 trace_context 参数引用。

        LangFuse SDK v4 用 dict(trace_id, parent_span_id) 建立父子关系，
        替代旧版的 parent=span_object 参数。
        """
        if self._span is None:
            return None
        try:
            return {
                "trace_id": self._span.trace_id,
                "parent_span_id": self._span.id,
            }
        except Exception:
            return None

    def update(
        self,
        *,
        output: str | None = None,
        metadata: dict | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ):
        """更新 observation 的输出和元数据。"""
        dur = time.time() - self._start
        updates: dict[str, Any] = {}
        if output is not None:
            updates["output"] = output
        if metadata is not None:
            updates["metadata"] = metadata
        if level is not None:
            updates["level"] = level
        if status_message is not None:
            updates["status_message"] = status_message
        updates["metadata"] = {**(updates.get("metadata") or {}),
                               "duration_ms": round(dur * 1000)}
        try:
            self._span.update(**updates)
        except Exception:
            pass  # 追踪失败不影响业务

    def end(self):
        """显式结束 observation。"""
        try:
            self._span.end()
        except Exception:
            pass


class _NoopSpan:
    """无操作 span —— 未配置 LangFuse 时使用，所有方法为空操作。"""

    trace_context = None

    def update(self, **kwargs):  # noqa: ARG002
        pass

    def end(self):
        pass


@contextmanager
def TraceContext(
    name: str,
    *,
    input_data: str | None = None,
    metadata: dict | None = None,
    parent: Any | None = None,  # _SpanHandle 实例 或 LangFuse observation
):
    """
    手动创建 span 的上下文管理器。

    用于无法用 @traced 装饰器的场景（如工具执行循环中的内联包裹、
    ReAct 迭代循环等）。

    Usage::

        with TraceContext(name="tool.calculate",
                          input_data=json.dumps(inputs),
                          metadata={"type": "math"}) as span:
            result = fn()
            span.update(output=str(result)[:500])
    """
    lf = get_langfuse_client()
    if lf is None:
        yield _NoopSpan()
        return

    # 构建 trace_context 用于建立父子关系
    trace_context = None
    if parent is not None:
        if hasattr(parent, "trace_context"):
            # _SpanHandle / _NoopSpan
            trace_context = parent.trace_context
        elif hasattr(parent, "trace_id"):
            # 原始 LangFuse observation
            try:
                trace_context = {
                    "trace_id": parent.trace_id,
                    "parent_span_id": parent.id,
                }
            except Exception:
                pass

    # 1. 独立处理初始化的异常
    try:
        lf_span = lf.start_observation(
            name=name,
            as_type="span",
            trace_context=trace_context,
            input=input_data,
            metadata=metadata,
        )
        handle = _SpanHandle(lf_span)
    except Exception:
        # 如果 LangFuse 宕机，安全降级并直接返回，结束生成器
        yield _NoopSpan()
        return

    # 2. 严格管理业务执行的生命周期
    try:
        # 挂起，执行业务逻辑
        yield handle
    finally:
        # 无论业务代码是成功还是抛出异常，finally 必定执行
        # 确保 Span 被正确关闭，且不会吞噬或干扰业务异常的传播
        handle.end()
