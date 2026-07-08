"""
pytest 测试：Pydantic 数据模型校验器
覆盖 models/schemas.py 中的 5 个 validator。
"""
import pytest
from pydantic import ValidationError
from models.schemas import (
    Transaction,
    MonthlyReport,
    SuggestedRatios,
    SuggestedSavingsSplit,
    BudgetCritique,
)


# ── Transaction.amount_not_zero ──────────────────────────────────────────────────

def test_transaction_valid_amount_accepted():
    """正常金额被接受。"""
    t = Transaction(category="餐饮", amount=100.5)
    assert t.amount == 100.5


def test_transaction_amount_rounded_to_2_decimals():
    """金额自动四舍五入到两位小数。"""
    t = Transaction(category="餐饮", amount=100.456)
    assert t.amount == 100.46


def test_transaction_zero_amount_raises_validation_error():
    """金额为 0 时拒绝。"""
    with pytest.raises(ValidationError, match="金额不能为 0"):
        Transaction(category="餐饮", amount=0)


def test_transaction_negative_amount_accepted_for_income():
    """负金额（收入）被接受。"""
    t = Transaction(category="工资", amount=-5000)
    assert t.amount == -5000.0


# ── MonthlyReport.valid_rate ─────────────────────────────────────────────────────

def test_monthly_report_valid_savings_rate():
    """有效储蓄率被接受并四舍五入到4位。"""
    r = MonthlyReport(
        month="2025-01", total_income=10000, total_expense=7000,
        savings_rate=0.29168, top_category="餐饮", health_score=70,
        suggestions=["减少开支"],
    )
    assert r.savings_rate == pytest.approx(0.2917, rel=1e-5)


def test_monthly_report_negative_savings_rate_raises():
    """负储蓄率拒绝。"""
    with pytest.raises(ValidationError, match="0 到 1"):
        MonthlyReport(
            month="2025-01", total_income=10000, total_expense=7000,
            savings_rate=-0.1, top_category="餐饮", health_score=70,
            suggestions=["减少开支"],
        )


def test_monthly_report_savings_rate_above_one_raises():
    """>1 的储蓄率拒绝。"""
    with pytest.raises(ValidationError, match="0 到 1"):
        MonthlyReport(
            month="2025-01", total_income=10000, total_expense=7000,
            savings_rate=1.5, top_category="餐饮", health_score=70,
            suggestions=["减少开支"],
        )


# ── SuggestedRatios._sum (model_validator) ───────────────────────────────────────

@pytest.mark.parametrize("needs,wants,savings,should_raise,desc", [
    (0.5, 0.3, 0.2, False, "精确和为 1.0"),
    (0.34, 0.33, 0.33, False, "精确和为 1.00"),
    # --- 新增：真正触发容差边界的测试数据 ---
    (0.51, 0.30, 0.20, False, "正向容差边界（和=1.01，允许）"),
    (0.49, 0.30, 0.20, False, "负向容差边界（和=0.99，允许）"),
    # ----------------------------------------
    (0.3, 0.3, 0.3, True, "低于公差（和=0.90，拒绝）"),
    (0.5, 0.5, 0.05, True, "超出公差（和=1.05，拒绝）"),
])
def test_suggested_ratios_sum_validation(needs, wants, savings, should_raise, desc):
    """SuggestedRatios 的三类比例之和必须在 1.0 ± 0.02 内。"""
    if should_raise:
        with pytest.raises(ValidationError, match="约等于 1"):
            SuggestedRatios(needs=needs, wants=wants, savings=savings)
    else:
        r = SuggestedRatios(needs=needs, wants=wants, savings=savings)
        # 强化断言：必须验证所有字段，确保没有发生数据截断或错位
        assert r.needs == needs
        assert r.wants == wants
        assert r.savings == savings


# ── SuggestedSavingsSplit._sum (model_validator) ─────────────────────────────────

@pytest.mark.parametrize("emergency,investment,goal,should_raise,desc", [
    (0.4, 0.4, 0.2, False, "精确和为 1.0"),
    (0.405, 0.4, 0.205, False, "在 ±0.02 公差内（和=1.01）"),
    (0.5, 0.5, 0.5, True, "远超公差（和=1.5）"),
    (0.3, 0.3, 0.3, True, "低于公差（和=0.9）"),
])
def test_savings_split_sum_validation(emergency, investment, goal, should_raise, desc):
    """SuggestedSavingsSplit 的三项权重之和必须在 1.0 ± 0.02 内。"""
    if should_raise:
        with pytest.raises(ValidationError, match="约等于 1"):
            SuggestedSavingsSplit(emergency=emergency, investment=investment, goal=goal)
    else:
        s = SuggestedSavingsSplit(emergency=emergency, investment=investment, goal=goal)
        assert s.emergency == emergency


# ── BudgetCritique._coherence (model_validator) ──────────────────────────────────

def test_critique_ok_true_empty_issues_valid():
    """ok=True 且 issues 为空 → 合法。"""
    c = BudgetCritique(ok=True, issues=[])
    assert c.ok is True


def test_critique_ok_true_with_issues_valid():
    """ok=True 时 issues 非空也合法（可能只是备注）。"""
    c = BudgetCritique(ok=True, issues=["供参考"])
    assert c.ok is True


def test_critique_ok_false_with_issues_valid():
    """ok=False 且 issues 非空 → 合法。"""
    c = BudgetCritique(ok=False, issues=["储蓄率偏低"])
    assert c.ok is False
    assert len(c.issues) > 0


def test_critique_ok_false_no_issues_raises():
    """ok=False 但 issues 为空 → 拒绝。"""
    with pytest.raises(ValidationError, match="issues"):
        BudgetCritique(ok=False, issues=[])


def test_critique_suggested_extra_debt_negative_raises():
    """suggested_extra_debt 必须 ≥ 0。"""
    with pytest.raises(ValidationError):
        BudgetCritique(ok=True, suggested_extra_debt=-100)
