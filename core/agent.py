"""
核心 Agent — 手写 ReAct 循环，无任何框架依赖
ReAct = Reasoning + Acting，每步：Think → Act（调用工具）→ Observe（看结果）→ 重复
"""
import os
import time
from pprint import pprint
from functools import partial
import json
import anthropic
import asyncio
from models.schemas import AgentState, ToolCall, ToolResult, ConversationTurn, MonthlyReport
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS, generate_budget_plan, retrieve_document, memory_recall
from tools.tracing import get_langfuse_client, TraceContext, scrub_content
from memory import MemoryManager


# ── 常量 ──────────────────────────────────────────────────────────────────────
def _require_env(name: str) -> str:
    """读取必须的环境变量，缺失时抛出清晰的错误提示。"""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"缺少必须的环境变量 {name}。请在 .env 文件或系统环境中设置该变量。"
        )
    return val

API_KEY = "sk-6e1028b8517e4cf79735955e4b7733dd"
API_CRITIC_KEY = "sk-f4acd747610446d5a03e361f4a800b7d"

MODEL='deepseek-v4-pro'
BASE_URL = 'https://api.deepseek.com/anthropic'
MAX_ITERATIONS = 10          # 防止无限循环的安全上限
SYSTEM_PROMPT = f"""你是一个专业的个人财务分析助手。你能帮用户：
- 分析收支数据，计算关键指标（储蓄率、消费占比等）
- 查询实时汇率或模拟股票数据
- 制定预算方案并评估财务健康度
- 阅读并检索用户上传的财务文档（理财产品说明书 / 账单 / 年报等），回答文档相关问题
- 调用 memory_recall 检索用户之前对话中透露的个人信息（收入/目标/偏好），用这些信息给出个性化建议
- 多轮追问，持续深入分析


工作原则：
1. 先思考需要哪些信息，再决定调用哪个工具，严格参照Tool Schemas调用工具
2. 工具返回结果后，判断是否需要继续调用或可以给出最终答案
3. 数字计算必须使用 calculate 工具，不要心算
4. 当问题的答案依赖用户上传的具体文档内容（如某产品的费率、合同条款、年报数据、
   账单明细）时，调用 retrieve_document 检索原文，并基于检索结果作答、标注来源；
   检索片段中没有的信息不要编造。纯计算 / 实时行情 / 通用常识则用对应工具或直接回答，
   不要滥用文档检索。
5. 当系统提示中包含「用户记忆摘要」且与当前问题相关时，优先基于记忆给出个性化建议；
   摘要不够详细时可调用 memory_recall 获取完整记忆内容。
6. 回答要具体，给出可操作的建议
"""


