# Week 1 · Day 3-4 集成说明 —— 接入 Mem0 跨会话记忆（渐进式披露）

> 目标（计划原文）：用户说"我月薪 12000、想买房" → Mem0 自动提取并存储 → 下次对话 Agent 主动记得这些信息，不用重复问。

---

## 一、本次做了什么

### 核心功能

1. **Mem0 跨会话记忆**：同一 `user_id` 的不同 session 之间共享用户记忆，关掉重开仍记得
2. **渐进式披露** ：每轮只注入轻量摘要（~100 token），Agent 需要详情时自主调 `memory_recall` 工具
3. **修复 RAG 隔离维度**：文档检索从 `session_id` 改为 `user_id`，和记忆用同一套隔离（同一用户的不同 session 都能查到文档）

### 设计灵感（来自高 star 开源项目调研）

| 设计决策 | 灵感来源 | 做法 |
|---------|---------|------|
| 渐进式披露（摘要 → 详情） | claude-mem (83k stars) | 系统注入摘要，Agent 自主拉详情 |
| 异步写入不阻塞回答 | Letta / Mem0 / Zep 全部采用 | `asyncio.create_task` fire-and-forget |
| 相关性门控 threshold=0.7 | Zep/memgov | 低于 threshold 的记忆不注入 |
| 记忆检索作为 Agent 工具 | claude-mem / LangMem | `memory_recall` 和 `retrieve_document` 同级 |

---

## 二、文件清单

```
finance_agent/
├── memory/
│   ├── __init__.py           ← 🆕 3 行，导出 MemoryManager
│   └── manager.py            ← 🆕 ~100 行，Mem0 封装：add_async / search / format_summary
├── core/
│   └── agent.py              ← ✏️ 改：user_id + MemoryManager + _make_system_prompt + 异步存储
├── tools/
│   ├── registry.py           ← ✏️ 改：加 memory_recall 函数 + schema + 注册
│   ├── retrieve_tool.py      ← ✏️ 改：session_id → user_id
│   └── rag_pipeline.py       ← ✏️ 改：ingest/retrieve/has_documents/_delete_by_source 全改 user_id
├── models/
│   └── schemas.py            ← ✏️ 改：加 MemorySummary 模型
├── server.py                 ← ✏️ 改：ChatRequest + /upload 加 user_id 字段
└── requirements_mem0.txt     ← 🆕 1 行：mem0ai
```

🆕 = 全新文件；✏️ = 在现有基础上改动

---

## 三、安装依赖

```bash
pip install -r requirements_mem0.txt
```

首次运行 Mem0 可能需要下载 HuggingFace embedding 模型（和 rag_pipeline 一样，断网用 `HF_ENDPOINT=https://hf-mirror.com`）。

---

## 四、跑通跨会话记忆（测试流程）

```bash
uvicorn server:app --reload
```

### 会话 A：建立记忆

```bash
# 1. 第一轮对话 —— 告诉 Agent 你的情况
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我月薪12000，存了5万，想买房，偏好低风险投资", "user_id": "alice"}'

# 返回的 session_id 记为 sid_a
```

### 会话 B：跨会话验证

```bash
# 2. 关掉重开（新 session_id，同一 user_id），问一个需要记忆的问题
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我手头有5万该怎么分配", "user_id": "alice"}'

# Agent 应该：
#   - system prompt 中看到记忆摘要：[0.92] 用户月薪12000 / [0.85] 想买房 / [0.78] 偏好低风险
#   - 摘要足够 → 直接基于记忆给出"留3万应急，2万考虑低风险债基"这类个性化建议
#   - 不调 memory_recall（摘要信息足够）

# 3. 再问一个需要详细记忆的问题
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "评估一下我的财务健康度", "user_id": "alice"}'

# Agent 应该：
#   - 摘要说月薪12000+想买房，但不知道月支出 → 调 memory_recall("月收入 月支出 储蓄 买房")
#   - 拿到完整记忆后调 evaluate_financial_health
```

### 验证记忆不越界

```bash
# 4. 问一个和用户信息无关的问题
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "SPY基金怎么样", "user_id": "alice"}'

# 记忆 search("SPY基金") → 相关度 < 0.7 → 全过滤 → system prompt 尾部显示"（暂无相关用户记忆）"
# Agent 不应调 memory_recall，直接调 get_fund_info("SPY")
```

### 上传文档跨会话验证（顺带验证 RAG 修复）

```bash
# 会话 A 上传文档
curl -F "file=@产品说明书.pdf" -F "user_id=alice" http://localhost:8000/upload

# 会话 B（新 session_id，同一 user_id）查询文档
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "这款产品的赎回费率怎么算", "user_id": "alice"}'
# → Agent 调 retrieve_document → ✅ 能查到会话 A 上传的文档（同一 user_id）
```

