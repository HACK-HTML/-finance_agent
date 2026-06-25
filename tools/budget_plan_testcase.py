TEST_CASES = [
    # (monthly_income, financial_goal, current_obligations, 这个用例想考察什么)
    {"monthly_income": 8000,  "financial_goal": "买房存首付", "current_obligations": "", "probe": "激进储蓄目标，初版储蓄率够不够"},
    {"monthly_income": 5000,  "financial_goal": "还清信用卡债务", "current_obligations": "每月还款2000", "probe": "高负债，必要支出是否挤压储蓄"},
    {"monthly_income": 15000, "financial_goal": "平衡储蓄与生活", "current_obligations": "", "probe": "高收入默认策略，储蓄率20%是否偏低"},
    {"monthly_income": 3000,  "financial_goal": "存钱", "current_obligations": "房租1500", "probe": "低收入+高固定支出，预算是否可行"},
    {"monthly_income": 20000, "financial_goal": "买房", "current_obligations": "车贷3000", "probe": "高收入有负债，激进储蓄合理性"},
    {"monthly_income": 6000,  "financial_goal": "平衡", "current_obligations": "", "probe": "中等收入基准线"},
    {"monthly_income": 10000, "financial_goal": "提前退休储蓄", "current_obligations": "", "probe": "目标未命中关键词，落到默认策略，储蓄率是否过低"},
    {"monthly_income": 4500,  "financial_goal": "还债", "current_obligations": "助学贷款1800", "probe": "还债型+大额负债"},
    {"monthly_income": 12000, "financial_goal": "储蓄买房", "current_obligations": "房租4000", "probe": "高固定支出 vs 激进储蓄的冲突"},
    {"monthly_income": 7000,  "financial_goal": "平衡生活质量", "current_obligations": "", "probe": "默认策略中等收入，娱乐占比是否过高"},
]