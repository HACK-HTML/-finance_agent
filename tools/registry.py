"""
工具实现 — Agent 的全部"技能"
每个工具函数都是纯 Python，与 Agent 框架完全解耦
工具注册表 TOOL_REGISTRY 负责名字 → 函数的映射
"""

import json
import random
import math
from datetime import datetime
from typing import Callable, Any
from models.schemas import BudgetCritique
from tools.budget_plan import _initial_ratios, _compute_plan, _critique_plan, _render_plan
# ★ Week1 Day1-2：把 Agentic RAG 检索作为标准工具接入
from tools.retrieve_tool import retrieve_document, RETRIEVE_DOCUMENT_SCHEMA


# ── 1. 财务计算工具 ────────────────────────────────────────────────────────────

def calculate(expression: str) -> str:
    """
    安全地计算数学表达式。
    LLM 不应该自己做算术，必须通过工具，防止计算幻觉。
    """
    # 只允许安全的字符，防止代码注入
    allowed = set("0123456789+-*/()., %")
    if not all(c in allowed for c in expression.replace(" ", "")):
        return f"错误：表达式包含不允许的字符"
    try:
        # 替换百分号为 /100
        expr = expression.replace("%", "/100")
        result = eval(expr, {"__builtins__": {}, "math": math})
        return f"{result:.4f}".rstrip("0").rstrip(".")
    except Exception as e:
        return f"计算错误：{e}"


def analyze_expenses(
    transactions_json: str,
    period: str = "本月"
) -> str:
    """
    分析一组交易数据，返回分类汇总和关键指标。
    transactions_json 格式：[{"category": "餐饮", "amount": 500, "description": "..."}, ...]
    """
    try:
        transactions = json.loads(transactions_json)
    except json.JSONDecodeError:
        return "错误：transactions_json 格式无效，需要 JSON 数组"

    income = sum(t["amount"] for t in transactions if t["amount"] < 0)
    expenses = sum(t["amount"] for t in transactions if t["amount"] > 0)

    # 按分类汇总支出
    by_category: dict[str, float] = {}
    for t in transactions:
        if t["amount"] > 0:
            cat = t.get("category", "未分类")
            by_category[cat] = by_category.get(cat, 0) + t["amount"]

    sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    total_income = abs(income)
    savings = total_income - expenses
    savings_rate = savings / total_income if total_income > 0 else 0

    lines = [
        f"📊 {period} 财务分析",
        f"  总收入：¥{total_income:,.2f}",
        f"  总支出：¥{expenses:,.2f}",
        f"  净储蓄：¥{savings:,.2f}",
        f"  储蓄率：{savings_rate:.1%}",
        f"\n📌 支出分类排行：",
    ]
    for cat, amt in sorted_cats:
        pct = amt / expenses * 100 if expenses > 0 else 0
        lines.append(f"  {cat:<8} ¥{amt:>8,.2f}  ({pct:.1f}%)")

    if sorted_cats:
        lines.append(f"\n⚠️  最大支出项：{sorted_cats[0][0]}（占总支出 {sorted_cats[0][1]/expenses:.1%}）")

    return "\n".join(lines)


def evaluate_financial_health(
    monthly_income: float,
    monthly_expense: float,
    total_savings: float,
    monthly_debt_payment: float = 0.0,
) -> str:
    """
    根据标准财务指标评估财务健康度，给出评分和建议。
    使用 50/30/20 法则、储蓄率基准、债务收入比等标准。
    """
    savings_rate = (monthly_income - monthly_expense) / monthly_income if monthly_income > 0 else 0
    debt_to_income = monthly_debt_payment / monthly_income if monthly_income > 0 else 0
    emergency_months = total_savings / monthly_expense if monthly_expense > 0 else 0

    score = 50  # 基础分
    issues = []
    positives = []

    # 储蓄率评分（满分 30 分）
    if savings_rate >= 0.2:
        score += 30
        positives.append(f"储蓄率 {savings_rate:.1%} 达到20%基准线 ✓")
    elif savings_rate >= 0.1:
        score += 15
        issues.append(f"储蓄率 {savings_rate:.1%} 偏低，建议提升至 20%")
    else:
        issues.append(f"储蓄率仅 {savings_rate:.1%}，财务风险较高")

    # 应急资金评分（满分 15 分）
    if emergency_months >= 6:
        score += 15
        positives.append(f"应急资金可支撑 {emergency_months:.1f} 个月 ✓")
    elif emergency_months >= 3:
        score += 8
        issues.append(f"应急资金仅 {emergency_months:.1f} 个月，建议存够 6 个月")
    else:
        issues.append(f"应急资金严重不足（{emergency_months:.1f} 个月），优先补充")

    # 债务评分（满分 5 分）
    if debt_to_income <= 0.15:
        score += 5
    elif debt_to_income <= 0.36:
        issues.append(f"债务收入比 {debt_to_income:.1%}，注意控制")
    else:
        score -= 10
        issues.append(f"债务负担过重（{debt_to_income:.1%}），优先还款")

    score = max(1, min(100, score))

    grade = (
        "🟢 优秀" if score >= 80 else
        "🟡 良好" if score >= 60 else
        "🟠 需改善" if score >= 40 else
        "🔴 危险"
    )

    lines = [
        f"💯 财务健康评分：{score}/100  {grade}",
        f"\n✅ 优势：" + ("、".join(positives) if positives else "暂无明显优势"),
        f"\n⚠️  待改善：",
    ]
    for issue in issues:
        lines.append(f"  • {issue}")

    return "\n".join(lines)



