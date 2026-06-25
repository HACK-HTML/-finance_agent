"""
10 个测试用例跑 Eval，对比 Reflection 前后输出质量
用 LLM-as-Judge 给 Rubric 评分（储蓄率合理/建议可操作/数字正确），记录有 Reflection vs 无 Reflection 的评分差
"""
import json
import re
import anthropic
from statistics import mean
from pydantic import BaseModel,Field
from tools.registry import generate_budget_plan
from budget_plan_testcase import TEST_CASES

API_CRITIC_KEY = 'sk-33d367956a054b1c8f5870667ff821d6'
API_JUDGE_KEY = 'sk-301a24d67a474f20a54e7431d048b823'
BASE_URL = 'https://api.deepseek.com/anthropic'
# ──  LLM as judge 的评分标准──
class JudgeScore(BaseModel):
    """对单份预算方案的盲评打分。"""
    savings_reasonable: int = Field(ge=1, le=5, description="储蓄率是否合理（与收入和目标匹配）：1=很差，5=优秀")
    savings_reason: str = Field(description="给该分数的简短理由")

    actionable: int = Field(ge=1, le=5, description="方案是否具体可操作（分类清晰、金额明确、有指导性）：1=很差，5=优秀")
    actionable_reason: str = Field(description="给该分数的简短理由")

    goal_alignment: int = Field(ge=1, le=5, description="方案与理财目标的契合度：1=很差，5=优秀")
    goal_reason: str = Field(description="给该分数的简短理由")

# ── 数字正确性：代码硬核验证，不交给 LLM ──
import re

def check_numerical_correctness(plan_text, monthly_income):
    # 只匹配明细行：¥金额 后面紧跟 百分比（标题/审查记录没有这个模式）
    rows = re.findall(r"¥\s*([\d,]+)\s+[\d.]+%", plan_text)
    amounts = [float(x.replace(",", "")) for x in rows]

    if not amounts:
        return {"pass": False, "detail": "未解析出明细金额"}

    # 最后一行是"合计"，前面是9个分类
    *category_amounts, total = amounts
    cat_sum = sum(category_amounts)
    ok = abs(cat_sum - monthly_income) < monthly_income * 0.02
    return {
        "pass": ok,
        "detail": f"分类合计 ¥{cat_sum:.0f} vs 收入 ¥{monthly_income:.0f}（抽取{len(amounts)}项）",
    }


# ── LLM Judge：盲评三个主观维度 ──
def judge_plan(judge_client, plan_text: str, goal: str, income: float) -> JudgeScore:
    tool = {
        "name": "submit_score",
        "description": "提交对预算方案的评分",
        "input_schema": JudgeScore.model_json_schema(),
    }
    prompt = (
        "你是中立的理财方案评审专家。请对下面这份预算方案打分。"
        "你不知道也无需关心方案的来源，只根据方案本身的质量评判。\n\n"
        f"用户情况：月收入 ¥{income:.0f}，理财目标「{goal}」\n\n"
        f"预算方案：\n{plan_text}\n\n"
        "按以下维度各打 1-5 分（5最好），并给简短理由。"
        "调用 submit_score 工具提交各维度 1-5 分及理由"

    )
    resp = judge_client.messages.create(
        model="deepseek-v4-pro", max_tokens=1024*8,
        tools=[tool],
        messages=[{"role": "user", "content": prompt}],
    )
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return JudgeScore.model_validate(tool_use.input)  # 注意是 validate 不是 validate_json


# ── 单个用例：生成两组方案 + 评分 ──
DIMS = [
    ("savings_reasonable", "储蓄率合理性"),
    ("actionable",         "可操作性"),
    ("goal_alignment",     "目标契合度"),
]
SUB = "-" * 60
def run_one_case(case, critic_client, judge_client):
    income, goal, obligations = case["monthly_income"], case["financial_goal"], case["current_obligations"]

    # 无反思组：_client=None 跳过 critic 循环
    plan_without = generate_budget_plan(income, goal, obligations, _client=None)
    # 有反思组：传入 critic client，走完整反思
    plan_with = generate_budget_plan(income, goal, obligations, _client=critic_client)

    return {
        "probe": case["probe"],
        "without": {
            "score": judge_plan(judge_client, plan_without, goal, income),
            "numerical": check_numerical_correctness(plan_without, income),
        },
        "with": {
            "score": judge_plan(judge_client, plan_with, goal, income),
            "numerical": check_numerical_correctness(plan_with, income),
        },
    }

