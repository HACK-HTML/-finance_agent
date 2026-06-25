"""
核心 Agent — 手写 ReAct 循环，无任何框架依赖
ReAct[Reasoning->Act]:think->act->observation-> reloop
"""

from pprint import pprint
import json
import anthropic
from models.schemas import AgentState, ToolCall, ToolResult, ConversationTurn
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS

MODEL="deepseek-v4-pro"
MAX_ITERATION=10
TASK_PROMPT="""
你是一个专业的个人财务分析助手。你能帮用户：
- 分析收支数据，计算关键指标（储蓄率、消费占比等）
- 查询实时汇率或模拟股票数据
- 制定预算方案并评估财务健康度
- 多轮追问，持续深入分析
"""
TASK_DESCRIPTION="""
工作原则：
1. 先思考需要哪些信息，一步一步思考，再决定调用哪个工具
2. 工具返回结果后，判断是否需要继续调用或可以给出最终答案
3. 数字计算必须使用 calculate 工具，不要心算
4. 回答要具体，给出可操作的建议
5. 允许在最终结果阶段给出无法回答客户问题的回答，做出礼貌的道歉，并告知用户问题无法解决
"""
TONE_PROMPT="""
语气要求：
-采用友好的语气回答用户的问题
"""
INPUT_DATA=""""""
EXAMPLES=""""""
PRECOGNITION=""""""
OUTPUT_FORMATTING=""""""

SYSTEM_PROMPT=""

if TASK_PROMPT:
    SYSTEM_PROMPT+=f"""{TASK_PROMPT}"""
if TASK_DESCRIPTION:
    SYSTEM_PROMPT+=f"""{TASK_DESCRIPTION}"""
if TONE_PROMPT:
    SYSTEM_PROMPT+=f"""{TONE_PROMPT}"""
if EXAMPLES:
    SYSTEM_PROMPT+=f"""{EXAMPLES}"""
if PRECOGNITION:
    SYSTEM_PROMPT+=f"""{PRECOGNITION}"""
if OUTPUT_FORMATTING:
    SYSTEM_PROMPT+=f"""{OUTPUT_FORMATTING}"""
pprint(SYSTEM_PROMPT)

class FinanceAgent:
    def __init__(self):
        self.clint=anthropic.Anthropic()
        self.state=AgentState()
    def chat(self, user_input: str)->str:
        """
            接收用户消息，执行完整 ReAct 循环，返回最终回答。
            循环结构：
                用户消息 → Claude 思考 → [工具调用 → 观察结果]* → 最终回答
        """
        # 1.追加用户消息到 state.messsages
        self.state.messages.append(
            {
                "role":"user",
                "context":user_input
            }
        )
        iterations=0
        while iterations<MAX_ITERATION:
            iterations+=1
            pprint(f"\n{'─' * 50}")
            pprint(f"[ReAct 第 {iterations} 轮]")

            # 2.调用ds-v4p,设置系统提示词,工具定义
            response=self.clint.messages.create(
                model=MODEL,
                system=SYSTEM_PROMPT,
                max_tokens=1024*8,
                tools=TOOL_SCHEMAS,
                messages = self.state.messages,
            )

            pprint(f"[stop_reason] {response.stop_reason}")

            # 3. 将消息加入队列
            self.state.messages.append(
                {
                    "role":"assistant",
                    "context":response.content
                }
            )

            # 4.停止逻辑
            # 4.1 agent决定停止，不在需要工具
            if response.stop_reason=="end_turn":
                final_text=self._extract_text(response.content)
                self.state.turns.append(ConversationTurn(
                    user=user_input,
                    assistant=final_text
                ))
                pprint(f"[最终回答] 完成（共 {iterations} 轮 ReAct）")
                pprint(f"[最终回答] {final_text}")
            # 4.2 agent调用一个或者多个工具
            if response.stop_reason=="tool_use":
                tool_results = self._execute_tools(response.content)
                self.state.messages.append({
                    "role": "user",
                    "content": tool_results
                })
                continue
            # 兜底：其他停止原因直接取文本
            return self._extract_text(response.content)
        return "达到最大循环数，非常抱歉无法解决您的问题"

                 
    def _extract_text(self, content_blocks: list) -> str:
        """从响应内容块中提取纯文本"""
        texts = [b.text for b in content_blocks if hasattr(b, "text")]
        return "\n".join(texts) if texts else "（无文本输出）"
    def _execute_tools(self,content_blocks:list)->list[dict]:
        """
        遍历response中的所有内容块，选取tool_use块
        返回格式符合 Anthropic API 规范的 tool_result 列表。
        """
        tool_results=[]
        for content_block in content_blocks:
            if content_block.type!="tool_use":
                continue

            tool_call=ToolCall(
                tool_use_id=content_block.id,
                tool_name=content_block.name,
                tool_input=content_block.input,
            )

            pprint(f"[工具调用] {content_block.name}({json.dumps(content_block.input, ensure_ascii=False)})")
            # 检查工具是否注册，并执行
            tool_fn = TOOL_REGISTRY.get(content_block.name)
            if tool_fn is None:
                result_content = f"错误：工具 '{content_block.name}' 未注册"
            else:
                try:
                    result_content = tool_fn(**content_block.input)
                except Exception as e:
                    result_content = f"工具执行出错：{str(e)}"
            # 记录工具调用历史
            self.state.tool_history.append(
                ToolResult(
                    tool_call=tool_call,
                    result=result_content
                )
            )
            # 构建符合 API 规范的 tool_result 块
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": content_block.id,
                "content": str(result_content),
            })
        return tool_results

