# Week 2 · Day 8-9 计划 —— 搭建 RAGAS 评估集

> 目标（计划原文）：搭建 20-30 个 QA 对的评估集，记录基础 RAG vs Agentic RAG 的 RAGAS 四指标对比，把对比数据写进 README。
> 面试价值：能讲"我用数据驱动优化，Context Recall 从 X 提升到 Y"。

---

## 一、为什么需要这个

项目目前有一个 `course/RAG.ipynb` 用 **LlamaIndex + ChromaDB** 在大学论文 PDF 上跑过 RAGAS baseline，但**生产管线从未被 RAGAS 评估过**：

- 生产管线 = Qdrant + 自定义递归切块 + 两阶段 Rerank + Agentic Router/Critic
- 面试时必须能说"我用 RAGAS 四指标对比了 baseline vs Agentic RAG，Context Recall 提升了 X%"
- 不能靠感觉说"好像更好了"——要有数据

**已有基础设施（可直接复用）**：

| 资源 | 位置 | 可复用内容 |
|------|------|-----------|
| RAGAS v0.4.3 | 已安装 | 直接 import |
| RAGAS 工作流模板 | `course/RAG.ipynb` | LLM 配置、EvaluationDataset 构建、4 指标 evaluate、结果持久化 |
| 输出格式参考 | `course/ragas_baseline_summary.txt` + `.csv` | summary + per_sample 的文件格式 |
| 对比模式参考 | `tools/budget_plan_judge.py` | with vs without reflection 的 side-by-side delta 输出 |
| 财务 PDF × 2 | 项目根目录 | 年报 + 产品说明书，QA 对的素材 |
| PDF 内容源 | `generate_financial_pdf.py` + `generate_product_pdf.py` | 确认 PDF 实际内容，确保 reference 准确 |

---

## 二、设计原则

1. **零新依赖** — RAGAS + DeepSeek API 即可，`course/RAG.ipynb` 已验证可行
2. **复用生产管线** — 直接调 `tools/rag_pipeline.py` 的 `DocumentStore.retrieve()`，不用 LlamaIndex/ChromaDB
3. **和 `budget_plan_judge.py` 一致的对比模式** — baseline vs agentic，输出 side-by-side delta + 分层分析
4. **QA 对基于真实 PDF 内容** — 先读 PDF 生成脚本确认内容，再写 reference，不凭空编造

---

## 三、文件清单

### 🆕 新增文件

| 文件 | 用途 | 预计行数 |
|------|------|---------|
| `tools/qa_pairs.py` | 28 个财务 QA 对（含 ground truth、类型标签、来源文档） | ~200 行 |
| `tools/ragas_eval.py` | 主评估脚本：检索 → 生成 → RAGAS 评估 → 对比报告 | ~250 行 |
| `tools/ragas_eval_verify.py` | 前置验证：检索覆盖检查 + 诚实性探针检查 + 生成器抽查 | ~120 行 |

### ✏️ 修改文件

| 文件 | 改动 | 原因 |
|------|------|------|
| `tools/retrieve_tool.py` | 提取 `_do_retrieve()` 共享逻辑，新增 `retrieve_document_structured()` 返回 `tuple[list[RetrievedChunk], str]` | eval 需要结构化的 chunks，Agent 仍用原有的字符串接口 |

### 📊 输出文件（评估运行后生成，git-ignored）

| 文件 | 内容 |
|------|------|
| `course/ragas_finance_baseline_summary.txt` | Baseline 聚合分数 + 配置快照 |
| `course/ragas_finance_baseline_per_sample.csv` | Baseline 逐样本分数 |
| `course/ragas_finance_agentic_summary.txt` | Agentic RAG 聚合分数 + 配置快照 |
| `course/ragas_finance_agentic_per_sample.csv` | Agentic RAG 逐样本分数 |
| `course/ragas_finance_comparison.txt` | Side-by-side delta 表 + 按问题类型分层分析 |

---

## 四、QA 对设计

### 规模与分布

总计 **28 对**（25-30 区间），3 类 × 2 文档：

