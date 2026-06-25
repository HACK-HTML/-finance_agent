"""
实现agent需要的所有函数工具
所有工具采用纯python实现
TOOL_REGISTRY - 工具注册表 注册工具，实现从函数名到函数的映射
TOOL_SCHEMAS - 工具描述，越精准越好，LLM就能越准确选择工具，并正确的调用工具
"""
import json
import random
import math
from datetime import datetime
from typing import Any, Callable, Annotated
import inspect
from pydantic import Field,create_model
from pprint import pprint


# ── 1. 财务计算工具 ────────────────────────────────────────────────────────────

def calculate(
        expression: Annotated[str,Field(description="数学表达式，如 '(5000 - 3200) / 5000' 或 '1200 * 12'")]) -> str:
    """
     安全计算数学表达式，支持 +−×÷ 和括号。所有需要计算的数字运算必须通过此工具，不要自行心算。
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
    transactions_json: Annotated[str,Field(description="""transactions_json 格式：[{"category": "餐饮", "amount": 500, "description": "..."}, ...]""")],
    period: Annotated[str,Field(description="进行财务分析的月份，例如一月，二月，默认为本月")]="本月"
) -> str:
    """
    分析一组交易数据，返回分类汇总和关键指标。
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
        monthly_income: Annotated[
            float,
            Field(description="用户的月总收入金额（税后实际到手收入）")
        ],
        monthly_expense: Annotated[
            float,
            Field(description="用户的月总支出金额（包含所有日常开销与固定支出）")
        ],
        total_savings: Annotated[
            float,
            Field(description="用户当前的总储蓄或可随时调用的应急资金总额")
        ],
        monthly_debt_payment: Annotated[
            float,
            Field(description="每月的债务还款总额（如房贷、车贷、信用卡分期等），若无债务则为 0")
        ] = 0.0,
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


def generate_budget_plan(
        monthly_income: Annotated[
            float,
            Field(description="用户的月度总收入金额（单位：元），必须为正数。"),

        ],
        financial_goal: Annotated[
            str,
            Field(
                description="用户的核心财务目标，例如'买房'、'存钱'、'还债'或'平衡储蓄与生活质量'。系统将根据此目标动态调整预算分配策略。")
        ] = "平衡储蓄与生活质量",
        current_obligations: Annotated[
            str,
            Field(description="当前已有的固定支出或债务说明，例如'每月房贷4000元'。若无则留空。")
        ] = ""
) -> str:
    """
    根据收入和目标，生成个性化预算方案。
    使用 50/30/20 法则作为基础，根据目标调整比例。
    """
    goal_lower = financial_goal.lower()

    # 根据目标调整比例
    if "买房" in goal_lower or "存钱" in goal_lower or "储蓄" in goal_lower:
        needs_pct, wants_pct, savings_pct = 0.45, 0.20, 0.35
        strategy = "激进储蓄型"
    elif "还债" in goal_lower or "债务" in goal_lower:
        needs_pct, wants_pct, savings_pct = 0.50, 0.15, 0.35
        strategy = "还债优先型"
    else:
        needs_pct, wants_pct, savings_pct = 0.50, 0.30, 0.20
        strategy = "均衡发展型"

    needs = monthly_income * needs_pct
    wants = monthly_income * wants_pct
    savings = monthly_income * savings_pct

    # 细分各项
    plan = {
        "🏠 固定必要支出（住房+交通+饮食）": round(needs * 0.7, 0),
        "🏥 保险+医疗备用": round(needs * 0.2, 0),
        "📱 通讯+订阅服务": round(needs * 0.1, 0),
        "🎮 娱乐+社交": round(wants * 0.4, 0),
        "👗 购物+个人消费": round(wants * 0.35, 0),
        "📚 学习+成长": round(wants * 0.25, 0),
        "🏦 应急基金（优先补足6个月）": round(savings * 0.4, 0),
        "📈 长期投资（指数基金等）": round(savings * 0.4, 0),
        "🎯 目标专项存款": round(savings * 0.2, 0),
    }

    lines = [
        f"📋 {strategy}预算方案（月收入 ¥{monthly_income:,.0f}）",
        f"  目标：{financial_goal}",
        f"\n{'分类':<20} {'预算':>10}  {'占比':>6}",
        "─" * 42,
    ]
    for cat, amt in plan.items():
        pct = amt / monthly_income * 100
        lines.append(f"  {cat:<18} ¥{amt:>8,.0f}  {pct:>5.1f}%")

    lines.append("─" * 42)
    lines.append(f"  {'合计':<18} ¥{monthly_income:>8,.0f}  100.0%")

    if current_obligations:
        lines.append(f"\n💡 当前固定支出（{current_obligations}）需从固定必要支出中扣除")

    return "\n".join(lines)


# ── 2. 市场数据工具（模拟）──────────────────────────────────────────────────────

def get_exchange_rate(
        from_currency: Annotated[
            str,
            Field(
                description="源货币的三位字母代码，例如 'USD' (美元), 'CNY' (人民币), 'EUR' (欧元), 'JPY' (日元), 'HKD' (港币), 'GBP' (英镑)")
        ],
        to_currency: Annotated[
            str,
            Field(
                description="目标货币的三位字母代码，例如 'CNY' (人民币), 'USD' (美元), 'EUR' (欧元), 'JPY' (日元), 'HKD' (港币), 'GBP' (英镑)")
        ]
) -> str:
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


