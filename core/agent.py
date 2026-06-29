"""
核心 Agent — 手写 ReAct 循环，无任何框架依赖
ReAct = Reasoning + Acting，每步：Think → Act（调用工具）→ Observe（看结果）→ 重复
"""
from pprint import pprint
from functools import partial
import json
import anthropic
import asyncio
from models.schemas import AgentState, ToolCall, ToolResult, ConversationTurn, MonthlyReport
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS, generate_budget_plan, retrieve_document, memory_recall
from memory import MemoryManager


# ── 常量 ──────────────────────────────────────────────────────────────────────
API_KEY='sk-9f690eab2b2340cdaf451dde1746830d'
API_CRITIC_KEY='sk-33d367956a054b1c8f5870667ff821d6'

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
    def __init__(self, session_id: str = "default", user_id: str | None = None):
        self.session_id = session_id          # 会话维度（消息历史 / 文档上传）
        self.user_id = user_id or session_id  # 用户维度（记忆 + 文档检索，跨会话共享）
        self.client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)
        self.state = AgentState()
        self._critic = anthropic.Anthropic(api_key=API_CRITIC_KEY, base_url=BASE_URL)
        self.memory = MemoryManager(self.user_id)
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
        # 1. 把用户消息加入历史
        self.state.messages.append({
            "role": "user",
            "content": user_input
        })

        iteration = 0

        while iteration < MAX_ITERATIONS:
            pprint(self.state.messages)

            iteration += 1
            print(f"\n{'─'*50}")
            print(f"[ReAct 第 {iteration} 轮]")

            # 2. 每轮动态拼 system prompt（注入相关记忆摘要）
            system = self._make_system_prompt(user_input)

            # 3. 调用 Claude，附带工具定义
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096 * 2,
                system=system,
                tools=TOOL_SCHEMAS,
                messages=self.state.messages,
            )

            print(f"[stop_reason] {response.stop_reason}")

            # 4. 把 Claude 的回复加入历史（必须在处理工具调用之前）
            self.state.messages.append({
                "role": "assistant",
                "content": response.content
            })

            # 5. 判断停止原因
            # end_turn = Claude 认为不需要工具，直接给出最终答案
            if response.stop_reason == "end_turn":
                final_text = self._extract_text(response.content)
                self.state.turns.append(
                    ConversationTurn(user=user_input, assistant=final_text)
                )
                print(f"[最终回答] 完成（共 {iteration} 轮 ReAct）")

                # ★ 异步存储记忆：fire-and-forget，不阻塞回答返回
                asyncio.create_task(
                    asyncio.to_thread(
                        self.memory.add_async,
                        f"用户：{user_input}\n助手：{final_text}"
                    )
                )
                return final_text

            # tool_use = Claude 决定调用一个或多个工具
            if response.stop_reason == "tool_use":
                tool_results = await self._execute_tools(response.content)

                # 6. 把工具执行结果作为 user 消息反馈给 Claude
                # 这就是 ReAct 中的 "Observe" 步骤
                self.state.messages.append({
                    "role": "user",
                    "content": tool_results
                })
                continue  # 进入下一轮，让 Claude 基于工具结果继续推理

            # 兜底：其他停止原因直接取文本
            final_text = self._extract_text(response.content)
            asyncio.create_task(
                asyncio.to_thread(
                    self.memory.add_async,
                    f"用户：{user_input}\n助手：{final_text}"
                )
            )
            return final_text

        return "已达到最大推理轮数，请简化问题后重试。"

    # ── 工具执行 ────────────────────────────────────────────────────────────────

    async def _execute_single_tool(self, block) -> tuple[ToolCall, str]:
        """执行单个工具调用，返回 (调用记录, 结果字符串)。永不抛异常。"""
        tool_call = ToolCall(
            tool_use_id=block.id,
            tool_name=block.name,
            tool_input=block.input,
        )

        print(f"[工具调用] {block.name}({json.dumps(block.input, ensure_ascii=False)})")

        tool_fn = self.tool_registry.get(block.name)
        if tool_fn is None:
            result_content = f"错误：工具 '{block.name}' 未注册"
        else:
            try:
                if asyncio.iscoroutinefunction(tool_fn):
                    result_content = await tool_fn(**block.input)
                else:
                    result_content = await asyncio.to_thread(tool_fn, **block.input)
            except Exception as e:
                result_content = f"工具执行出错：{str(e)}"

        print(f"[工具结果] {str(result_content)[:200]}")
        return tool_call, str(result_content)

    async def _execute_tools(self, content_blocks: list) -> list[dict]:
        """
        并发执行 Claude 响应中的所有 tool_use 块。
        返回格式符合 Anthropic API 规范的 tool_result 列表（顺序与输入一致）。
        """
        tool_use_blocks = [b for b in content_blocks if b.type == "tool_use"]
        if not tool_use_blocks:
            return []

        results = await asyncio.gather(
            *(self._execute_single_tool(block) for block in tool_use_blocks)
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

    def reset(self):
        """重置对话，开始新会话"""
        self.state = AgentState()
        print("[会话已重置]")