| 类型 | 数量 | 测试目标 | 示例 |
|------|------|---------|------|
| `direct_lookup` | 15 | 检索精度——答案在单个 chunk 中 | "2024 年总营收是多少？""托管费率是多少？" |
| `multi_chunk` | 9 | 上下文召回——答案需跨 chunk 合成 | "哪些业务增长了哪些下滑了？""投资 10 万扣费后净收益多少？" |
| `honesty_probe` | 4 | 忠实度——答案不在文档中，不能编造 | "CEO 是谁？""历史年化收益率是多少？" |

### 来源文档分布

| 文档 | direct_lookup | multi_chunk | honesty_probe | 小计 |
|------|:---:|:---:|:---:|:---:|
| `ABC_Tech_2024_Annual_Report.pdf` | 8 | 3 | 2 | 13 |
| `Huaxia_Stable_Growth_365_Prospectus.pdf` | 7 | 6 | 2 | 15 |

### 设计原则

- **全部中文**（和 PDF 语言一致，和项目约定一致）
- **先读 `generate_financial_pdf.py` + `generate_product_pdf.py`**，确认 PDF 实际包含哪些数字和条款，再写 reference——确保 ground truth 真的在文档里
- **每个 QA 对带元数据**：`category`（direct_lookup / multi_chunk / honesty_probe）+ `source_pdf`，支持分层分析
- **包含计算类问题**（如"投资 10 万持有到期，年化 5.2%，扣浮动管理费后净收益多少"）——这类问题不仅测检索还测生成器的推理能力
- **诚实性探针的 reference 统一为"文档中未提及"**

### 数据结构

```python
# tools/qa_pairs.py
FINANCIAL_QA_PAIRS: list[dict] = [
    {
        "question": "ABC Technology 2024财年的总营收是多少？",
        "reference": "85.2亿元人民币（8,520 million CNY）",
        "category": "direct_lookup",
        "source_pdf": "ABC_Tech_2024_Annual_Report.pdf",
    },
    # ... 共 28 对
]
```

---

## 五、代码结构

### `tools/retrieve_tool.py` 重构

```
tools/retrieve_tool.py
├── QueryRouter          —— 不变
├── RetrievalCritic      —— 不变
│
├── _do_retrieve()       ← 🆕 提取共享逻辑（~20 行）
│   └── Router classify → retrieve → Critic evaluate → maybe retry
│       返回 (chunks, query_type, reason)
│
├── retrieve_document_structured()  ← 🆕 新公开接口（~30 行）
│   └── 调用 _do_retrieve() → 格式化 → 返回 (chunks, formatted_text)
│
├── retrieve_document()  ← ✏️ 改为薄封装
│   └── return retrieve_document_structured(...)[1]
│
└── RETRIEVE_DOCUMENT_SCHEMA —— 不变
```

**向后兼容**：Agent 的 `tool_registry` 仍绑定 `retrieve_document`，行为完全不变。

### `tools/ragas_eval.py` 架构

```
main()
  │
  ├─ 1. _ensure_docs_ingested()
  │     幂等入库，用专用 eval_user_id 隔离（不污染默认用户数据）
  │
  ├─ 2. _build_llm_components()
  │     ├─ ChatOpenAI(model="deepseek-v4-pro") → generator（生成回答）
  │     ├─ ChatOpenAI(model="deepseek-v4-pro", temperature=0) → judge（RAGAS 评分）
  │     └─ HuggingFaceEmbeddings("BAAI/bge-base-zh-v1.5") → evaluator_emb
  │
  ├─ 3. run_evaluation() × 2  ← baseline + agentic 各跑一遍
  │     for each QA pair:
  │       ├─ retrieve_fn(query)   → contexts: list[str]
  │       ├─ generate_answer()    → response: str（LLM 基于 contexts 生成）
  │       └─ 收集 (user_input, contexts, response, reference)
  │     ↓
  │     EvaluationDataset.from_list(records)
  │     ↓
  │     evaluate(metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
  │
  ├─ 4. _save_results()
  │     写入 summary.txt + per_sample.csv
  │
  └─ 5. _save_comparison()
         Side-by-side delta 表 + 按 category 分层 + 按 source_pdf 分层
```

### 两种检索配置对比

