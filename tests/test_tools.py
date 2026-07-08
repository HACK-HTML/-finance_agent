"""
pytest 测试：工具函数纯函数
覆盖 tools/budget_plan.py、tools/registry.py、tools/retrieve_tool.py、
tools/budget_plan_judge.py 中的纯函数。
"""
import pytest
from tools.budget_plan import (
    _parse_obligations,
    _initial_ratios,
    _label_from_actual,
    _compute_plan,
    _render_plan,
)
from tools.registry import (
    calculate,
    analyze_expenses,
    evaluate_financial_health,
    _compare_plans,
)
from tools.retrieve_tool import QueryRouter, RetrievalCritic
from tools.rag_pipeline import RetrievedChunk
from tools.budget_plan_judge import check_numerical_correctness


# ═══════════════════════════════════════════════════════════════════════════════════
# tools/budget_plan.py
# ═══════════════════════════════════════════════════════════════════════════════════

# ── _parse_obligations ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("", 0.0),
    ("每月还款2000", 2000.0),
    ("房租1500+车贷3000", 4500.0),
    ("还款2,500", 2500.0),
])
def test_parse_obligations(text, expected):
    """从负债描述文本中提取数字金额。"""
    assert _parse_obligations(text) == expected


# ── _initial_ratios ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("goal,expected", [
    ("买房", (0.45, 0.20, 0.35, "激进储蓄型")),
    ("存钱", (0.45, 0.20, 0.35, "激进储蓄型")),
    ("储蓄", (0.45, 0.20, 0.35, "激进储蓄型")),
    ("还债", (0.50, 0.15, 0.35, "还债优先型")),
    ("债务", (0.50, 0.15, 0.35, "还债优先型")),
    ("随便写", (0.50, 0.30, 0.20, "均衡发展型")),
])
def test_initial_ratios(goal, expected):
    """财务目标关键词映射到正确的初始比例。"""
    assert _initial_ratios(goal) == expected


# ── _label_from_actual ──────────────────────────────────────────────────────────

def test_label_debt_priority_when_extra_debt_exists():
    """有额外偿债时返回还债优先型标签。"""
    actual = {"extra_debt_rate": 0.1, "net_improvement_rate": 0.30,
              "savings_rate": 0.20}
    result = _label_from_actual(actual, "平衡", "base")
    assert "还债优先型" in result


def test_label_debt_when_goal_contains_debt_keyword():
    """目标含还债关键词时返回还债标签。"""
    actual = {"extra_debt_rate": 0, "net_improvement_rate": 0.25,
              "savings_rate": 0.25}
    result = _label_from_actual(actual, "想还债", "base")
    assert "还债优先型" in result


@pytest.mark.parametrize("net_rate,sav_rate,label_keyword", [
    (0.35, 0.35, "积极储蓄型"),
    (0.30, 0.30, "积极储蓄型"),  # 边界：≥0.30 → 积极
    (0.20, 0.20, "稳健储蓄型"),
    (0.15, 0.15, "稳健储蓄型"),  # 边界：≥0.15 → 稳健
    (0.05, 0.05, "保守型"),
])
def test_label_from_net_improvement_rate(net_rate, sav_rate, label_keyword):
    """net_improvement_rate 决定策略标签。"""
    actual = {"extra_debt_rate": 0, "net_improvement_rate": net_rate,
              "savings_rate": sav_rate}
    result = _label_from_actual(actual, "平衡", "base")
    assert label_keyword in result


# ── _compute_plan ────────────────────────────────────────────────────────────────

def test_compute_plan_basic_no_obligations():
    """无负债基本场景：可支配收入 == 月收入。"""
    plan = _compute_plan(10000, 0.5, 0.3, 0.2, "均衡发展型",
                         "平衡储蓄与生活质量")
    assert plan["monthly_income"] == 10000
    assert plan["obligation"] == 0
    assert plan["disposable"] == 10000
    assert plan["actual"]["obligation_rate"] == 0
    assert len(plan["categories"]) == 9  # 无负债/偿债 → 9 个分类


