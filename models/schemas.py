"""
数据模型 — 用 Pydantic 强类型约束所有关键数据结构
目的：学习如何用 Pydantic 验证 LLM 的结构化输出，防止脏数据进入业务逻辑
"""

from pydantic import BaseModel, Field, field_validator
from typing import Any
from datetime import datetime


# ── 工具调用 ──────────────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    """
    记录一次工具调用的入参

    Attributes:
        tool_use_id:工具调用id


    """
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    called_at: datetime = Field(default_factory=datetime.now)


class ToolResult(BaseModel):
    """记录一次工具调用的完整信息（入参 + 结果）"""
    tool_call: ToolCall
    result: str
    success: bool = True


# ── 财务数据模型 ───────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    """单笔交易记录"""
    category: str = Field(description="消费分类，如 餐饮/交通/娱乐/储蓄")
    amount: float = Field(description="金额，正数为支出，负数为收入")
    description: str = Field(default="", description="备注")

    @field_validator("amount")
    @classmethod
    def amount_not_zero(cls, v: float) -> float:
        if v == 0:
            raise ValueError("金额不能为 0")
        return round(v, 2)


class MonthlyReport(BaseModel):
    """月度财务报告 — Claude 结构化输出的目标格式"""
    month: str = Field(description="如 2025-01")
    total_income: float
    total_expense: float
    savings_rate: float = Field(description="储蓄率，0-1 之间")
    top_category: str = Field(description="最大支出分类")
    health_score: int = Field(description="财务健康评分 1-100", ge=1, le=100)
    suggestions: list[str] = Field(description="改善建议，3-5 条")

    @field_validator("savings_rate")
    @classmethod
    def valid_rate(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("储蓄率必须在 0 到 1 之间")
        return round(v, 4)


class BudgetPlan(BaseModel):
    """预算方案 — Claude 结构化输出"""
    monthly_income: float
    allocations: dict[str, float] = Field(
        description="各分类预算分配，key 为分类名，value 为金额"
    )
    emergency_fund_months: float = Field(description="应急资金可支撑月数")
    investment_suggestion: str


class MemorySummary(BaseModel):
    """从记忆库中召回的一条用户信息——用于注入 system prompt 或评估统计"""
    content: str = Field(description="记忆内容摘要")
    score: float = Field(description="相关性分数 0-1", ge=0, le=1)
    recalled_at: datetime = Field(default_factory=datetime.now)


from pydantic import BaseModel, Field, model_validator
from typing import Optional


class SuggestedRatios(BaseModel):
    needs: float = Field(ge=0, le=1)
    wants: float = Field(ge=0, le=1)
    savings: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum(self):
        if abs(self.needs + self.wants + self.savings - 1.0) > 0.02:
            raise ValueError("三类比例之和必须约等于 1")
        return self


class SuggestedSavingsSplit(BaseModel):
    """储蓄内部三项权重，和为1。"""
    emergency: float = Field(ge=0, le=1)
    investment: float = Field(ge=0, le=1)
    goal: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum(self):
        if abs(self.emergency + self.investment + self.goal - 1.0) > 0.02:
            raise ValueError("储蓄三项权重之和必须约等于 1")
        return self

class BudgetCritique(BaseModel):
    ok: bool = Field(description="预算是否合理")
    issues: list[str] = Field(default_factory=list, description="发现的问题；合理则为空")
    suggested_ratios: Optional[SuggestedRatios] = Field(
        default=None, description="修正后的三大类比例；无需调整则 null")
    suggested_savings_split: Optional[SuggestedSavingsSplit] = Field(
        default=None, description="修正后的储蓄内部权重（应急/投资/专项）；"
                                  "如买房目标应提高 goal、降低 investment。无需调整则 null")
    suggested_extra_debt: Optional[float] = Field(
        default=None, ge=0, description="建议的每月额外加速偿债金额（元）；"
                                        "还债目标下应 >0。无需调整则 null")

    @model_validator(mode="after")
    def _coherence(self):
        if not self.ok and not self.issues:
            raise ValueError("ok=false 时必须说明 issues")
        return self

# ── Agent 状态 ─────────────────────────────────────────────────────────────────

class ConversationTurn(BaseModel):
    """一轮完整对话"""
    user: str
    assistant: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentState(BaseModel):
    """
    Agent 运行时状态 — 核心是 messages 列表
    messages 就是传给 Anthropic API 的完整对话历史
    """
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_history: list[ToolResult] = Field(default_factory=list)
    turns: list[ConversationTurn] = Field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def total_tool_calls(self) -> int:
        return len(self.tool_history)

    def summary(self) -> str:
        return (
            f"对话轮数: {self.turn_count} | "
            f"工具调用: {self.total_tool_calls} | "
            f"消息数: {len(self.messages)}"
        )