# ── ReAct 核心循环 ────────────────────────────────────────────────────────────
class FinanceAgent:
    def __init__(self, session_id: str = "default", user_id: str | None = None,
                 _langfuse_trace=None):
        self.session_id = session_id          # 会话维度（消息历史 / 文档上传）
        self.user_id = user_id or session_id  # 用户维度（记忆 + 文档检索，跨会话共享）
        self.client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)
        self.state = AgentState()
        self._critic = anthropic.Anthropic(api_key=API_CRITIC_KEY, base_url=BASE_URL)
        self.memory = MemoryManager(self.user_id, api_key=API_KEY)
        self._lf = get_langfuse_client()      # LangFuse 客户端（None = 追踪关闭）
        self._lf_trace = _langfuse_trace      # 来自 FastAPI 中间件的 observation
        # 注册表：隐藏参数（_client / user_id / _memory）由 partial 绑定，不进 schema、不暴露给 LLM
        self.tool_registry = {
            **TOOL_REGISTRY,
            "generate_budget_plan": partial(generate_budget_plan, _client=self._critic),
            "retrieve_document": partial(retrieve_document, user_id=self.user_id),
            "memory_recall": partial(memory_recall, _memory=self.memory),
        }

    # ── 动态 System Prompt ─────────────────────────────────────────────────────

    def _make_system_prompt(self, user_input: str) -> str:
        """每轮对话前根据用户输入检索记忆摘要，动态拼入 system prompt 尾部。"""
        results = self.memory.search(user_input)
        summary = self.memory.format_summary(results)
        return SYSTEM_PROMPT + "\n\n## 用户记忆摘要\n" + summary

    # ── 对话入口 ────────────────────────────────────────────────────────────────

    async def chat(self, user_input: str) -> str:
        """
        接收用户消息，执行完整 ReAct 循环，返回最终回答。
        循环结构：
            用户消息 → Claude 思考 → [工具调用 → 观察结果]* → 最终回答
        """
        t_start = time.time()
        lf = self._lf

        # 1. 把用户消息加入历史
        self.state.messages.append({
            "role": "user",
            "content": user_input
        })

        # ── LangFuse Observation（会话级 root）───────────────────────────
        lf_trace = None
        if lf is not None:
            try:
                lf.propagate_attributes(
                    user_id=self.user_id,
                    session_id=self.session_id,
                )
            except Exception:
                pass  # propagate_attributes may not exist in older SDKs
            parent = self._lf_trace  # 来自 FastAPI 中间件的 observation
            trace_context = None
            if parent is not None:
                try:
                    trace_context = {
                        "trace_id": parent.trace_id,
                        "parent_span_id": parent.id,
                    }
                except Exception:
                    pass
            try:
                lf_trace = lf.start_observation(
                    name="agent.chat",
                    as_type="span",
                    trace_context=trace_context,
                    input=scrub_content(user_input)[:500],
                    metadata={"interface": "fastapi" if parent else "cli"},
                )
            except Exception:
                pass  # 追踪失败不影响业务

        iteration = 0
        final_text = "已达到最大推理轮数，请简化问题后重试。"

        while iteration < MAX_ITERATIONS:
            pprint(self.state.messages)

            iteration += 1
            print(f"\n{'─'*50}")
            print(f"[ReAct 第 {iteration} 轮]")

            # 2. 每轮动态拼 system prompt（注入相关记忆摘要）
            system = self._make_system_prompt(user_input)

            # ── LangFuse: ReAct 迭代 span ──────────────────────────────
            with TraceContext(
                name=f"react.iteration_{iteration}",
                metadata={"iteration": iteration},
                parent=lf_trace,
            ) as iter_span:

                # 3. 调用 Claude，附带工具定义
                t_llm = time.time()
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=4096 * 2,
                    system=system,
                    tools=TOOL_SCHEMAS,
                    messages=self.state.messages,
                )
                llm_ms = round((time.time() - t_llm) * 1000)
                stop_reason = response.stop_reason
                llm_text = self._extract_text(response.content)

                print(f"[stop_reason] {stop_reason}")

                # ── LangFuse: LLM Generation ────────────────────────────
                if lf is not None:
                    try:
                        lf_gen = lf.start_observation(
                            name="llm.react",
                            as_type="generation",
                            model=MODEL,
                            trace_context=iter_span.trace_context,
                            input=scrub_content(user_input)[:200],
                            metadata={
                                "stop_reason": stop_reason,
                                "iteration": iteration,
                                "input_chars": sum(
                                    len(str(m.get("content", "")))
                                    for m in self.state.messages
                                ),
                                "output_chars": len(llm_text),
                                "duration_ms": llm_ms,
                            },
                        )
                        lf_gen.update(output=scrub_content(llm_text)[:500])
                        lf_gen.end()
                    except Exception:
                        pass  # 追踪失败不影响业务

                # 4. 把 Claude 的回复加入历史（必须在处理工具调用之前）
                self.state.messages.append({
                    "role": "assistant",
                    "content": response.content
                })

                # 5. 判断停止原因
                if stop_reason == "end_turn":
                    final_text = llm_text
                    self.state.turns.append(
                        ConversationTurn(user=user_input, assistant=final_text)
                    )
                    print(f"[最终回答] 完成（共 {iteration} 轮 ReAct）")
                    iter_span.update(
                        output=scrub_content(final_text)[:500],
                        metadata={
                            "stop_reason": "end_turn",
                            "total_iterations": iteration,
                            "total_duration_ms": round(
                                (time.time() - t_start) * 1000
                            ),
                        },
                    )

                    # ★ 异步存储记忆：fire-and-forget，不阻塞回答返回
                    asyncio.create_task(
                        asyncio.to_thread(
                            self.memory.add_async,
                            f"用户：{user_input}\n助手：{final_text}"
                        )
                    )
                    if lf_trace is not None:
                        try:
                            lf_trace.update(
                                output=scrub_content(final_text)[:500],
                                metadata={
                                    "total_iterations": iteration,
                                    "total_duration_ms": round(
                                        (time.time() - t_start) * 1000
                                    ),
                                },
                            )
                            lf_trace.end()
                        except Exception:
                            pass
                    return final_text

                # tool_use = Claude 决定调用一个或多个工具
                if stop_reason == "tool_use":
                    tool_results = await self._execute_tools(
                        response.content, parent=iter_span,
                    )

                    # 6. 把工具执行结果作为 user 消息反馈给 Claude
                    self.state.messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                    iter_span.update(
                        metadata={"stop_reason": "tool_use",
                                  "tool_count": len(
                                      [b for b in response.content
                                       if b.type == "tool_use"]
                                  )},
                    )
                    continue  # 进入下一轮

                # 兜底：其他停止原因直接取文本
                final_text = llm_text
                asyncio.create_task(
                    asyncio.to_thread(
                        self.memory.add_async,
                        f"用户：{user_input}\n助手：{final_text}"
                    )
                )
                if lf_trace is not None:
                    try:
                        lf_trace.update(output=scrub_content(final_text)[:500])
                        lf_trace.end()
                    except Exception:
                        pass
                return final_text


        # 循环耗尽 MAX_ITERATIONS —— 安全截断
        if lf_trace is not None:
            try:
                lf_trace.update(
                    output=scrub_content(final_text)[:500],
                    metadata={
                        "total_iterations": iteration,
                        "stop_reason": "max_iterations",
                        "total_duration_ms": round(
                            (time.time() - t_start) * 1000
                        ),
                    },
                )
                lf_trace.end()
            except Exception:
                pass
        return final_text

    # ── 工具执行 ────────────────────────────────────────────────────────────────

    async def _execute_single_tool(self, block, parent=None) -> tuple[ToolCall, str]:
        """执行单个工具调用，返回 (调用记录, 结果字符串)。永不抛异常。"""
        tool_call = ToolCall(
            tool_use_id=block.id,
            tool_name=block.name,
            tool_input=block.input,
        )

        print(f"[工具调用] {block.name}({json.dumps(block.input, ensure_ascii=False)})")

        with TraceContext(
            name=f"tool.{block.name}",
            input_data=scrub_content(json.dumps(block.input, ensure_ascii=False))[:500],
            metadata={"tool_name": block.name},
            parent=parent,
        ) as tool_span:
            tool_fn = self.tool_registry.get(block.name)
            tool_ms = -1
            if tool_fn is None:
                result_content = f"错误：工具 '{block.name}' 未注册"
            else:
                try:
                    t_tool = time.time()
                    if asyncio.iscoroutinefunction(tool_fn):
                        result_content = await tool_fn(**block.input)
                    else:
                        result_content = await asyncio.to_thread(tool_fn, **block.input)
                    tool_ms = round((time.time() - t_tool) * 1000)
                except Exception as e:
                    result_content = f"工具执行出错：{str(e)}"

            tool_span.update(
                output=scrub_content(str(result_content))[:500],
                metadata={
                    "tool_name": block.name,
                    "duration_ms": tool_ms,
                    "result_len": len(str(result_content)),
                },
            )

        print(f"[工具结果] {str(result_content)[:200]}")
        return tool_call, str(result_content)

    async def _execute_tools(self, content_blocks: list, parent=None) -> list[dict]:
        """
        并发执行 Claude 响应中的所有 tool_use 块。
        返回格式符合 Anthropic API 规范的 tool_result 列表（顺序与输入一致）。
        """
        tool_use_blocks = [b for b in content_blocks if b.type == "tool_use"]
        if not tool_use_blocks:
            return []

        results = await asyncio.gather(
            *(self._execute_single_tool(block, parent=parent)
              for block in tool_use_blocks)
        )

        tool_results = []
        for block, (tool_call, result_content) in zip(tool_use_blocks, results):
            self.state.tool_history.append(
                ToolResult(tool_call=tool_call, result=result_content)
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_content,
            })

        return tool_results

    def _extract_text(self, content_blocks: list) -> str:
        """从响应内容块中提取纯文本"""
        texts = [b.text for b in content_blocks if hasattr(b, "text")]
        return "\n".join(texts) if texts else "（无文本输出）"

    # ── 基于上下文的问答（供 RAGAS 评估使用）──────────────────────────────────

    def generate_from_contexts(self, question: str, contexts: list[str]) -> str:
        """
        基于预检索的文档片段生成回答，不经过 ReAct 工具调用循环。
        供 RAGAS 评估等需要可控检索的场景使用——评估脚本负责检索，
        Agent 负责用自身的 LLM 和 system prompt 生成回答。

        返回：LLM 生成的回答文本。
        """
        if not contexts:
            return "根据提供的文档片段，无法回答此问题。"

        ctx_block = "\n\n---\n\n".join(
            f"[片段{i+1}] {c}" for i, c in enumerate(contexts)
        )
        prompt = (
            f"请严格基于下面提供的文档片段回答用户的问题。\n"
            f"要求：\n"
            f"1. 如果片段中包含答案，直接回答并引用相关片段编号\n"
            f"2. 如果片段中部分包含答案，回答已知部分并说明哪些信息缺失\n"
            f"3. 如果片段中完全没有答案，诚实地说「根据提供的文档片段，无法回答此问题」，不要编造\n\n"
            f"文档片段：\n{ctx_block}\n\n"
            f"用户问题：{question}\n\n"
            f"请回答："
        )

        try:
            t_start = time.time()
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024 * 8,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._extract_text(response.content)
            gen_ms = round((time.time() - t_start) * 1000)

            # ── LangFuse Generation ──────────────────────────────────────
            if self._lf is not None:
                try:
                    lf_gen = self._lf.start_observation(
                        name="llm.generate_from_contexts",
                        as_type="generation",
                        model=MODEL,
                        input=scrub_content(prompt)[:500],
                        metadata={
                            "context_count": len(contexts),
                            "input_chars": len(prompt),
                            "output_chars": len(result),
                            "duration_ms": gen_ms,
                        },
                    )
                    lf_gen.update(output=scrub_content(result)[:500])
                    lf_gen.end()
                except Exception:
                    pass

            return result
        except Exception as e:
            return f"（生成错误：{e}）"

    def reset(self):
        """重置对话，开始新会话"""
        self.state = AgentState()
        print("[会话已重置]")