def test_compute_plan_with_obligations_deducts_correctly():
    """含负债时先从收入中扣除。"""
    plan = _compute_plan(10000, 0.5, 0.3, 0.2, "均衡发展型",
                         "平衡", "房租2000")
    assert plan["obligation"] == 2000
    assert plan["disposable"] == 8000
    assert "💳" in list(plan["categories"].keys())[0]


def test_compute_plan_categories_sum_approximately_equals_income():
    """分类金额之和 ≈ 月收入（四舍五入误差 < 1 元）。"""
    plan = _compute_plan(12000, 0.5, 0.3, 0.2, "均衡发展型", "存钱")
    total = sum(plan["categories"].values())
    assert abs(total - plan["monthly_income"]) < 1.0


def test_compute_plan_zero_income_edge_case():
    """零收入时不抛异常，可支配收入为 0。"""
    plan = _compute_plan(0, 0.5, 0.3, 0.2, "均衡发展型", "存钱")
    assert plan["disposable"] == 0
    # 无 ZeroDivisionError
    assert "actual" in plan


# ── _render_plan ─────────────────────────────────────────────────────────────────

def test_render_plan_output_contains_income_and_strategy():
    """渲染输出包含月收入和策略标签。"""
    plan = _compute_plan(12000, 0.5, 0.3, 0.2, "均衡发展型", "存钱")
    text = _render_plan(plan)
    assert "月收入" in text
    assert "¥12,000" in text
    assert plan["strategy"] in text


def test_render_plan_with_obligations_shows_debt_info():
    """含负债的 plan 渲染输出显示负债信息。"""
    plan = _compute_plan(10000, 0.5, 0.3, 0.2, "均衡发展型",
                         "平衡", "房租2000")
    text = _render_plan(plan)
    assert "固定负债" in text
    assert "可支配" in text


# ═══════════════════════════════════════════════════════════════════════════════════
# tools/registry.py
# ═══════════════════════════════════════════════════════════════════════════════════

# ── calculate ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr,expected", [
    ("2+3", "5"),
    ("(5000-3200)/5000", "0.36"),
    ("5%", "0.05"),
    ("10+20*3", "70"),
])
def test_calculate_valid_expressions(expr, expected):
    """安全计算合法数学表达式。"""
    assert calculate(expr) == expected


def test_calculate_rejects_invalid_characters():
    """包含非法字符的表达式被拒绝。"""
    result = calculate("2+abc")
    assert "错误" in result


def test_calculate_trailing_zero_stripping():
    """结果尾随零被去除。"""
    assert calculate("3.000") == "3"


# ── analyze_expenses ─────────────────────────────────────────────────────────────

def test_analyze_expenses_valid_json():
    """有效 JSON 返回完整的财务摘要。"""
    txn = '[{"category":"餐饮","amount":500},{"category":"交通","amount":200},{"category":"工资","amount":-8000}]'
    result = analyze_expenses(txn, "2025-01")
    assert "总收入" in result
    assert "总支出" in result
    assert "储蓄率" in result
    assert "分类排行" in result


def test_analyze_expenses_invalid_json_returns_error():
    """无效 JSON 返回错误提示。"""
    result = analyze_expenses("{not json}")
    assert "格式无效" in result


def test_analyze_expenses_empty_array():
    """空数组不崩溃。"""
    result = analyze_expenses("[]")
    assert "储蓄率" in result


# ── evaluate_financial_health ────────────────────────────────────────────────────

def test_health_excellent():
    """高储蓄+高应急金+低负债 → 优秀。"""
    result = evaluate_financial_health(20000, 12000, 100000, 0)
    assert "优秀" in result


def test_health_good():
    """中等储蓄率+低应急金 → 良好。"""
    # savings=15% (+15), emergency=2.5mo (+0), debt=10% (+5) → score=70 → 良好
    result = evaluate_financial_health(10000, 8500, 21250, 1000)
    assert "良好" in result


