"""
预算计划的工具代码

"""
import json
from pydantic import BaseModel, Field
from models.schemas import BudgetCritique
import re
# ── 1. 解析负债字符串里的金额 ──
def _parse_obligations(text: str) -> float:
    """从 '每月还款2000'、'房租1500'、'车贷3000' 等提取数字金额，多项求和。"""
    if not text:
        return 0.0
    nums = re.findall(r"(\d[\d,]*)", text.replace("，", ","))
    return sum(float(n.replace(",", "")) for n in nums)


# ── 2. 计算内核：先扣负债，再分配剩余；储蓄细分可调 ──
def _compute_plan(monthly_income, needs_pct, wants_pct, savings_pct, strategy_base,
                  financial_goal, current_obligations="",
                  savings_split=(0.4, 0.4, 0.2), extra_debt_payment=0.0):
    obligation = _parse_obligations(current_obligations)
    disposable = max(monthly_income - obligation - extra_debt_payment, 0)

    needs = disposable * needs_pct
    wants = disposable * wants_pct
    savings = disposable * savings_pct
    emer_w, inv_w, goal_w = savings_split

    categories = {}
    if obligation > 0:
        categories["💳 固定负债偿还（房租/贷款等）"] = round(obligation, 0)
    if extra_debt_payment > 0:
        categories["🔥 额外加速偿债"] = round(extra_debt_payment, 0)
    categories.update({
        "🏠 必要支出（住房+交通+饮食）": round(needs * 0.7, 0),
        "🏥 保险+医疗备用": round(needs * 0.2, 0),
        "📱 通讯+订阅服务": round(needs * 0.1, 0),
        "🎮 娱乐+社交": round(wants * 0.4, 0),
        "👗 购物+个人消费": round(wants * 0.35, 0),
        "📚 学习+成长": round(wants * 0.25, 0),
        "🏦 应急基金": round(savings * emer_w, 0),
        "📈 长期投资": round(savings * inv_w, 0),
        "🎯 目标专项存款": round(savings * goal_w, 0),
    })

    # ★ 方向A核心：全部占比以"总收入"为分母反算，作为唯一对外口径
    inc = monthly_income if monthly_income else 1
    actual = {
        # 三大类的真实占比（注意：分母是总收入，含被负债占走的部分）
        "obligation_rate": obligation / inc,
        "extra_debt_rate": extra_debt_payment / inc,
        "needs_rate": needs / inc,
        "wants_rate": wants / inc,
        # 真实储蓄率：纯储蓄部分（不含偿债）
        "savings_rate": savings / inc,
        # 广义"资产改善率"：储蓄 + 额外偿债（还债也是净资产改善）
        "net_improvement_rate": (savings + extra_debt_payment) / inc,
    }

    # ★ 标签根据真实储蓄率动态生成，不再沿用名义关键词标签
    strategy = _label_from_actual(actual, financial_goal, strategy_base)

    return {
        "monthly_income": monthly_income,
        "obligation": obligation,
        "extra_debt_payment": extra_debt_payment,
        "disposable": disposable,
        "strategy": strategy,
        "financial_goal": financial_goal,
        "current_obligations": current_obligations,
        # 同时保留名义比例(供内部调试)和真实占比(对外口径)
        "nominal_ratios": {"needs": needs_pct, "wants": wants_pct, "savings": savings_pct},
        "savings_split": {"emergency": emer_w, "investment": inv_w, "goal": goal_w},
        "actual": actual,                       # ★ 对外、给Critic、给渲染都用这个
        "categories": categories,
    }
# ── 根据真实占比生成诚实的策略标签 ──
def _label_from_actual(actual, financial_goal, base):
    net = actual["net_improvement_rate"]        # 储蓄+偿债 的总资产改善率
    if actual["extra_debt_rate"] > 0 or "还债" in financial_goal or "债务" in financial_goal:
        return f"还债优先型（净资产改善率{net:.0%}）"
    if net >= 0.30:
        return f"积极储蓄型（储蓄率{actual['savings_rate']:.0%}）"
    elif net >= 0.15:
        return f"稳健储蓄型（储蓄率{actual['savings_rate']:.0%}）"
    else:
        return f"保守型（储蓄率{actual['savings_rate']:.0%}）"

# ── 3. 渲染：标注负债扣除与可支配收入 ──
def _render_plan(plan: dict) -> str:
    income = plan["monthly_income"]
    a = plan["actual"]
    lines = [
        f"📋 {plan['strategy']}预算方案（月收入 ¥{income:,.0f}）",
        f"  目标：{plan['financial_goal']}",
    ]
    if plan["obligation"] > 0:
        lines.append(f"  已有固定负债 ¥{plan['obligation']:,.0f}／月（占收入{a['obligation_rate']:.0%}），"
                     f"可支配 ¥{plan['disposable']:,.0f}")
    # ★ 摘要行直接报告真实占比，杜绝"名义vs实际"裂缝
    lines.append(f"  真实分配：必要{a['needs_rate']:.0%}｜弹性{a['wants_rate']:.0%}｜"
                 f"储蓄{a['savings_rate']:.0%}"
                 + (f"｜偿债{a['extra_debt_rate']:.0%}" if a['extra_debt_rate'] > 0 else ""))
    lines.append(f"\n{'分类':<20} {'预算':>10}  {'占比':>6}")
    lines.append("─" * 42)
    for cat, amt in plan["categories"].items():
        pct = amt / income * 100
        lines.append(f"  {cat:<18} ¥{amt:>8,.0f}  {pct:>5.1f}%")
    lines.append("─" * 42)
    total = sum(plan["categories"].values())
    lines.append(f"  {'合计':<18} ¥{total:>8,.0f}  {total/income*100:>5.1f}%")
    return "\n".join(lines)
# ── 4. get budget plan 初始比例：沿用原来的关键词逻辑 ──
def _initial_ratios(goal: str):
    g = goal.lower()
    if "买房" in g or "存钱" in g or "储蓄" in g:
        return 0.45, 0.20, 0.35, "激进储蓄型"
    elif "还债" in g or "债务" in g:
        return 0.50, 0.15, 0.35, "还债优先型"
    else:
        return 0.50, 0.30, 0.20, "均衡发展型"
# ── 5. LLM Critic：评审 + 给出调整后的比例（结构化输出）──
def _critique_plan(client, plan: dict) -> BudgetCritique:
    schema = BudgetCritique.model_json_schema()
    prompt = (
        "你是严格的个人理财审查员。审查以下预算是否合理，重点检查：\n"
        "①储蓄率是否合理（一般≥15%，激进目标≥30%）；\n"
        "②若有固定负债，是否已被妥善纳入、剩余可支配收入分配是否现实；\n"
        "③还债类目标是否给出了足够的加速偿债（suggested_extra_debt）；\n"
        "④储蓄内部结构是否匹配目标——如买房应让目标专项存款(goal)占大头、"
        "而非长期投资(investment)反超（用 suggested_savings_split 修正）；\n"
        "⑤三大类占比是否与目标匹配（用 suggested_ratios 修正）。\n\n"
        f"方案数据：{json.dumps(plan, ensure_ascii=False)}\n\n"
        "只返回符合以下 JSON Schema 的内容，不要额外文字：\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
    try:
        resp = client.messages.create(
            model="deepseek-v4-pro", max_tokens=1024*8,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[1].text.strip().replace("```json", "").replace("```", "").strip()
        return BudgetCritique.model_validate_json(text)
    except Exception as e:
        print(f"[critic解析失败，放行] {e}")
        return BudgetCritique(ok=True, issues=[])


