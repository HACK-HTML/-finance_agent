"""
数据模型 — 用 Pydantic 强类型约束所有关键数据结构
目的：学习如何用 Pydantic 验证 LLM 的结构化输出，防止脏数据进入业务逻辑
"""
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict
from datetime import datetime


# ── 工具调用 ──────────────────────────────────────────────────────────────────
class ToolCall(BaseModel):
    """
    继承BaseModel,记录一次工具调用的入参
    Attributes:
        tool_id:
        tool_name:
        tool_input:
        call_at:
    """
    tool_id: str
    tool_name: str
    tool_input:dict[str, Any]
    call_at: datetime=Field(default_factory=datetime.now)

class ToolResult(BaseModel):
    """
    记录一次工具调用的结果
    Attributes:
        tool_call:
        tool_result:
        success:
    """
    tool_call: ToolCall
    tool_result: str
    success: bool = True

# ── 财务数据模型 ───────────────────────────────────────────────────────────────
class Transaction(BaseModel):
    """
    单笔交易记录
    Attributes:
        category:
        amount:
        description:
    """
    category:str=Field(description="单笔交易的分类")
    amount: float = Field(description="金额，正数为支出，负数为收入")
    description: str = Field(default="", description="备注")

    @field_validator("amount")
    def amount_validator(cls, v:float) -> float:
        if v<=0:
            raise ValueError("金额不能为0,小于0")
        return round(v,2)


class MonthlyReport(BaseModel):
    """
    月度财务报告
    Attributes:
        month:
        total_income:
        total_expense:
        savings_rate:
        top_category:
        health_score:
        suggestions:

    """
    month: int=Field(description="记录财报月份,eg:2026-5")
    total_income: float
    total_expense: float
    savings_rate: float = Field(description="储蓄率，0-1 之间")
    top_category: str = Field(description="最大支出分类")
    health_score: int = Field(description="财务健康评分 1-100", ge=1, le=100)
    suggestions: list[str] = Field(description="改善建议，3-5 条")

    @field_validator("savings_rate")
    @classmethod
    def savings_rate_validator(cls, v:float) -> float:
        if not v>=0 and v<=1:
            raise ValueError("储蓄率必须在0-1之间")
        return round(v,2)

class BudgetPlan(BaseModel):
    """
    预算方案
    Attributes:
        monthly_income
        allocations:
    """
    monthly_income: float
    allocations: dict[str, float] = Field(
        description="各分类预算分配，key 为分类名，value 为金额"
    )
    emergency_fund_months: float = Field(description="应急资金可支撑月数")
    investment_suggestion: str

# ── Agent 状态 ─────────────────────────────────────────────────────────────────
class ConversationTurn(BaseModel):
    """
    一轮完整对话
    Attributes:
        user:
        assistant:
        timestamp:
    """
    user: str
    assistant: str
    timestamp: datetime = Field(default_factory=datetime.now)
class AgentState(BaseModel):
    """
    Agent 运行时状态 — 核心是 messages 列表
    messages 就是传给 Anthropic API 的完整对话历史
    Attributes:
        messages:
        tool_history:
        turns:
    """
    messages:list[dict[str,Any]] = Field(default_factory=list)
    tool_history: list[ToolResult] = Field(default_factory=list)
    turns: list[ConversationTurn] = Field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)
    @property
    def tool_count(self) -> int:
        return len(self.tool_history)
    def summary(self) -> str:
        return (
            f"对话轮数: {self.turn_count} | "
            f"工具调用: {self.tool_count} | "
            f"消息数: {len(self.messages)}"
        )
