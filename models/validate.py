import json
from pprint import pprint

from models.schemas import MonthlyReport

raw = """
{
  "month": "2025-07",
  "total_income": 12000,
  "total_expense": 8500,
  "savings_rate": 0.2917,
  "top_category": "需提供支出明细以确定",
  "health_score": 93,
  "suggestions": [
    "优先补足应急基金：当前3万仅覆盖3.5个月，目标5.1万覆盖6个月，按每月结余3500元约需6个月达成",
    "应急金达标后启动投资：每月3500元可配置指数基金定投，长期享受复利增长",
    "审视弹性支出：从8500元月支出中寻找可优化空间，每月多省500元一年即多攒6000元",
    "保持零负债优势：目前无任何债务，这是财务健康的重要基石，避免不必要的消费贷款",
    "建议记录并分类每笔支出，以便精准定位最大消费类别，针对性优化支出结构"
  ]
}"""
report = MonthlyReport.model_validate(json.loads(raw))
pprint(report)