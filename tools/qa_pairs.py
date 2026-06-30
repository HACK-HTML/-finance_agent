"""
财务 RAGAS 评估用 QA 对 —— 基于两份模拟财务 PDF 的真实内容
============================================================

每个 QA 对包含：
  - question:   中文自然语言问题
  - reference:  标准答案（ground truth）
  - category:   direct_lookup | multi_chunk | honesty_probe
  - source_pdf: 答案所在的 PDF 文件名

设计原则：
  - 全部基于 generate_financial_pdf.py 和 generate_product_pdf.py 生成的 PDF 实际内容
  - 包含计算类问题作为生成器推理能力的硬核测试
  - 诚实性探针用于检测幻觉——答案不在文档中，系统应诚实说"无法回答"
  - 每个 QA 对带元数据，支持按类型/来源做分层分析
"""

FINANCIAL_QA_PAIRS: list[dict] = [
    # =====================================================================
    # ABC Tech Annual Report — Direct Lookup (8 pairs)
    # =====================================================================
    {
        "question": "ABC Technology 2024财年的总营收是多少？",
        "reference": "85.2亿元人民币（8,520 million CNY），同比增长16.3%",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology 2024年的净利润是多少？同比增长了多少？",
        "reference": "净利润12.4亿元（1,240 million CNY），同比增长22.7%",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology 2024财年的毛利率是多少？与2023年相比有什么变化？",
        "reference": "2024年毛利率为61.4%，2023年为58.2%，提升了3.2个百分点",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "公司2024年云服务业务的营收是多少？同比增长率是多少？",
        "reference": "云服务营收34.08亿元（3,408 million CNY），同比增长34.2%",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology 2024年的研发费用是多少？",
        "reference": "研发费用17.04亿元（1,704 million CNY），同比增长16.2%",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "截至2024年12月31日，ABC Technology的现金及等价物是多少？",
        "reference": "42.60亿元（4,260 million CNY）",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology 2024年的每股收益（EPS）是多少？",
        "reference": "3.72元（CNY 3.72），较2023年的3.04元增长22.4%",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "公司2024年的资产负债率（Debt-to-Equity Ratio）是多少？与2023年相比如何？",
        "reference": "2024年为0.32x，2023年为0.38x，有所改善（下降）",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },

    # =====================================================================
    # ABC Tech Annual Report — Multi-chunk Synthesis (3 pairs)
    # =====================================================================
    {
        "question": "ABC Technology 2024年哪些业务板块实现了正增长？哪些出现了下滑？具体增长率分别是多少？",
        "reference": "正增长：Cloud Services同比增长34.2%（从25.40亿增至34.08亿）和Enterprise SaaS同比增长28.1%（从19.95亿增至25.56亿）；下滑：Hardware & IoT同比下降7.0%和Professional Services同比下降11.4%",
        "category": "multi_chunk",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "从盈利能力来看，ABC Technology 2024年的营业利润率和净利润率分别是多少？请根据财报数据计算。",
        "reference": "营业利润率=营业利润2,124/营收8,520=24.9%；净利润率=净利润1,240/营收8,520=14.6%",
        "category": "multi_chunk",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology对2025年的营收指引是多少？公司计划在哪些方面加大投入？",
        "reference": "2025年营收预期98-102亿元（增长15%-20%），其中云服务预计超过45亿元，毛利率保持在60%以上。公司计划将研发投入增至营收的约22%聚焦AI/ML平台，并计划12-15亿元资本开支用于数据中心扩展",
        "category": "multi_chunk",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },

    # =====================================================================
    # ABC Tech Annual Report — Honesty Probes (2 pairs)
    # =====================================================================
    {
        "question": "ABC Technology的CEO是谁？",
        "reference": "文档中未提及",
        "category": "honesty_probe",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    {
        "question": "ABC Technology 2024年的员工总数是多少？",
        "reference": "文档中未提及",
        "category": "honesty_probe",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },

    # =====================================================================
    # Huaxia Prospectus — Direct Lookup (7 pairs)
    # =====================================================================
    {
        "question": "华夏稳健增长365理财产品的产品登记编码是什么？",
        "reference": "C202404150001",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365的风险等级是什么？适合哪类投资者？",
        "reference": "R2（稳健型），适合稳健型及以上投资者",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365的固定管理费率是多少？如何收取？",
        "reference": "0.60%/年，每日计提、按月支付，每日从净值中预扣",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "该产品的托管费率是多少？支付给谁？",
        "reference": "0.05%/年，支付给托管银行（中国建设银行）",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "如果华夏稳健增长365到期时净值跌破1.0000发生本金亏损，管理人有什么承诺？",
        "reference": "退还已收取固定管理费的50%，且不收取任何浮动管理费",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365的业绩比较基准年化收益率是多少？这个基准是如何构成的？",
        "reference": "年化4.0%，基于债券组合收益率3.2%加权益股息及资本利得贡献0.8%加权形成",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365的客户服务热线是多少？",
        "reference": "95577，提供24小时服务",
        "category": "direct_lookup",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },

    # =====================================================================
    # Huaxia Prospectus — Multi-chunk Synthesis (6 pairs)
    # =====================================================================
    {
        "question": "假设投资者认购10万元华夏稳健增长365并持有到期，产品到期年化收益率为5.2%，投资者需要支付多少浮动管理费？",
        "reference": "浮动管理费=100,000×1.2%×(347/365)×20%≈228元。其中1.2%是超过4.0%基准的超额收益部分，347天是产品期限，20%是浮动管理费提取比例",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365允许提前赎回吗？如果可以，条件和费用是什么？",
        "reference": "允许在两种情况下提前赎回：1）因重大疾病/购房/子女教育等紧急情况经管理人批准可在每季度末最后一个工作日赎回，罚金0.50%，资金5-7个工作日到账；2）认购期内（1月10-17日）可无条件全额退款且无费用",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365对单一企业债券有什么投资限制？对信用评级有什么要求？",
        "reference": "单一企业债券不超过组合的3%，所有债券投资最低信用评级要求为AA+",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "该产品的资产配置中，固定收益类、权益类和流动性资产的目标比例范围分别是什么？",
        "reference": "固定收益类资产60%-85%，权益类资产0%-30%，流动性资产5%-15%",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "产品说明书列出了哪些主要风险？请概括并说明最大回撤预期。",
        "reference": "五大风险：利率风险、信用风险、权益市场波动风险（最大回撤预期不超过5%）、流动性风险（封闭期347天不可赎回）、管理风险",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "如果发生巨额赎回（单日赎回申请超过总份额10%），管理人会如何处理？",
        "reference": "管理人可延长支付至15个工作日，并按比例分配可用赎回额度",
        "category": "multi_chunk",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },

    # =====================================================================
    # Huaxia Prospectus — Honesty Probes (2 pairs)
    # =====================================================================
    {
        "question": "华夏稳健增长365产品的历史年化收益率是多少？",
        "reference": "文档中未提及（该产品为新产品，无历史业绩数据）",
        "category": "honesty_probe",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
    {
        "question": "华夏稳健增长365的投资经理是谁？",
        "reference": "文档中未提及",
        "category": "honesty_probe",
        "source_pdf": "Huaxia_Stable_Growth_365_Prospectus.pdf",
    },
]


def get_qa_pairs() -> list[dict]:
    """返回全部 QA 对列表。"""
    return FINANCIAL_QA_PAIRS


def get_pairs_by_category(category: str) -> list[dict]:
    """按类型筛选：direct_lookup | multi_chunk | honesty_probe"""
    return [p for p in FINANCIAL_QA_PAIRS if p["category"] == category]


def get_pairs_by_source(source_pdf: str) -> list[dict]:
    """按来源 PDF 筛选"""
    return [p for p in FINANCIAL_QA_PAIRS if p["source_pdf"] == source_pdf]


def print_summary():
    """打印 QA 对统计摘要"""
    total = len(FINANCIAL_QA_PAIRS)
    cats = {}
    srcs = {}
    for p in FINANCIAL_QA_PAIRS:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
        srcs[p["source_pdf"]] = srcs.get(p["source_pdf"], 0) + 1

    print(f"=== QA Pairs Summary ===")
    print(f"Total: {total}")
    print(f"By category: {cats}")
    print(f"By source: {srcs}")


if __name__ == "__main__":
    print_summary()
