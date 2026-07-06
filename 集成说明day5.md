# Week 1 · Day 5 集成说明 —— Agentic RAG：Router + Critic

> 目标（计划原文）：把 RAG 从"固定两阶段检索"升级为"Agentic RAG"——
> Router 根据问题类型选检索策略（精确查找 vs 摘要类），Critic 评估检索质量、不够则重检索。
> 参考 Context Engineering 的 Write / Select / Compress / Isolate 四操作。

---

## 一、本次做了什么

### 核心功能

1. **QueryRouter**：中文财务查询分类器，将用户问题分为 `exact`（精确查找）和 `summary`（概括总结）两类，自动选择不同的 `top_k`/`top_n` 检索参数
2. **RetrievalCritic**：利用已有的 Cross-Encoder 重排序分数评估检索质量，平均分 < 0.3 或最高分 < 0.5 时判定为不合格，触发查询改写 + 重检索（最多 1 次）
3. **零侵入**：Router + Critic 全部封装在 `retrieve_document()` 工具内部，Agent 的 ReAct 循环、`TOOL_SCHEMAS` 无任何改动

### 为什么叫"Agentic RAG"

普通 RAG 是无条件检索一次就生成，Agentic RAG 是检索前先判定"怎么查"，检索后评估"查得够不够"——
这就是 Context Engineering 的 **Select** 操作（选什么进上下文、怎么选）+ 反馈闭环。

---

## 二、文件清单

```
finance_agent/
└── tools/
    └── retrieve_tool.py     ← ✏️ 改：加 QueryRouter + RetrievalCritic 两个类，
                                 修改 retrieve_document() 函数内部流程（+112 行）
```

🆕 无新增文件；✏️ 仅一个文件改动

**未改的文件（不需要动）**：

| 文件 | 原因 |
|------|------|
| `tools/rag_pipeline.py` | `retrieve()` 已支持可选的 `top_k`/`top_n` 覆盖参数（Day 1-2 留的接口） |
| `core/agent.py` | Router/Critic 在工具内部，ReAct 循环透明 |
| `tools/registry.py` | TOOL_SCHEMAS 不变——Agent 看到的工具描述和以前完全一样 |
| `models/schemas.py` | 无新数据类型 |

---

## 三、代码结构

```
tools/retrieve_tool.py
├── QueryRouter                          ← 🆕 ~35 行
│   ├── _EXACT_RE      正则：费率/赎回/多少/第X条/是什么…
│   ├── _SUMMARY_RE    正则：总结/概括/主要/整体/怎么投资…
│   ├── classify()     输入 query → 返回 "exact" 或 "summary"
│   └── get_strategy() 返回 {"top_k": N, "top_n": M}
│
├── RetrievalCritic                      ← 🆕 ~45 行
│   ├── MIN_AVG_SCORE = 0.3
│   ├── MIN_MAX_SCORE = 0.5
│   ├── evaluate()     输入 chunks → 返回 (ok, reason)
│   └── reformulate()  输入 (原query, 失败原因) → 返回 改写后的 query
│
├── retrieve_document()                  ← ✏️ 核心流程改动 ~30 行
│   ├── guard（知识库为空）—— 不变
│   ├── Router.classify() → get_strategy()     ← 🆕
│   ├── store.retrieve(strategy)               ← ✏️ 传 top_k/top_n
│   ├── Critic.evaluate() → reformulate()      ← 🆕
│   ├── store.retrieve(revised) [条件触发]      ← 🆕
│   └── 格式化输出 —— 基本不变（加了策略标注）
│
└── RETRIEVE_DOCUMENT_SCHEMA —— 不变
```

---

## 四、Router 分类规则

| 策略 | 匹配信号（中文正则） | top_k | top_n | 适用场景 |
|------|---------------------|-------|-------|---------|
| `exact` | 费率、赎回、多少、第X条、是什么、金额… | 20 | 5 | 事实查找：某费率是多少、第几条条款 |
| `summary` | 总结、概括、主要、整体、怎么投资… | 30 | 7 | 概括理解：这份文档讲什么、风险评估 |

默认 fallback = `exact`（保守，宁可窄召回也不错召）。

---

## 五、Critic 评估与改写规则

### 质量判定

| 检查 | 阈值 | 含义 |
|------|------|------|
| 无结果 | 0 条 | 直接不合格 |
| 平均分 | < 0.3 | 整体相关性弱 |
| 最高分 | < 0.5 | 最好片段也差（Cross-Encoder 分数范围约 0~1） |

### 查询改写（最多 1 次重试）

| 失败原因 | 改写策略 | 示例 |
|---------|---------|------|
| `no_results` | 截断问句后缀，保留核心关键词 | "赎回费率是多少？有没有优惠" → "赎回费率是多少" |
| `avg_low` / `max_low` | 注入金融领域词增强语义匹配 | "加密货币投资建议" → "理财产品 金融文档 加密货币投资建议" |
| 已有领域词 | 跳过改写，不重试 | "基金收益率分析" → (空，已有"基金""收益") |

---

## 六、验证方法

```bash
python main.py
```

### 测试 1：Router 分类正确
```bash
# 先上传一份中文财务 PDF
你：/upload ./产品说明书.pdf
你：赎回费率是多少              # → Router 选 exact，top_k=20/top_n=5
你：这份文档主要讲什么           # → Router 选 summary，top_k=30/top_n=7
```

观察输出头的 `策略=` 标注：
```
📚 文档检索结果（query=「赎回费率是多少」｜策略=exact｜按相关性排序）：
📚 文档检索结果（query=「这份文档主要讲什么」｜策略=summary｜按相关性排序）：
```

