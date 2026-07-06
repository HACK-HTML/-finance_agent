## Project overview

Personal financial analysis AI Agent — hand-coded ReAct loop using the Anthropic SDK (via DeepSeek API with Anthropic-compatible endpoint), Pydantic validation, Qdrant-based Agentic RAG, and Mem0 cross-session memory. Built as a learning project for Agentic RAG and LLM tool-use engineering.

## Commands

```bash
# CLI interactive mode
python main.py

# CLI demo mode (3 preset questions)
python main.py --demo

# FastAPI server → Swagger at http://localhost:8000/docs
python server.py

# Unit tests
python test.py

# Budget plan LLM-as-Judge evaluation (10 test cases)
python tools/budget_plan_judge.py

# Smoke test — verify all modules import
python -c "
from core.agent import FinanceAgent
from models.schemas import AgentState, BudgetPlan
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS
print(f'{len(TOOL_REGISTRY)} tools loaded')
"

# Generate sample PDFs for RAG testing
python generate_financial_pdf.py
python generate_product_pdf.py

# RAGAS evaluation — baseline vs Agentic RAG comparison
python tools/ragas_eval_verify.py   # pre-flight check (2 min, no LLM)
python tools/ragas_eval.py          # full eval (~30 min)

# LangFuse observability — trace viewer
# Requires: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
python main.py --demo               # then open LangFuse Dashboard
```

IMPORTANT: No `requirements.txt` exists. Dependencies are managed ad-hoc in `.venv/`. Key packages: `anthropic`, `pydantic`, `fastapi`, `uvicorn`, `qdrant-client`, `fastembed`, `pypdf`, `fpdf2`, `mem0ai`.

## Architecture

```
main.py / server.py          ← Interface layer (CLI + FastAPI)
core/agent.py                ← ReAct loop: FinanceAgent class
tools/registry.py            ← 8 tools + Anthropic tool schemas
tools/rag_pipeline.py        ← Qdrant ingest/retrieve with 2-stage rerank
tools/retrieve_tool.py       ← Agentic RAG: QueryRouter + RetrievalCritic
tools/budget_plan.py         ← Budget computation + internal LLM critic loop
memory/manager.py            ← Mem0 persistent memory (fire-and-forget writes)
models/schemas.py            ← Pydantic models (AgentState, BudgetPlan, etc.)
```

**Data flow through the ReAct loop (`core/agent.py`):**
1. User input → appended to `AgentState.messages`
2. System prompt built dynamically (injects memory summaries from Mem0)
3. `client.messages.create()` called with tools + message history
4. If `stop_reason == "end_turn"`: extract text, store turn in memory (fire-and-forget), return
5. If `stop_reason == "tool_use"`: execute tools concurrently via `asyncio.gather`, append results as `role: "user"` messages, loop
6. Max 10 iterations (safety limit)

**API configuration** (set via environment variables, see `.env.example`):
- Model: `deepseek-v4-pro` via `https://api.deepseek.com/anthropic`
- `DEEPSEEK_API_KEY` — main API key (used for both agent and critic clients)
- `MEM0_LLM_KEY` — Mem0 LLM/embedding key (falls back to `OPENAI_API_KEY`)
- `MEM0_API_KEY` — Mem0 service API key
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — LangFuse observability (all optional; tracing skipped if missing)

## LangFuse observability (`tools/tracing.py`)

Zero-dependency integration via LangFuse Python SDK — no LangChain callbacks, no OpenTelemetry. All tracing is opt-in: if the three LangFuse env vars are not set, every trace call is a no-op (zero overhead).

**Trace hierarchy:** `Trace (session) → Span (ReAct iteration | tool execution) → Generation (LLM call)`

**Instrumented spans:**

| Span | What it captures |
|------|-----------------|
| `agent.chat` | Top-level trace per conversation turn (tags: user_id, session_id, interface) |
| `react.iteration_N` | Each ReAct loop iteration |
| `llm.react` | Main LLM inference (model, stop_reason, input/output chars, duration) |
| `tool.{name}` | Each tool execution (input, output truncated, duration, error) |
| `llm.budget_critic` | Budget plan critic LLM call |
| `router.classify` / `critic.evaluate` / `retrieve.vector_search` / `retrieve.reformulate_retry` | Agentic RAG pipeline stages |
| `api.{method} {path}` | FastAPI HTTP request trace (middleware) |
| `llm.generate_from_contexts` | RAGAS evaluation generation |

**PII scrubbing:** `scrub_content()` redacts emails, phone numbers, Chinese ID numbers, and API keys from all content before sending to LangFuse.

**FastAPI integration:** `server.py` middleware creates an HTTP-level trace, then passes it to `FinanceAgent` via `_langfuse_trace` parameter so agent spans nest cleanly under the request trace.

```bash
# Configure (all optional — tracing skipped if any is missing)
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com

# Verify — run demo, then open LangFuse Dashboard
python main.py --demo
```

## Key patterns

- **Tool descriptions** use a dual-segment pattern: "trigger conditions" (when to call) + "negative constraints" (when NOT to call), with Chinese examples in `input_examples`
- **Hidden parameters**: `_client`, `_memory`, `user_id` are bound via `functools.partial` in `agent.py` — the LLM never sees them
- **Tool results** are fed back as `role: "user"` messages (not `role: "tool"`) — this is an Anthropic API requirement for the Messages API without native tool-use support
- **Memory writes** are fire-and-forget (`asyncio.create_task`) — never block the ReAct response
- **Memory reads** are progressive disclosure: `search()` returns lightweight summaries (~100 tokens) for system prompt injection; full details on demand via the `memory_recall` tool
- **RAG** uses `user_id` filtering for multi-user document isolation; re-ingesting the same doc replaces old chunks (idempotent)
- **RAG retrieval** is two-stage: vector recall (top_k via FastEmbed bge-small-zh-v1.5) → Cross-Encoder rerank (top_n via bge-reranker-base)
- **Agentic RAG**: `QueryRouter` classifies queries as "exact" vs "summary" to tune retrieval params; `RetrievalCritic` evaluates result quality and triggers reformulation + retry if scores are below threshold
- **Budget plans** include an internal LLM critic loop: generate plan → LLM reviews it → optional refinement, before returning to the user

## Coding conventions

See @.claude/rules/python.md for Python coding conventions (path-scoped: loads only when editing `**/*.py` or `**/*.ipynb`).

## Testing

- `test.py` — standalone script with print-based assertions (not pytest). Tests `_extract_text()` with 3 scenarios.
- `tools/budget_plan_judge.py` — LLM-as-Judge eval across 10 test cases (from `tools/budget_plan_testcase.py`). Scores on savings reasonableness, actionability, goal alignment (1-5 scale), plus programmatic numerical correctness check. Compares plans with vs without the critic reflection loop.
- Course materials → see @.claude/rules/course.md (path-scoped: loads when working in `course/**`). Includes RAGAS evaluation baselines for the RAG pipeline.

## Storage

- `storage/qdrant/` — local Qdrant for RAG documents (collection: `finance_docs`, 512-dim, Cosine)
- `storage/mem0_qdrant/` — local Qdrant for Mem0 memories (collections: `user_memories` + `user_memories_entities`)
- `storage/mem0_history.db` — SQLite history for Mem0 LLM extraction
- All storage directories are git-ignored

## Session management (server.py)

In-memory session dict (`sessions: dict[str, FinanceAgent]`) — not production-ready. Each session has its own AgentState, message history, and tool history. Sessions are created per `session_id` (UUID if not provided) and keyed by `user_id` for RAG/memory isolation.
