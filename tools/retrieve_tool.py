"""
retrieve_document 工具 —— 把 Agentic RAG 检索封装成 Agent 的标准工具
====================================================================

这是 Week1 Day1-2 的核心交付：复用第一阶段的 TOOL_REGISTRY 机制，
让 Agent 能在「检索文档」和「调用计算/分析工具」之间自主选择。

⚠️ 踩坑提示（计划里点名的）：工具 description 必须把
   「什么时候该检索文档 vs 什么时候该用计算工具」写到位，否则 Agent 会混淆——
   把"算储蓄率"也丢给检索，或者把"产品费率是多少"硬算。
   下面的 description 用「触发时机 + 负向约束」双段式写法（和现有工具风格一致）。
"""
from __future__ import annotations

from tools.rag_pipeline import get_store, RetrievedChunk


def retrieve_document(query: str, *, user_id: str = "default") -> str:
    """
    在用户上传的财务文档（理财产品说明书 / 账单 / 年报等）里做语义检索，
    返回最相关的若干原文片段（带来源与页码，便于回答时引用）。

    user_id 是「隐藏参数」：由 Agent 在注册时用 functools.partial 绑定，
    不暴露给 LLM，因此模型只会传 `query`（与 generate_budget_plan 绑定 _client 同理）。
    ★ Day 3-4 修复：从 session_id 改为 user_id，和记忆用同一隔离维度。
    同一用户的不同 session 共享文档检索结果。
    """
    store = get_store()

    if not store.has_documents(user_id):
        return ("【知识库为空】当前用户还没有上传任何文档，无法检索。"
                "请提示用户先上传财务文档（PDF），或改用计算/分析类工具回答通用问题。")

    chunks: list[RetrievedChunk] = store.retrieve(query, user_id=user_id)
    if not chunks:
        return (f"【未检索到相关内容】文档里没有与「{query}」直接相关的片段。"
                "可以换个说法再检索，或如实告诉用户文档中未涉及该信息——不要编造。")

    lines = [f"📚 文档检索结果（query=「{query}」，按相关性排序）：", ""]
    for i, c in enumerate(chunks, 1):
        loc = f"{c.source}" + (f" · 第{c.page}页" if c.page else "")
        lines.append(f"[片段{i}] 来源：{loc}｜相关性 {c.score:.2f}")
        lines.append(c.text.strip())
        lines.append("")
    lines.append("——以上为原文片段。回答时请基于这些内容作答，并标注来源；"
                 "片段中没有的信息不要臆造。")
    return "\n".join(lines)


# ── 工具 Schema：给 Claude 看的「说明书」──────────────────────────────────────────
RETRIEVE_DOCUMENT_SCHEMA = {
    "name": "retrieve_document",
    "description": (
        "在『用户上传的财务文档』内做语义检索，取回最相关的原文片段。"
        "触发时机：当问题的答案需要依赖具体某份文档的内容时调用——例如询问"
        "理财产品的费率/赎回规则/风险等级、年报里的某项数据、账单上的某笔交易明细、"
        "合同条款、产品说明书里的具体约定等『文档里才有、模型无法凭空知道』的信息。"
        "负向约束：①不要用它做数学计算或比例核算（那是 calculate / analyze_expenses / "
        "evaluate_financial_health 的职责）；②不要用它查实时汇率或基金行情"
        "（那是 get_exchange_rate / get_fund_info）；③通用理财常识、定义性问题"
        "无需检索，直接回答即可。一句话：只有当答案藏在用户的文档里时才检索。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "检索用的自然语言问题或关键词，尽量贴近文档用语。"
                    "如『XX 理财产品的赎回费率是多少』『年报中第三季度净利润』。"
                ),
            }
        },
        "required": ["query"],
    },
    "input_examples": [
        {"query": "这款理财产品的赎回手续费怎么算"},
        {"query": "产品风险等级和适合的投资者类型"},
        {"query": "账单里餐饮类的总支出和明细"},
    ],
}
