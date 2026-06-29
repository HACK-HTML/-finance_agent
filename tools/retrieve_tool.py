"""
retrieve_document 工具 —— 把 Agentic RAG 检索封装成 Agent 的标准工具
====================================================================

这是 Week1 Day1-2 的核心交付：复用第一阶段的 TOOL_REGISTRY 机制，
让 Agent 能在「检索文档」和「调用计算/分析工具」之间自主选择。

⚠️ 踩坑提示（计划里点名的）：工具 description 必须把
   「什么时候该检索文档 vs 什么时候该用计算工具」写到位，否则 Agent 会混淆——
   把"算储蓄率"也丢给检索，或者把"产品费率是多少"硬算。
   下面的 description 用「触发时机 + 负向约束」双段式写法（和现有工具风格一致）。

★ Week1 Day 5 升级：Agentic RAG — Router（分类问题类型选策略）+ Critic（评估质量改查重检）
  两组件封装在 retrieve_document 内部，对 Agent ReAct 循环完全透明。
"""
from __future__ import annotations

import re

from tools.rag_pipeline import get_store, RetrievedChunk


# ── Router：根据问题类型选择检索策略 ──────────────────────────────────────────

class QueryRouter:
    """中文财务查询分类器：精确查找 vs 概括总结。"""

    # 精确查找信号：具体费率/数字/条款引用
    _EXACT_RE = re.compile(
        r'(费率|手续费|赎回|买入|卖出|价格|净值|利率|年化|收益率|'
        r'比例|百分点|数值|数据|指标|日期|时间|截止|编号|代码|'
        r'第[一二三四五六七八九十\d]+[章节条款项]|'
        r'是什么|什么是|定义|含义|具体|'
        r'多少|几%|百分之|金额)'
    )

    # 概括总结信号：整体了解/归纳/评估
    _SUMMARY_RE = re.compile(
        r'(总结|概括|归纳|汇总|概述|综述|整体|全局|全面|'
        r'主要|核心|关键|重点|'
        r'(介绍|说明|描述).*(产品|基金|策略|方案|风险)|'
        r'(怎么样|如何|怎么).*(投资|理财|规划|配置))'
    )

    @classmethod
    def classify(cls, query: str) -> str:
        """根据查询内容分类为 'exact' 或 'summary'。"""
        if cls._SUMMARY_RE.search(query):
            return "summary"
        return "exact"  # 默认精确查找（更保守）

    @classmethod
    def get_strategy(cls, query_type: str) -> dict:
        """返回对应策略的检索参数。"""
        if query_type == "summary":
            return {"top_k": 30, "top_n": 7}
        return {"top_k": 20, "top_n": 5}


# ── Critic：评估检索质量，不足则改写查询重检 ────────────────────────────────

class RetrievalCritic:
    """利用重排序分数评估检索质量，不合格时改写查询（最多 1 次重试）。"""

    MIN_AVG_SCORE: float = 0.3    # 平均分低于此 → 整体相关性弱
    MIN_MAX_SCORE: float = 0.5    # 最高分低于此 → 最好片段也差

    @staticmethod
    def evaluate(chunks: list[RetrievedChunk]) -> tuple[bool, str]:
        """返回 (是否合格, 原因标签)。"""
        if not chunks:
            return False, "no_results"

        scores = [c.score for c in chunks]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)

        issues = []
        if avg_score < RetrievalCritic.MIN_AVG_SCORE:
            issues.append(f"avg_low({avg_score:.2f})")
        if max_score < RetrievalCritic.MIN_MAX_SCORE:
            issues.append(f"max_low({max_score:.2f})")

        return (False, ",".join(issues)) if issues else (True, "ok")

    @staticmethod
    def reformulate(original: str, reason: str) -> str:
        """基于失败原因改写查询，返回空串表示无需重试。"""
        if reason == "no_results":
            # 截断问句后缀，保留核心关键词
            shortened = re.sub(r'[？?!！。.，,；;：:].*', '', original).strip()
            return shortened if len(shortened) >= 4 else original[:20]

        # 分数低 → 注入金融领域关键词增强语义匹配
        if not re.search(r'(理财|基金|投资|财务|费率|收益|风险|金融|产品|保险|股票|债券)', original):
            return f"理财产品 金融文档 {original}"

        return ""  # 已有领域词，不重复改写


# ── 工具函数 ────────────────────────────────────────────────────────────────

def retrieve_document(query: str, *, user_id: str = "default") -> str:
    """
    在用户上传的财务文档（理财产品说明书 / 账单 / 年报等）里做语义检索，
    返回最相关的若干原文片段（带来源与页码，便于回答时引用）。

    内部流程（Week1 Day5）：Router 分类 → 初检 → Critic 评估 → 可能改写重检。

    user_id 是「隐藏参数」：由 Agent 在注册时用 functools.partial 绑定，
    不暴露给 LLM，因此模型只会传 `query`（与 generate_budget_plan 绑定 _client 同理）。
    ★ Day 3-4 修复：从 session_id 改为 user_id，和记忆用同一隔离维度。
    """
    store = get_store()

    if not store.has_documents(user_id):
        return ("【知识库为空】当前用户还没有上传任何文档，无法检索。"
                "请提示用户先上传财务文档（PDF），或改用计算/分析类工具回答通用问题。")

    # ── Router：分类问题类型，选择检索策略 ──
    query_type = QueryRouter.classify(query)
    strategy = QueryRouter.get_strategy(query_type)

    # ── 第一轮检索 ──
    chunks: list[RetrievedChunk] = store.retrieve(
        query, user_id=user_id,
        top_k=strategy["top_k"], top_n=strategy["top_n"],
    )

    # ── Critic：评估质量，不足则改写查询重检索 ──
    ok, reason = RetrievalCritic.evaluate(chunks)
    if not ok:
        revised = RetrievalCritic.reformulate(query, reason)
        if revised and revised != query:
            chunks = store.retrieve(
                revised, user_id=user_id,
                top_k=max(strategy["top_k"], 30),
                top_n=strategy["top_n"],
            )

    if not chunks:
        return (f"【未检索到相关内容】文档里没有与「{query}」直接相关的片段。"
                "可以换个说法再检索，或如实告诉用户文档中未涉及该信息——不要编造。")

    lines = [f"📚 文档检索结果（query=「{query}」｜策略={query_type}｜按相关性排序）：", ""]
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
