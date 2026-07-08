# 💰 个人财务分析 AI Agent

手写 ReAct 循环 · Agentic RAG · Mem0 跨会话记忆 · LangFuse 可观测 · Docker 部署

[![Test](https://github.com/KeWang/finance_agent/actions/workflows/test.yml/badge.svg)](https://github.com/KeWang/finance_agent/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)

一个从零手写的 AI Agent 学习项目——**没有 LangChain、没有 LlamaIndex、没有任何 Agent 框架**。7 个 Python 文件实现完整的 ReAct 推理循环，配合 Qdrant 向量检索、Mem0 持久记忆、LangFuse 全链路追踪。

---

## 功能特性

- **ReAct 推理循环** — 手写 `while` 循环驱动 Claude 思考→工具调用→观察→再思考，支持并行工具执行（`asyncio.gather`），最多 10 轮安全截断
- **8 个工具** — 数学计算、支出分析、财务健康评估、预算方案生成、汇率查询、基金信息、文档检索、记忆召回
- **Agentic RAG** — QueryRouter 分类问题类型 + 两阶段检索（向量召回 → Cross-Encoder 重排）+ RetrievalCritic 评估质量并自动改写重检
- **Mem0 跨会话记忆** — 渐进式披露：system prompt 注入轻量摘要（~100 token），按需调用 `memory_recall` 获取完整上下文
- **Budget Plan 双层审查** — LLM Critic 外部审查（数值参数调整）→ Self-Reflection 自我反思（逻辑合理性审视）→ 版本比较，保留最优方案
- **LangFuse 全链路追踪** — 零框架依赖，追踪层次：Session Trace → ReAct 迭代 Span → LLM Generation + Tool Span → RAG Pipeline 子 Span
- **Docker 一键部署** — `docker-compose up -d` 启动 app + Qdrant 向量库，支持 Server / CLI / CLI-Demo 三种模式，内置健康检查

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                     Interface Layer                      │
│          main.py (CLI)  │  server.py (FastAPI)           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    FinanceAgent                          │
│              core/agent.py — ReAct Loop                  │
│                                                          │
│  while iteration < 10:                                   │
│    Claude 思考 ──→ stop_reason?                          │
│      │ end_turn: 返回最终回答                             │
│      │ tool_use: asyncio.gather(工具1, 工具2, ...)        │
│      │          → 结果作为 user 消息回传 → 继续下一轮      │
└──────┬───────────────┬───────────────┬──────────────────┘
       │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────────┐
│  8 Tools    │ │  RAG Pipeline│ │  Memory (Mem0)      │
│  registry   │ │  Qdrant +    │ │  search / recall    │
│  .py        │ │  Reranker    │ │  manager.py         │
└─────────────┘ └─────────────┘ └─────────────────────┘
```

## 快速开始

### 本地开发

```bash
# 1. 克隆
git clone https://github.com/KeWang/finance_agent.git
cd finance_agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env 填入你的 DEEPSEEK_API_KEY

# 4. 加载环境变量
source .env  # Linux/Mac
# 或 Windows: 手动设置系统环境变量

# 5. 命令行交互模式
python main.py

# 6. API 服务模式
python -m uvicorn server:app --reload
# 打开 http://localhost:8000/docs 查看 Swagger 文档
```

### Docker 部署

```bash
# 1. 配置 API Key
export DEEPSEEK_API_KEY=sk-your-key-here

# 2. 启动服务（Server 模式）
docker-compose up -d

# 3. 验证健康状态
curl http://localhost:8000/health
# → {"status":"healthy"}

# 4. CLI 交互模式
docker-compose --profile cli run --rm cli

# 5. CLI 演示模式（3 个预设问题）
docker-compose --profile cli run --rm cli-demo

# 6. 停止
docker-compose down           # 保留数据
docker-compose down -v        # 清空全部数据
```

---

## 项目结构

```
finance_agent/
├── core/
│   └── agent.py               ← ReAct 循环（while + asyncio.gather）
├── models/
│   └── schemas.py             ← Pydantic 数据模型 + 验证器
├── tools/
│   ├── registry.py            ← 8 个工具实现 + Anthropic Tool Schema
│   ├── rag_pipeline.py        ← Qdrant 向量库 + 切块 + 两阶段 Reranker
│   ├── retrieve_tool.py       ← Agentic RAG（Router + Critic + 改写重检）
│   ├── budget_plan.py         ← 预算计算 + LLM Critic + Self-Reflection
│   ├── tracing.py             ← LangFuse 基础设施（装饰器 + 上下文管理器）
│   ├── ragas_eval.py          ← RAGAS 评估（Baseline vs Agentic RAG 对比）
│   └── budget_plan_judge.py   ← LLM-as-Judge 预算方案评估（10 用例）
├── memory/
│   └── manager.py             ← Mem0 跨会话记忆（渐进式披露）
├── server.py                  ← FastAPI HTTP 服务（多会话管理 + 中间件）
├── main.py                    ← CLI 交互界面（/upload /demo /stats /reset）
├── test.py                    ← 单元测试（_extract_text）
├── Dockerfile                 ← 多阶段构建（builder → slim runtime）
├── docker-compose.yml         ← 编排 app + Qdrant 服务
├── requirements.txt           ← Python 依赖
├── .env.example               ← 环境变量模板
└── .gitignore
```

---

## 环境变量

| 变量 | 必须 | 说明 |
|------|:--:|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API Key |
| `LANGFUSE_PUBLIC_KEY` | | LangFuse 公钥（不配则跳过所有追踪） |
| `LANGFUSE_SECRET_KEY` | | LangFuse 私钥 |
| `LANGFUSE_HOST` | | LangFuse 服务地址 |
| `QDRANT_URL` | | 远程 Qdrant 地址（Docker 自动设为 `http://qdrant:6333`） |
| `MEM0_QDRANT_URL` | | Mem0 的 Qdrant 地址（同上） |
| `MEM0_HISTORY_DB` | | Mem0 SQLite 历史路径（Docker 自动设） |
| `DEBUG` | | 设为 `1` 时每轮 ReAct 打印完整消息历史 |

---

## API 接口

启动 `python -m uvicorn server:app` 后访问 `http://localhost:8000/docs`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 服务状态 + 活跃会话数 |
| `GET` | `/health` | 健康检查（Docker probe） |
| `POST` | `/chat` | 发送消息，返回 Agent 回答 |
| `POST` | `/upload` | 上传 PDF 入库 |
| `GET` | `/session/{id}` | 查看会话详情 |
| `DELETE` | `/session/{id}` | 重置会话 |
| `GET` | `/sessions` | 列出所有活跃会话 |

```bash
# 对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "月收入12000，支出8000，存款5万，评估财务健康度"}'

# 继续同一会话（传入返回的 session_id）
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我制定预算方案", "session_id": "xxx"}'

# 上传 PDF
curl -X POST http://localhost:8000/upload \
  -F "file=@理财产品说明书.pdf" \
  -F "user_id=wangke"
```

---

## 评估

| 评估 | 文件 | 说明 |
|------|------|------|
| RAGAS | `tools/ragas_eval.py` | Baseline vs Agentic RAG 对比（Context Precision / Recall / Faithfulness） |
| Budget Judge | `tools/budget_plan_judge.py` | LLM-as-Judge 评估 10 个用例（含 Critics 循环前后对比 + 数值正确性校验） |

```bash
# RAGAS 评估
python tools/ragas_eval_verify.py   # 预检（2min，无 LLM 调用）
python tools/ragas_eval.py          # 完整评估（~30min）

# Budget Plan 评估
python tools/budget_plan_judge.py   # 10 个用例 + Critics 前后对比
```

---

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| LLM | DeepSeek V4 Pro (via Anthropic SDK) | 推理 + 工具决策 |
| 数据模型 | Pydantic v2 | 强类型验证（含 field_validator + model_validator） |
| 向量库 | Qdrant (Rust) | RAG 文档存储 + Mem0 记忆存储 |
| Embedding | FastEmbed (ONNX) | bge-small-zh-v1.5 + bge-reranker-base |
| 记忆 | Mem0 | LLM 提取 → embedding → 去重/合并 → 写入 Qdrant |
| 可观测 | LangFuse | session trace → 迭代 span → LLM generation → tool span |
| Web | FastAPI + Uvicorn | HTTP API + Swagger 文档 |
| 容器 | Docker + Compose | 多服务编排（app + Qdrant） |
| 评估 | RAGAS + LLM-as-Judge | 检索质量 + 预算方案质量 |

---

## 面试要点

这是一个为面试设计的"手写 Agent"项目，核心谈资：

1. **为什么不调 LangChain 的 AgentExecutor？** → 手写 ReAct 循环让你完全掌控推理→行动→观察的每一步；理解 Anthropic API 的 `stop_reason` 机制（`tool_use` vs `end_turn`）；面试官更看重"你懂原理"而不是"你会调库"

2. **并行工具执行怎么做的？** → `asyncio.gather()` 并发执行同一轮中 Claude 请求的所有工具；用 `asyncio.to_thread()` 包裹同步工具函数，不阻塞事件循环

3. **RAG 为什么是两阶段？** → 向量召回（宽召回 top_k=20）+ Cross-Encoder 精排（精度优先 top_n=5）；Embedding 是双塔模型（query 和 passage 独立编码），Cross-Encoder 是交互模型（query×passage 联合打分）——后者更准但更慢，所以只在缩小后的候选集上跑

4. **Agentic RAG 的 Router 和 Critic 解决了什么问题？** → Router 分类"精确查找"vs"概括总结"，调不同召回数；Critic 用重排分数评估检索质量，不合格时自动改写查询重试（最多 1 次）

5. **LangFuse 追踪的层次设计？** → context manager 管理 span 生命周期（`try/finally` 保证 end）；`trace_context` dict 传递父子关系；PII 脱敏后再发送；LangFuse 未配置时全部 no-op 零开销

6. **Mem0 为什么在 system prompt 注入摘要而不是直接注入全部记忆？** → 渐进式披露（progressive disclosure）——先给 Agent 轻量结构预览，Agent 判断需要时才调 `memory_recall` 拉详情。避免 context window 浪费在不相关的记忆上

---

## License

MIT © 2026 KeWang