---

## 五、关键设计决策（面试时讲这些）

### 1. 为什么不每轮把完整记忆注入 system prompt？

参考 claude-mem（83k stars）的渐进式披露架构。每轮只注入轻量摘要（~100 token），Agent 需要详情时自己调用 `memory_recall` 工具。这样做的好处：
- 避免 context pollution（上下文超过 500-750 token 开始让模型退化）
- Agent 比系统更擅长判断"这条记忆和当前问题有关吗"
- 节省 20-30 倍 token

### 2. 为什么文档检索和记忆用同一隔离维度（user_id）？

Day 1-2 的实现按 `session_id` 隔离文档，导致切 session 就找不到自己上传的文档。本方案把检索的过滤字段统一为 `user_id`——文档和记忆同一套隔离，符合用户直觉："我的文档"和"我的记忆"都跟我走。

### 3. 为什么异步写入？

Mem0 的 `add()` 需要 LLM 提取事实 → embedding → 去重 → 写入，耗时 2-5 秒。同步写入会让用户等。`asyncio.create_task` + `to_thread` = 回答立即返回，记忆写完后台完成。Letta/Mem0/Zep 都这么做。

### 4. 为什么 threshold=0.7？

防止"月薪 12000"被注入到"SPY 净值查询"中。0.7 是经验值——太低会注污染，太高会漏相关记忆。Week 2 做 RAGAS 评估时可以网格搜索最佳值。

### 5. 工具 description 怎么防止 Agent 滥用 memory_recall？

和 `retrieve_document` 同一套设计模式——"触发时机 + 负向约束"。关键是：
- 正向：摘要相关但不够详细 → 调
- 负向：纯计算/汇率/基金/常识 → 不要调
- 具体措辞见 `tools/registry.py` 中 `MEMORY_RECALL_SCHEMA["description"]`

---

## 六、数据流示意

```
POST /chat {user_id: "alice", session_id: "s2", message: "我手头有5万该怎么分配"}
  │
  ├─ 1. MemoryManager("alice").search("5万怎么分配")
  │     └─ mem0.search() → [("月薪12000", 0.89), ("想买房", 0.85)]
  │     └─ 全过 0.7 ✅ → 拼成摘要注入 system prompt 尾部（~100 token）
  │
  ├─ 2. ReAct 循环
  │     ├─ Agent 看到摘要：月薪12000 + 想买房 → 摘要信息够用，不调 memory_recall
  │     └─ Agent 直接回答（基于记忆给个性化分配建议）
  │
  └─ 3. asyncio.create_task(asyncio.to_thread(mem0.add("用户：5万怎么分配\n助手：...")))

--- 用户关掉浏览器，重新打开 ---

POST /chat {user_id: "alice", session_id: "s3", message: "我的财务状况健康吗"}
  │
  ├─ 1. search("财务状况健康") → [("月薪12000", 0.75), ("想买房", 0.71)]
  │     └─ 注入摘要
  │
  ├─ 2. Agent 看摘要：知道月薪12000+想买房，但不知道月支出和存款
  │     → 调 memory_recall("月收入 月支出 储蓄金额 买房计划")
  │     → 拿到完整记忆 → 调 evaluate_financial_health(income=12000, expense=..., savings=...)
  │
  └─ 3. asyncio.create_task(...)
```

---

## 七、踩坑备忘

| 风险 | 应对 |
|------|------|
| `add()` 阻塞 ReAct 返回 | `create_task` + `to_thread`, fire-and-forget |
| 无关记忆污染对话 | search 的 `threshold=0.7` 门控 + system prompt 写"不相关就忽略" |
| Mem0 和项目 Qdrant 冲突 | 不同 collection：`user_memories` vs `finance_docs` |
| 首次下载 embedding 模型 | 和 rag_pipeline 一样，设 `HF_ENDPOINT=https://hf-mirror.com` |
| `memory_recall` 被 Agent 滥用 | schema description 里明确负向约束 |
| 文档跨 session 查不到 | **本轮已修复**：retrieve/has_documents 的 filter 从 session_id 改为 user_id |
| 记忆越积越多 | Mem0 内置 LRU 淘汰；后续可加 `max_memories_per_user` 检查 |

---

## 八、为 Day 5 留的接口

Day 5 要做 Agentic RAG 的 Router + Critic，和记忆层无关。本方案不改动 rag_pipeline 的检索内核（embedding / reranker / 两阶段排序都没动），只改了过滤维度（session_id → user_id），不影响 Day 5 的计划。