# ── 5. 对外工具：自带反思循环，返回已审查的最终方案 ──
MAX_BUDGET_REVISIONS = 2

def generate_budget_plan(monthly_income, financial_goal="平衡储蓄与生活质量",
                         current_obligations="", _client=None):
    needs_pct, wants_pct, savings_pct, strategy = _initial_ratios(financial_goal)
    split = (0.4, 0.4, 0.2)
    extra_debt = 0.0
    plan = _compute_plan(monthly_income, needs_pct, wants_pct, savings_pct,
                         strategy, financial_goal, current_obligations,
                         savings_split=split, extra_debt_payment=extra_debt)

    review_log = []
    if _client is not None:
        for attempt in range(MAX_BUDGET_REVISIONS):
            critique = _critique_plan(_client, plan)
            # 无任何可采纳的修正建议 → 终止
            has_change = any([critique.suggested_ratios,
                              critique.suggested_savings_split,
                              critique.suggested_extra_debt is not None])
            if critique.ok or not has_change:
                if not critique.ok:
                    review_log.append(f"第{attempt+1}轮发现问题但无有效调整方案")
                break

            # 消化各类修正信号
            if critique.suggested_ratios:
                r = critique.suggested_ratios
                needs_pct, wants_pct, savings_pct = r.needs, r.wants, r.savings
            if critique.suggested_savings_split:
                s = critique.suggested_savings_split
                split = (s.emergency, s.investment, s.goal)
            if critique.suggested_extra_debt is not None:
                extra_debt = critique.suggested_extra_debt

            review_log.append(f"第{attempt+1}轮调整：{'; '.join(critique.issues)}")
            plan = _compute_plan(monthly_income, needs_pct, wants_pct, savings_pct,
                                 strategy + "·已优化", financial_goal, current_obligations,
                                 savings_split=split, extra_debt_payment=extra_debt)

    # ★ 审查记录只打印到日志，不进返回文本（上一步的修复，保留）
    if review_log:
        print("[budget review log]", " | ".join(review_log))

    return _render_plan(plan)


# ── 2. 市场数据工具（模拟）──────────────────────────────────────────────────────

def get_exchange_rate(from_currency: str, to_currency: str) -> str:
    """
    获取汇率（模拟数据，真实项目接外部 API）。
    演示：Agent 如何调用外部数据源工具。
    """
    mock_rates = {
        ("USD", "CNY"): 7.24,
        ("CNY", "USD"): 0.138,
        ("EUR", "CNY"): 7.85,
        ("CNY", "EUR"): 0.127,
        ("JPY", "CNY"): 0.048,
        ("CNY", "JPY"): 20.8,
        ("HKD", "CNY"): 0.927,
        ("CNY", "HKD"): 1.079,
        ("GBP", "CNY"): 9.15,
    }
    from_upper = from_currency.upper()
    to_upper = to_currency.upper()
    rate = mock_rates.get((from_upper, to_upper))

    if rate is None:
        # 尝试反向计算
        reverse = mock_rates.get((to_upper, from_upper))
        if reverse:
            rate = round(1 / reverse, 4)
        else:
            return f"暂不支持 {from_currency} → {to_currency} 的汇率查询"

    # 模拟轻微波动
    fluctuation = random.uniform(-0.002, 0.002)
    actual_rate = round(rate * (1 + fluctuation), 4)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        f"💱 汇率查询（{timestamp}）\n"
        f"  1 {from_upper} = {actual_rate} {to_upper}\n"
        f"  数据来源：模拟（真实项目请接 exchangerate-api.com）"
    )