def get_fund_info(
fund_code: Annotated[
        str,
        Field(
            description="需要查询的基金或股票代码。当前系统支持的测试代码包括：'000001' (华夏成长混合), '110022' (易方达消费行业), 'SPY' (S&P 500 ETF), 'QQQ' (纳斯达克100 ETF)。"
        )
    ]
) -> str:
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
"calculate":                     calculate,
    "analyze_expenses":          analyze_expenses,
    "evaluate_financial_health": evaluate_financial_health,
    "generate_budget_plan":      generate_budget_plan,
    "get_exchange_rate":         get_exchange_rate,
    "get_fund_info":             get_fund_info,
}

# ── 4. 工具 Schema（告诉 Claude 每个工具的签名和用途）────────────────────────────
# 这是 Anthropic Function Calling 的关键：描述越清晰，Agent 调用越准确,这里采用函数动态生成符合anthropic function calling的JSON结构
"""
# ── 人工定义  ──────────────────────────────────────────────────────────────
TOOL_SCHEMAS = [
    {
        "name": "calculate",
        "description": "安全计算数学表达式，支持 +−×÷ 和括号。所有需要计算的数字运算必须通过此工具，不要自行心算。",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '(5000 - 3200) / 5000' 或 '1200 * 12'"
                }
            },
            "required": ["expression"]
        }
    },
    {
        "name": "analyze_expenses",
        "description": "分析一组交易数据，输出分类汇总、储蓄率等关键指标。用户提供交易明细时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "transactions_json": {
                    "type": "string",
                    "description": "JSON 字符串，格式：[{\"category\":\"餐饮\",\"amount\":500,\"description\":\"\"}, ...]。收入用负数，支出用正数。"
                },
                "period": {
                    "type": "string",
                    "description": "分析周期描述，如 '2024年12月' 或 '本月'",
                    "default": "本月"
                }
            },
            "required": ["transactions_json"]
        }
    },
    {
        "name": "evaluate_financial_health",
        "description": "根据收支和储蓄情况评估财务健康度，给出 1-100 评分和具体建议。",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_income":       {"type": "number", "description": "月收入（税后）"},
                "monthly_expense":      {"type": "number", "description": "月总支出"},
                "total_savings":        {"type": "number", "description": "当前总储蓄/应急资金"},
                "monthly_debt_payment": {"type": "number", "description": "每月还款金额（无债务填0）", "default": 0}
            },
            "required": ["monthly_income", "monthly_expense", "total_savings"]
        }
    },
    {
        "name": "generate_budget_plan",
        "description": "根据月收入和财务目标，生成个性化预算分配方案（基于 50/30/20 法则）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_income":       {"type": "number", "description": "月收入（税后）"},
                "financial_goal":       {"type": "string", "description": "财务目标，如 '3年内买房首付' 或 '提高投资比例'"},
                "current_obligations":  {"type": "string", "description": "固定支出项，如 '房租2000+车贷1500'", "default": ""}
            },
            "required": ["monthly_income"]
        }
    },
    {
        "name": "get_exchange_rate",
        "description": "查询两种货币之间的实时汇率，用于外币资产换算或跨境消费分析。",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_currency": {"type": "string", "description": "源货币代码，如 USD / CNY / EUR / JPY"},
                "to_currency":   {"type": "string", "description": "目标货币代码"}
            },
            "required": ["from_currency", "to_currency"]
        }
    },
    {
        "name": "get_fund_info",
        "description": "查询基金或股票的基本信息和近期表现，用于投资建议参考。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码（如 000001）或股票代码（如 SPY）"}
            },
            "required": ["fund_code"]
        }
    },
]

"""

def generate_anthropic_tool_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """
    将带有 Annotated 类型提示的 Python 函数转换为 Anthropic Claude Tool Schema。
    """
    sig = inspect.signature(func)

    # 提取函数级 docstring，清理换行符
    doc = inspect.getdoc(func) or ""

    func_description = " ".join(doc.strip().split())
    fields: dict[str, tuple[type, Any]] = {}

    for param_name, param in sig.parameters.items():
        # 提取类型注解 (包含 Annotated)
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        pprint(annotation)
        # 处理默认值
        if param.default == inspect.Parameter.empty:
            default_value = ...  # 必填项
        else:
            default_value = param.default

        fields[param_name] = (annotation, default_value)


    # 动态创建 Pydantic 模型
    dynamic_model = create_model(f"{func.__name__}_Model", **fields)

    # 获取原始 JSON Schema
    raw_schema = dynamic_model.model_json_schema()

    # 组装为 Anthropic 格式
    return {
        "name": func.__name__,
        "description": func_description,
        "input_schema": {
            "type": "object",
            "properties": raw_schema.get("properties", {}),
            "required": raw_schema.get("required", [])
        }
    }

if __name__ == "__main__":
    TOOL_SCHEMAS = [
        generate_anthropic_tool_schema(func)
        for func in TOOL_REGISTRY.values()
    ]
    print(TOOL_SCHEMAS)