### 测试 2：Critic 改写重检
```bash
# 上传一份和加密货币无关的文档
你：/upload ./ABC_Tech_2024_Annual_Report.pdf
你：加密货币投资建议           # 文档里没有相关 → Critic 判不合格 → 改写重检
```

### 测试 3：不改写场景（回归）
```bash
你：基金收益率分析              # 查询本身已有领域词"基金""收益"
# → Critic 检测到已有领域词 → 不重复注入 → 直接返回结果
```

### 测试 4：空库兜底（回归）
```bash
# 没上传文档
你：这款产品费率是多少
# → "【知识库为空】当前用户还没有上传任何文档，无法检索。"
```

---

## 七、关键设计决策（面试时讲这些）

### 1. 为什么 Router + Critic 放在工具内部而不是 Agent 层？

参考 `generate_budget_plan` 的内部反思循环（`MAX_BUDGET_REVISIONS=2`）——项目里已有"工具内部自行优化"的模式。这样做有三个好处：
- **Agent 循环零改动**：ReAct 的职责是"选工具 → 看结果 → 判断是否继续"，不关心工具内部怎么优化
- **可独立测试**：Router 和 Critic 都是纯函数，可以单独写 pytest
- **可替换**：想换 LLM 做 Router 或接入 Cohere Rerank score，只改这两个类

### 2. 为什么用正则而不是 LLM 做 Router？

- 零延迟、零 token 消耗
- 中文财务查询的词汇信号非常明确（"费率""赎回""是多少"= 精确查找，"总结""整体""怎么投资"= 概括理解）
- LLM Router 虽然更泛化，但会增加 ~200-500ms 延迟 + 一轮 API 调用
- 正则不能覆盖的边界 case 走默认策略（exact），不会出错

### 3. 为什么用重排序分数做 Critic 而不是 LLM 判断？

重排序是 Cross-Encoder 对 `(query, passage)` 显式打分，这个分数本身就是检索质量的直接指标——**免费、即时、可量化**。LLM 判断虽然灵活但引入额外成本和延迟。用已有的分数做门控 = 零额外成本的质量保证。

### 4. 为什么最多只重检 1 次？

查询改写是启发式的（截断/注词），不是 LLM 的深度语义改写。同一查询改一次已经能覆盖大部分情况（无结果 + 得分低），再改也是同样的策略重复，没有新信息。遵循项目既有模式（`MAX_BUDGET_REVISIONS=2` 也是保守设置）。

### 5. 这和 Context Engineering 四操作的关系？

- **Select**：Router 选择检索策略（精确 vs 概括）——决定什么信息进上下文
- **Select 的反馈修正**：Critic 评估选择质量，不达标就改写重选
- **不涉及 Write**（记忆层）、**Compress**（超长才用）、**Isolate**（单 Agent 场景）——聚焦一个操作做扎实

---

## 八、数据流示意

```
Agent 调 retrieve_document(query="赎回费率是多少？有没有优惠")
  │
  ├─ 1. has_documents() guard ── 无文档 → 直接返回提示
  │
  ├─ 2. QueryRouter.classify("赎回费率是多少？有没有优惠")
  │     └─ _EXACT_RE 匹配"费率"+"多少" → "exact"
  │     └─ get_strategy("exact") → {top_k: 20, top_n: 5}
  │
  ├─ 3. store.retrieve(query, top_k=20, top_n=5)
  │     └─ 向量召回 20 条 → Cross-Encoder 精排 5 条
  │     └─ 返回 [chunk(score=0.85), chunk(score=0.72), ...]
  │
  ├─ 4. RetrievalCritic.evaluate(chunks)
  │     └─ avg=0.68 (>0.3 ✓), max=0.85 (>0.5 ✓) → ok=True, reason="ok"
  │     └─ 跳过重检
  │
  └─ 5. 格式化输出 "📚 文档检索结果（query=…｜策略=exact｜按相关性排序）："

── 如果分数低 ──

  ├─ 4'. Critic.evaluate([chunk(score=0.15)])
  │      └─ avg=0.15 (<0.3 ✗) → ok=False, reason="avg_low(0.15),max_low(0.15)"
  │
  ├─ 5'. Critic.reformulate(query, "avg_low(0.15)")
  │      └─ query 不含金融词 → "理财产品 金融文档 赎回费率是多少？有没有优惠"
  │
  ├─ 6'. store.retrieve(revised_query, top_k=30, top_n=5)  ← 重检
  │
  └─ 7'. 格式化输出（同上）
```

---

## 九、踩坑备忘

| 风险 | 应对 |
|------|------|
| 正则覆盖不全（边界 case） | 默认 fallback = `exact`，不丢信息 |
| 改写后的 query 和原来一样 | `revised != query` 检查，相同则跳过重检 |
| 改写后 query 太短 | `len(shortened) >= 4` 检查，太短不重检 |
| 重复注入领域词 | 检测 query 是否已有理财/基金/投资等词，有则跳过 |
| Critic 门控太严导致漏检 | 门控在 `_ensure_collection` 和 `retrieve()` 返回空列表之间，不干预正常检索 |
| 和 Agent 工具选择逻辑冲突 | Router/Critic 在工具内部，Agent 按原来的 tool schema 判断是否调用——两套逻辑互不干扰 |

---

## 十、为 Day 6-7 留的接口

Day 6-7 要做"端到端打通 + 修 bug"：
- Router 的 `_EXACT_RE` / `_SUMMARY_RE` 正则列表可根据真实财务文档测试结果微调
- Critic 的 `MIN_AVG_SCORE=0.3` / `MIN_MAX_SCORE=0.5` 阈值可在 RAGAS 评估时网格搜索最佳值
- Week 2 做 RAGAS 时可直接对比"有 Router+Critic" vs "无 Router+Critic"的四指标差异