def display_one_case(r, index=None, total=None):
    """打印单个用例的对比明细（供 run_eval 逐个调用，也供报告复用）。"""
    wo, w = r["without"]["score"], r["with"]["score"]

    head = f"[用例 {index}/{total}]" if total else (f"[用例 {index}]" if index else "[用例]")
    print(f"\n{head} {r['probe']}")
    print(SUB)
    print(f"{'维度':<14}{'无反思':>8}{'有反思':>8}{'差':>6}")
    for key, label in DIMS:
        a, b = getattr(wo, key), getattr(w, key)
        print(f"{label:<14}{a:>8}{b:>8}{b - a:>+6}")

    nwo, nw = r["without"]["numerical"], r["with"]["numerical"]
    print(f"{'数字正确':<14}{'✓' if nwo['pass'] else '✗':>8}{'✓' if nw['pass'] else '✗':>8}")

    print(f"  反思后评语：储蓄率—{w.savings_reason}")
    print(f"            目标契合—{w.goal_reason}")
# ── 跑全部 10 个用例并汇总 ──
def run_eval(test_cases, critic_client, judge_client):
    results = []
    total = len(test_cases)

    for i, c in enumerate(test_cases, 1):
        r = run_one_case(c, critic_client, judge_client)
        results.append(r)
        display_one_case(r, index=i, total=total)   # ★ 跑完一个立刻打印

    # 全部跑完后汇总
    def collect(group, attr):
        return [getattr(x[group]["score"], attr) for x in results]

    summary = {}
    for key, _ in DIMS:
        w, wo = collect("with", key), collect("without", key)
        summary[key] = {
            "无反思均分": round(mean(wo), 2),
            "有反思均分": round(mean(w), 2),
            "提升": round(mean(w) - mean(wo), 2),
        }
    summary["数字正确率"] = {
        "无反思": f"{sum(r['without']['numerical']['pass'] for r in results)}/{total}",
        "有反思": f"{sum(r['with']['numerical']['pass'] for r in results)}/{total}",
    }
    return results, summary
def display_eval_report(results, summary, show_cases=False):
    """打印总览 + 结论。show_cases=True 时再打印逐用例明细。"""
    BAR = "=" * 60

    # ── 1. 总览 ──
    print(BAR)
    print(" Reflection 评测报告  (共 %d 个用例)" % len(results))
    print(BAR)
    print(f"\n{'维度':<14}{'无反思':>8}{'有反思':>8}{'提升':>8}")
    print(SUB)
    for key, label in DIMS:
        s = summary[key]
        delta = s["提升"]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "—")
        print(f"{label:<14}{s['无反思均分']:>8.2f}{s['有反思均分']:>8.2f}{delta:>+7.2f}{arrow}")
    print(SUB)
    num = summary["数字正确率"]
    print(f"{'数字正确率':<14}{num['无反思']:>8}{num['有反思']:>8}")
    print()

    # ── 2. 逐用例明细（默认跳过，因为 run_eval 已经逐个打印过了）──
    if show_cases:
        print(BAR)
        print(" 逐用例明细")
        print(BAR)
        for i, r in enumerate(results, 1):
            display_one_case(r, index=i, total=len(results))

    # ── 3. 结论提示 ──
    print("\n" + BAR)
    print(" 结论提示")
    print(BAR)
    improved = [label for key, label in DIMS if summary[key]["提升"] > 0.5]
    flat     = [label for key, label in DIMS if abs(summary[key]["提升"]) <= 0.5]
    dropped  = [label for key, label in DIMS if summary[key]["提升"] < -0.5]
    if improved:
        print(f"  ✓ 明显提升（>0.5）：{ '、'.join(improved) }")
    if flat:
        print(f"  — 提升不显著（≤0.5，可能在噪声范围内）：{ '、'.join(flat) }")
    if dropped:
        print(f"  ⚠ 出现下降（<-0.5）：{ '、'.join(dropped) }，建议回看对应用例的 judge 理由")
    print(f"\n  注：单次评分含 LLM 随机性，差值在 ±0.5 内不宜过度解读。")
    print(BAR)

if __name__ == "__main__":

    critic = anthropic.Anthropic(api_key=API_CRITIC_KEY, base_url=BASE_URL)
    judge = anthropic.Anthropic(api_key=API_JUDGE_KEY, base_url=BASE_URL)
    test_cases = TEST_CASES
    results, summary = run_eval(TEST_CASES, critic, judge)  # ★ 接住返回值
    display_eval_report(results, summary)