def test_health_needs_improvement():
    """低储蓄 → 需改善。"""
    result = evaluate_financial_health(8000, 7500, 10000, 0)
    assert "需改善" in result or "改善" in result


def test_health_danger():
    """入不敷出+高负债+无应急金 → 最低评分 40（当前评分体系下限）。"""
    # savings<10% (+0), emergency<3mo (+0), debt>36% (-10) → score=40
    result = evaluate_financial_health(2000, 5000, 0, 1500)
    assert "40/100" in result  # 当前最低分
    assert "优先还款" in result


def test_health_zero_income_edge_case():
    """零收入不抛 ZeroDivisionError。"""
    result = evaluate_financial_health(0, 1000, 5000)
    assert "评分" in result


# ── _compare_plans ───────────────────────────────────────────────────────────────

def _make_plan(savings_rate, net_improvement):
    """快捷构造 plan dict 用于 _compare_plans 测试。"""
    return {"actual": {"savings_rate": savings_rate,
                       "net_improvement_rate": net_improvement}}


def test_compare_prefers_v2_when_v1_savings_rate_out_of_range():
    """v1 储蓄率不在 0.15-0.50 范围，v2 在范围内 → v2 胜。"""
    v1 = _make_plan(0.05, 0.30)
    v2 = _make_plan(0.25, 0.25)
    assert _compare_plans(v1, v2) is v2


def test_compare_prefers_v2_when_better_net_improvement():
    """两者储蓄率都在范围内，v2 净改善率显著更高 → v2 胜。"""
    v1 = _make_plan(0.30, 0.30)
    v2 = _make_plan(0.30, 0.35)  # 差异 0.05 > 0.02
    assert _compare_plans(v1, v2) is v2


def test_compare_keeps_v1_when_v2_not_significantly_better():
    """v2 净改善率差异不大 → 保留 v1（保守策略）。"""
    v1 = _make_plan(0.30, 0.30)
    v2 = _make_plan(0.30, 0.31)  # 差异 0.01 ≤ 0.02
    assert _compare_plans(v1, v2) is v1


# ═══════════════════════════════════════════════════════════════════════════════════
# tools/retrieve_tool.py
# ═══════════════════════════════════════════════════════════════════════════════════

# ── QueryRouter.classify ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    ("赎回费率是多少", "exact"),
    ("什么是年化收益率", "exact"),
    ("这个产品怎么样", "exact"),  # 不匹配 "怎么样".*"投资" 组合
    ("总结一下这只基金的风险", "summary"),
    ("整体介绍一下这个理财产品", "summary"),
    ("归纳一下产品的核心特点", "summary"),
])
def test_query_router_classify(query, expected):
    """中文财务查询被正确分类为 exact 或 summary。"""
    assert QueryRouter.classify(query) == expected


# ── QueryRouter.get_strategy ─────────────────────────────────────────────────────

def test_get_strategy_exact():
    """exact 策略返回较小的 top_k/top_n。"""
    assert QueryRouter.get_strategy("exact") == {"top_k": 20, "top_n": 5}


def test_get_strategy_summary():
    """summary 策略返回较大的 top_k/top_n 以覆盖更多内容。"""
    assert QueryRouter.get_strategy("summary") == {"top_k": 30, "top_n": 7}


def test_get_strategy_unknown_defaults_to_exact():
    """未知类型默认返回 exact 策略。"""
    assert QueryRouter.get_strategy("unknown") == {"top_k": 20, "top_n": 5}


# ── RetrievalCritic.evaluate ─────────────────────────────────────────────────────

def _chunks(*scores):
    """快捷构造 RetrievedChunk 列表。"""
    return [RetrievedChunk(text=f"t{i}", source="src", page=1, score=s)
            for i, s in enumerate(scores)]


def test_evaluate_empty_list_returns_false_no_results():
    """空结果 → 不合格，原因 no_results。"""
    ok, reason = RetrievalCritic.evaluate([])
    assert ok is False
    assert "no_results" in reason