def get_fund_info(fund_code: str) -> str:
    """
    查询基金/股票信息（模拟）。
    演示：同一类工具如何复用，降低上下文 Token 消耗（Select 操作）。
    """
    mock_funds = {
        "000001": {"name": "华夏成长混合", "nav": 1.842, "ytd": "+12.3%", "risk": "中风险"},
        "110022": {"name": "易方达消费行业", "nav": 4.215, "ytd": "+8.7%", "risk": "中高风险"},
        "SPY":    {"name": "S&P 500 ETF", "nav": 587.4, "ytd": "+23.1%", "risk": "中风险"},
        "QQQ":   {"name": "纳斯达克100 ETF", "nav": 512.8, "ytd": "+28.5%", "risk": "中高风险"},
    }
    info = mock_funds.get(fund_code.upper(), mock_funds.get(fund_code))
    if not info:
        return f"未找到代码 {fund_code} 的基金/股票信息（支持：000001/110022/SPY/QQQ）"

    nav_change = random.uniform(-0.02, 0.02)
    return (
        f"📈 {info['name']}（{fund_code.upper()}）\n"
        f"  净值/价格：{info['nav'] * (1 + nav_change):.3f}\n"
        f"  年初至今：{info['ytd']}\n"
        f"  风险等级：{info['risk']}\n"
        f"  ⚠️ 以上为模拟数据，不构成投资建议"
    )


# ── 3. 工具注册表 ──────────────────────────────────────────────────────────────
# 名字 → 函数，Agent 通过名字查找并调用

TOOL_REGISTRY: dict[str, Callable[...,Any]] = {
    "calculate":               calculate,
    "analyze_expenses":        analyze_expenses,
    "evaluate_financial_health": evaluate_financial_health,
    "generate_budget_plan":    generate_budget_plan,
    "get_exchange_rate":       get_exchange_rate,
    "get_fund_info":           get_fund_info,
    "retrieve_document":       retrieve_document,   # ★ 新增：文档检索工具
}


# ── 4. 工具 Schema（告诉 Claude 每个工具的签名和用途）────────────────────────────
# 这是 Anthropic Function Calling 的关键：描述越清晰，Agent 调用越准确