| 维度 | Baseline | Agentic RAG |
|------|----------|-------------|
| 查询分类 | 无 | `QueryRouter.classify()` → exact / summary |
| 检索参数 | 固定 `top_k=20, top_n=5` | Router 动态：exact=20/5, summary=30/7 |
| 质量评估 | 无 | `RetrievalCritic.evaluate()` |
| 改写重检 | 从不 | `RetrievalCritic.reformulate()` → 最多 1 次 |
| 实现 | `store.retrieve(query, top_k=20, top_n=5)` | `retrieve_document_structured(query)` |

### Generator Prompt

```
你是一个财务文档问答助手。请严格基于下面提供的文档片段回答用户的问题。
要求：
1. 如果片段中包含答案，直接回答并引用相关片段编号
2. 如果片段中部分包含答案，回答已知部分并说明哪些信息缺失
3. 如果片段中完全没有答案，诚实地说「根据提供的文档片段，无法回答此问题」，不要编造

文档片段：
[片段1] ...
[片段2] ...
---

用户问题：{question}

请回答：
```

### RAGAS Judge 配置

照搬 `course/RAG.ipynb` 的已验证配置：

```python
from langchain_openai import ChatOpenAI

judge_llm = ChatOpenAI(
    model="deepseek-v4-pro",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com/",
    temperature=0,
)
```

4 个指标：
- **faithfulness** — 回答是否忠实于检索到的上下文（测幻觉）
- **answer_relevancy** — 回答是否切题
- **context_precision** — 检索到的 chunks 是否相关（测信噪比）
- **context_recall** — 是否检索到了所有需要的信息（测覆盖率）

---

## 六、前置验证（`ragas_eval_verify.py`）

完整 RAGAS 评估跑 **28 对 × 2 配置 ≈ 112 次 LLM 调用**（~30 分钟），先花 2 分钟跑前置验证避免浪费 API 费用：

### 检查 1：文档可用性
- 确认 PDF 文件存在
- 确认 Qdrant 中有非零 chunks（打印每文档 chunk 数）

### 检查 2：检索覆盖
- 每对用宽检索（`top_k=20, top_n=10`）获取 chunks
- 对每个 chunk 用 `difflib.SequenceMatcher` 计算与 reference 的模糊匹配
- 至少 1 个 chunk 匹配度 ≥ 0.6 → 通过
- 目标：≥ 85% 的 QA 对通过（计算类和诚实性探针除外）

### 检查 3：诚实性探针
- 4 对诚实性探针的检索结果应**不包含**答案内容
- 全部通过才算合格

### 检查 4：生成器抽查
- 跑 3 对代表性 QA（1 direct_lookup + 1 multi_chunk + 1 honesty_probe）
- 打印生成结果供人工 spot-check
- 确认 prompt 设计没有明显缺陷

```
=== QA Pair Verification ===
总QA对数: 28
检索覆盖: 25/28 通过 (89.3%)

未通过:
  [FAIL] "ABC Technology的CEO是谁？" — reference未在检索片段中找到 (expected: 诚实性探针 ✓)
  [WARN] "投资10万扣费后净收益..." — reference相似度仅0.45 (计算题，需生成器推理，合理)

诚实性探针检查: 4/4 正确 ✓

Generator 抽查:
  Q: "ABC Technology 2024财年的总营收是多少？"
  A: "根据片段[1]，ABC Technology 2024财年总营收为85.2亿元人民币"  ✓
  ...
```

---

## 七、对比报告格式

```
======================================================================
  RAGAS 评估对比：基础 RAG vs Agentic RAG（智能检索）
======================================================================
样本数: 28  |  embedding: BAAI/bge-base-zh-v1.5
judge: deepseek-v4-pro (temperature=0)
chunk_size=500, chunk_overlap=80

指标                 基础RAG      智能RAG       提升
─────────────────────────────────────────────────────
faithfulness         0.xxxx       0.xxxx       +0.xxxx
answer_relevancy     0.xxxx       0.xxxx       +0.xxxx
context_precision    0.xxxx       0.xxxx       +0.xxxx
context_recall       0.xxxx       0.xxxx       +0.xxxx

─────────────────────────────────────────────────────
按问题类型分层
─────────────────────────────────────────────────────
direct_lookup (15对):
  context_precision:  基础=0.xxxx  智能=0.xxxx
  context_recall:     基础=0.xxxx  智能=0.xxxx

multi_chunk (9对):
  context_precision:  基础=0.xxxx  智能=0.xxxx
  context_recall:     基础=0.xxxx  智能=0.xxxx

honesty_probe (4对):
  faithfulness:       基础=0.xxxx  智能=0.xxxx

─────────────────────────────────────────────────────
解读提示（面试时讲）:
• context_recall 提升 → Router 扩大的 top_k 覆盖了更多跨块信息
• context_precision 持平或提升 → Critic 改写没有引入噪声
• faithfulness 持平或更好 → Agentic 不损害忠实度
• 诚实性探针 faithfulness → 评估系统对"无法回答"场景的处理
```