def test_evaluate_all_high_scores_returns_true():
    """所有分数都高 → 合格。"""
    ok, reason = RetrievalCritic.evaluate(_chunks(0.6, 0.7, 0.8))
    assert ok is True
    assert reason == "ok"


def test_evaluate_low_average_returns_false():
    """平均分 < 0.3 → 不合格，含 avg_low。"""
    ok, reason = RetrievalCritic.evaluate(_chunks(0.2, 0.25, 0.3))
    assert ok is False
    assert "avg_low" in reason


def test_evaluate_low_max_returns_false():
    """最高分 < 0.5 → 不合格，含 max_low。"""
    ok, reason = RetrievalCritic.evaluate(_chunks(0.4, 0.45, 0.42))
    assert ok is False
    assert "max_low" in reason


def test_evaluate_both_low_returns_false_with_both_reasons():
    """平均和最高都低 → 两个原因都有。"""
    ok, reason = RetrievalCritic.evaluate(_chunks(0.2, 0.3, 0.2))
    assert ok is False
    assert "avg_low" in reason
    assert "max_low" in reason


# ── RetrievalCritic.reformulate ──────────────────────────────────────────────────

def test_reformulate_no_results_shortens_query():
    """no_results 时截断问号后缀。"""
    result = RetrievalCritic.reformulate(
        "什么是产品赎回费率？请详细说明", "no_results")
    assert "？" not in result
    assert "请详细说明" not in result
    assert "产品赎回费率" in result


def test_reformulate_short_query_keeps_prefix():
    """短查询 (<4 字符截断后) 保留前 20 字符。"""
    result = RetrievalCritic.reformulate("费率？", "no_results")
    assert len(result) > 0


def test_reformulate_low_score_without_domain_words_injects_keywords():
    """无领域词时注入金融关键词。"""
    result = RetrievalCritic.reformulate("这个怎么样", "avg_low(0.10)")
    assert "理财产品" in result
    assert "金融文档" in result


def test_reformulate_low_score_with_domain_words_returns_empty():
    """已有领域词时返回空串（无需改写）。"""
    result = RetrievalCritic.reformulate("基金费率怎么算", "avg_low(0.10)")
    assert result == ""


# ═══════════════════════════════════════════════════════════════════════════════════
# tools/budget_plan_judge.py
# ═══════════════════════════════════════════════════════════════════════════════════

# ── check_numerical_correctness ──────────────────────────────────────────────────

def test_numerical_correctness_pass_with_valid_plan():
    """分类金额之和 ≈ 月收入 → 通过。"""
    income = 9000
    cats = [2000, 1500, 1200, 1000, 800, 700, 600, 500, 700]  # sum=9000
    lines = []
    for amt in cats:
        lines.append("  某分类 ¥{:,}  {:.1f}%".format(amt, amt/income*100))
    total = sum(cats)
    lines.append("  合计 ¥{:,}  {:.1f}%".format(total, total/income*100))
    text = "\n".join(lines)

    result = check_numerical_correctness(text, income)
    assert result["pass"] is True


def test_numerical_correctness_fail_when_sum_mismatch():
    """分类和偏离收入 > 2% → 失败。"""
    lines = []
    cats = [2000, 1500, 1200]  # 和=4700，与 10000 差 53%
    for amt in cats:
        lines.append(f"  某分类 ¥{amt:,}  {amt/10000*100:.1f}%")
    total = sum(cats)
    lines.append(f"  合计 ¥{total:,}  {total/10000*100:.1f}%")
    text = "\n".join(lines)

    result = check_numerical_correctness(text, 10000)
    assert result["pass"] is False


def test_numerical_correctness_fail_when_no_amounts_parsed():
    """无法解析出任何金额 → 失败。"""
    result = check_numerical_correctness("No amounts here", 10000)
    assert result["pass"] is False
    assert "未解析出明细金额" in result["detail"]
