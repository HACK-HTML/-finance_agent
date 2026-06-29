# Week 1 · Day 1-2 集成说明 —— 把 Agentic RAG 接进财务 Agent

> 目标（计划原文）：把 RAG pipeline 作为一个「文档检索工具」`retrieve_document` 接入财务 Agent，
> 让 Agent 能在「调用计算工具」和「检索文档」之间自主选择，复用第一阶段的 TOOL_REGISTRY 机制。
> RAG 采用 **Qdrant + 切块 + 两阶段 Rerank** 的 Agentic RAG（不是 RAG.ipynb 里的 Chroma 版）。

---

## 一、文件清单（按你现有目录结构放置）

```
finance_agent/
├── tools/
│   ├── rag_pipeline.py     ← 🆕 RAG 核心：PDF→切块→Qdrant→两阶段检索+Rerank
│   ├── retrieve_tool.py    ← 🆕 retrieve_document 工具 + schema
│   └── registry.py         ← ✏️ 改：import + 注册工具 + 追加 schema（共 3 处小改动）
├── core/
│   └── agent.py            ← ✏️ 改：session_id + partial 绑定 + system prompt
├── server.py               ← ✏️ 改：新增 /upload 端点；按会话隔离；修复 chat 的 await
├── main.py                 ← ✏️ 改：新增 /upload <路径> 命令，方便命令行测试
└── requirements_rag.txt    ← 🆕 新增依赖
```

🆕 = 全新文件，直接放进去；✏️ = 在你原文件基础上改动，可直接用这里的整份替换。

---

## 二、安装依赖

```bash
pip install -r requirements_rag.txt
```

---

## 三、跑通整条链路（命令行最快）

```bash
python main.py
# 1) 先上传一份 PDF（理财产品说明书 / 账单 / 年报）
你：/upload ./产品说明书.pdf
✅ 文档已入库：{'doc_name': '产品说明书.pdf', 'chunks': 12}

# 2) 直接问文档里的内容 —— Agent 会自己决定调用 retrieve_document
你：这款产品的赎回费率是怎么算的？
# 3) 再问一个该用计算工具的问题 —— Agent 不会去检索文档，而是调 calculate
你：我月入12000、支出8500，储蓄率是多少？
```

观察 ReAct 日志里 `[工具调用]` 这一行：文档类问题走 `retrieve_document`，
计算类问题走 `calculate` —— 这就是「Agent 在检索与计算间自主选择」的证据。

## 四、HTTP 方式（FastAPI）

```bash
uvicorn server:app --reload
# 上传（session_id 不传会自动生成并返回）
curl -F "file=@产品说明书.pdf" -F "session_id=u1" http://localhost:8000/upload
# 提问（带同一 session_id，检索被限定在这份文档内）
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
     -d '{"message":"赎回费率怎么算","session_id":"u1"}'
```

---

## 五、关键设计决策（面试时讲这些）

1. **为什么 Qdrant 不用 Chroma**
   Qdrant 原生支持 payload 过滤。我用 `session_id` 字段做多会话/多用户隔离——
   检索时 `Filter(session_id=当前会话)`，A 用户的文档绝不会被 B 用户检索到。
   （已用单测验证：跨会话零泄漏。）

2. **两阶段检索（提升 Context Precision 的核心手法）**
   - 阶段一：向量召回 top_k=20（双塔，召回优先、宽召回）
   - 阶段二：Cross-Encoder Reranker 精排出 top_n=5（query 与片段一起喂模型打分，更准）
   Week 2 做 RAGAS 时，可对比「只用向量」vs「加 Rerank」的 Context Precision 提升，
   就是数据驱动优化的证据。

3. **切块策略**
   递归切块：优先在段落/句子边界切（`\n\n`→`\n`→`。`→…），避免把一句话/一个数字切两半；
   相邻块加 80 字重叠窗口，防止跨块语义断裂。

4. **工具如何接进 ReAct（复用既有机制）**
   `retrieve_document` 就是 TOOL_REGISTRY 里一个普通工具，和 `calculate` 同级。
   `session_id` 是隐藏参数，不进 schema、不暴露给 LLM，由 `functools.partial` 绑定——
   和你之前给 `generate_budget_plan` 绑定 `_client` 是同一套手法。
   Agent 只看到 `query` 一个入参，纯靠工具 description 决定何时检索。

5. **踩坑点（计划点名的）**
   工具 description 用「触发时机 + 负向约束」双段式写清楚：
   *只有当答案藏在用户文档里时才检索；纯计算、实时行情、通用常识都不要走检索。*
   否则 Agent 会把「算储蓄率」也丢给检索，或硬算文档里的费率。

---

## 六、本环境已验证 / 未验证

- ✅ 已验证：PDF 抽取、递归切块+重叠、Qdrant 入库、**session 过滤检索零泄漏**、
  两阶段排序、工具空库提示与格式化输出、registry 注册、agent 的 partial 绑定与 schema 隔离。
- ⚠️ 未在本机跑：Embedding/Reranker 的真实推理（需联网下载 HuggingFace 模型）。
  在你本地联网环境首次运行会自动下载；若受限用 `export HF_ENDPOINT=https://hf-mirror.com`。

---

## 七、为 Day 5 留的接口

Day 5 要加 Router + Critic 把 RAG 升级成完整 Agentic：
- **Router**：`store.retrieve(query, top_k, top_n)` 已支持按问题类型动态传不同 top_k/top_n
  （精确查找用小 k、摘要类用大 k）。
- **Critic**：`retrieve()` 返回的 `RetrievedChunk.score` 就是重排相关性分，
  可据此判断「检索质量是否够」，不够则改写 query 重检索。
两个钩子都已经留好，Day 5 在工具外面包一层循环即可，不用动 pipeline 内核。