---

## 八、实施顺序

### Day 8（~4 小时）

| # | 任务 | 产出 | 预计 |
|---|------|------|:---:|
| 1 | 读 `generate_financial_pdf.py` + `generate_product_pdf.py`，确认 PDF 实际内容 | 内容清单 | 30min |
| 2 | 写 `tools/qa_pairs.py`（28 对，含 reference + 元数据） | QA 对数据集 | 45min |
| 3 | 跑 `ragas_eval_verify.py` 前置验证，修正不通过的 QA 对 | 验证通过的 QA 对 | 30min |
| 4 | 重构 `retrieve_tool.py`：提取 `_do_retrieve()` + 新增 `retrieve_document_structured()` | 结构化检索接口 | 45min |
| 5 | 搭建 `ragas_eval.py` 骨架：LLM 配置 + baseline 检索路径 + 生成器 + RAGAS evaluate | 可运行的评估脚本 | 60min |

### Day 9（~4 小时）

| # | 任务 | 产出 | 预计 |
|---|------|------|:---:|
| 6 | 加 Agentic 检索路径 + 对比逻辑 | 完整对比管道 | 45min |
| 7 | 跑完整评估：baseline（~15min）→ agentic（~15min） | 原始评估数据 | 30min |
| 8 | 生成对比报告 + 按 category/source_pdf 分层分析 | `comparison.txt` | 45min |
| 9 | 人工审查逐样本 CSV 异常值（faithfulness=0 的样本、context_recall 极低的样本） | 异常分析笔记 | 45min |
| 10 | 更新 `CLAUDE.md` 加评估命令 | 文档 | 15min |

---

## 九、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| RAGAS `ChatOpenAI` 不接受 DeepSeek API key | 评估跑不起来 | `course/RAG.ipynb` 已验证可行，照搬其 `ChatOpenAI` 配置 |
| Generator 编造不在 contexts 中的答案 | faithfulness 分数虚高 | Prompt 显式约束 + 诚实性探针作为金丝雀检测 |
| Agentic 的 `reformulate()` 引入非确定性（同一 query 两次结果不同） | 对比结果不可复现 | Judge 用 temperature=0，记录完整配置快照 |
| API 成本高（~112 次 LLM 调用：28对×2配置×(1生成+1评判)） | 费用 | 前置验证先跑 3 对确认无误，再全量跑 |
| `LangchainLLMWrapper` 未来版本废弃 | 脚本未来跑不起来 | 在代码中加注释标注迁移路径（→ `ragas.llms.llm_factory`） |

---

## 十、验证方法

```bash
# Step 1: 前置验证（2 分钟，无 LLM 调用）
python tools/ragas_eval_verify.py

# Step 2: 完整评估（约 30 分钟，含 LLM 调用）
python tools/ragas_eval.py

# Step 3: 查看对比报告
cat course/ragas_finance_comparison.txt

# Step 4: 人工抽查逐样本 CSV
# 打开 course/ragas_finance_baseline_per_sample.csv
# 检查 faithfulness=0 和 context_recall 极低的样本是否合理
```

---

## 十一、为后续任务留的接口

- **Day 10-11（Langfuse）**：`ragas_eval.py` 的 `generate_answer()` 和检索调用点可嵌入 Langfuse trace span
- **Week 3（README）**：对比报告数据可直接贴入 README 的「评估结果」章节
- **后续优化**：`ragas_eval.py` 的 `retrieve_fn` 参数化设计——换任何检索策略只需传一个新函数，不改脚本主体
- **CI 集成**：脚本是标准 Python 模块，`python tools/ragas_eval.py` 即可跑，可接入 GitHub Actions 做回归