TOOL_SCHEMAS = [{
    "name": "calculate",
    "description": "执行精确的纯数值数学计算。触发时机：当需要进行任何金额核算、比例计算或多步加减乘除时，必须调用此工具，绝对禁止模型自行心算。负向约束：仅支持纯数字与基础运算符(+, -, *, /, (), **)，严禁传入任何字母、变量名、等号(=)或编程语言内置函数。注意：绝对不要在表达式中包含 '计算' 或 'x=' 等非数学字符。",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "需要计算的纯数学表达式。必须是可以直接被数学引擎解析的算式。",
                "pattern": "^[0-9+\\-*/().\\s]+$"
            }
        },
        "required": ["expression"]
    },
    "input_examples": [
        {
            "expression": "(5000 - 3200) / 5000"
        },
        {
            "expression": "1200 * 12.5"
        },
        {
            "expression": "10000 * (1 + 0.05) ** 3"
        }
    ]
}, {
    "name": "analyze_expenses",
    "description": "分析一组交易数据，输出分类汇总、储蓄率、支出排行等关键指标。触发时机：当用户提供了多笔交易明细、询问消费结构或某段时间的收支概况时调用。负向约束：绝对禁止模型自行对交易数据做分类汇总或心算储蓄率，必须通过此工具完成；transactions_json 必须是合法的 JSON 数组字符串，空数组或格式错误将被拒绝。",
    "input_schema": {
        "type": "object",
        "properties": {
            "transactions_json": {
                "type": "string",
                "description": "JSON 数组字符串。每项含 category(消费分类)、amount(正数=支出/负数=收入)、description(备注)。",
                "pattern": "^\\s*\\[.*\\]\\s*$"
            },
            "period": {
                "type": "string",
                "description": "分析周期描述，如 '2024年12月' 或 '本月'",
                "default": "本月"
            }
        },
        "required": ["transactions_json"]
    },
    "input_examples": [
        {
            "transactions_json": "[{\"category\":\"餐饮\",\"amount\":500,\"description\":\"周末聚餐\"},{\"category\":\"交通\",\"amount\":200,\"description\":\"地铁充值\"},{\"category\":\"工资\",\"amount\":-8000,\"description\":\"月薪\"}]",
            "period": "2024年12月"
        },
        {
            "transactions_json": "[{\"category\":\"娱乐\",\"amount\":300},{\"category\":\"购物\",\"amount\":1200,\"description\":\"衣服\"}]"
        }
    ]
}, {
    "name": "evaluate_financial_health",
    "description": "根据收支和储蓄情况评估财务健康度，输出 1-100 评分、等级和具体改善建议。触发时机：当用户询问自己的财务状况是否健康、风险评估、或想知道哪些方面需要改进时调用。负向约束：绝对禁止模型自行打分或编造评估结论，必须通过此工具基于 50/30/20 法则、储蓄率基准、债务收入比等标准指标进行客观评估；所有金额参数必须为正数。",
    "input_schema": {
        "type": "object",
        "properties": {
            "monthly_income": {
                "type": "number",
                "description": "月收入（税后到手），单位：元",
                "minimum": 0
            },
            "monthly_expense": {
                "type": "number",
                "description": "月总支出（含所有日常开销与固定支出），单位：元",
                "minimum": 0
            },
            "total_savings": {
                "type": "number",
                "description": "当前总储蓄 / 可随时调用的应急资金总额，单位：元",
                "minimum": 0
            },
            "monthly_debt_payment": {
                "type": "number",
                "description": "每月债务还款总额（房贷、车贷、信用卡分期等），无债务填 0",
                "default": 0,
                "minimum": 0
            }
        },
        "required": ["monthly_income", "monthly_expense", "total_savings"]
    },
    "input_examples": [
        {
            "monthly_income": 15000,
            "monthly_expense": 12000,
            "total_savings": 50000,
            "monthly_debt_payment": 2000
        },
        {
            "monthly_income": 8000,
            "monthly_expense": 7500,
            "total_savings": 10000
        }
    ]
}, {
    "name": "generate_budget_plan",
    "description": "根据月收入和财务目标，基于 50/30/20 法则生成个性化预算分配方案。触发时机：当用户需要预算规划、收入分配建议、制定省钱/还债/投资计划时调用。负向约束：绝对禁止模型自行计算或估算预算分配比例，必须通过此工具动态生成；financial_goal 必须从预设选项中选取，monthly_income 必须为正数。",
    "input_schema": {
        "type": "object",
        "properties": {
            "monthly_income": {
                "type": "number",
                "description": "月收入（税后到手），单位：元",
                "minimum": 0
            },
            "financial_goal": {
                "type": "string",
                "description": "核心财务目标，系统将据此动态调整预算分配策略（激进储蓄型 / 还债优先型 / 均衡发展型）",
                "enum": ["买房", "存钱", "储蓄", "还债", "债务", "平衡储蓄与生活质量"]
            },
            "current_obligations": {
                "type": "string",
                "description": "当前固定支出或债务说明，如 '房租2000+车贷1500'，无则留空",
                "default": ""
            }
        },
        "required": ["monthly_income"]
    },
    "input_examples": [
        {
            "monthly_income": 12000,
            "financial_goal": "买房",
            "current_obligations": "房租2500"
        },
        {
            "monthly_income": 9000,
            "financial_goal": "平衡储蓄与生活质量"
        },
        {
            "monthly_income": 15000,
            "financial_goal": "还债",
            "current_obligations": "房贷4000+车贷1500"
        }
    ]
}, {
    "name": "get_exchange_rate",
    "description": "查询两种货币之间的实时汇率（当前为模拟数据）。触发时机：当用户需要进行货币换算、外币资产估值、跨境消费金额转换时调用。负向约束：绝对禁止模型自行估算或猜测汇率数值，必须通过此工具查询；仅支持系统中预定义的货币代码（USD/CNY/EUR/JPY/HKD/GBP），不支持的货币对将返回错误。",
    "input_schema": {
        "type": "object",
        "properties": {
            "from_currency": {
                "type": "string",
                "description": "源货币的三位 ISO 字母代码",
                "pattern": "^[A-Z]{3}$",
                "enum": ["USD", "CNY", "EUR", "JPY", "HKD", "GBP"]
            },
            "to_currency": {
                "type": "string",
                "description": "目标货币的三位 ISO 字母代码",
                "pattern": "^[A-Z]{3}$",
                "enum": ["USD", "CNY", "EUR", "JPY", "HKD", "GBP"]
            }
        },
        "required": ["from_currency", "to_currency"]
    },
    "input_examples": [
        {
            "from_currency": "USD",
            "to_currency": "CNY"
        },
        {
            "from_currency": "CNY",
            "to_currency": "JPY"
        },
        {
            "from_currency": "EUR",
            "to_currency": "USD"
        }
    ]
}, {
    "name": "get_fund_info",
    "description": "查询基金或股票的基本信息（净值、年初至今收益、风险等级），当前为模拟数据。触发时机：当用户询问某只基金/股票的表现、需要投资参考数据、或想了解特定标的的基本面时调用。负向约束：绝对禁止模型自行编造或猜测基金的净值、涨跌幅、风险等级等数据，必须通过此工具查询；仅支持系统中已录入的代码，不支持的代码将返回未找到提示。⚠️ 所有数据均为模拟，不构成投资建议。",
    "input_schema": {
        "type": "object",
        "properties": {
            "fund_code": {
                "type": "string",
                "description": "基金或股票代码",
                "enum": ["000001", "110022", "SPY", "QQQ"]
            }
        },
        "required": ["fund_code"]
    },
    "input_examples": [
        {
            "fund_code": "000001"
        },
        {
            "fund_code": "SPY"
        },
        {
            "fund_code": "110022"
        }
    ]
}, RETRIEVE_DOCUMENT_SCHEMA]

# ★ Week1 Day1-2：把文档检索工具的 schema 也告诉 Claude
