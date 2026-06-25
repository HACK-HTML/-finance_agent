# 💰 个人财务分析 Agent

> 第一阶段毕业项目：手写 ReAct 循环 · Claude Tool Use · Pydantic 验证 · FastAPI 服务化

---

## 项目结构

```
finance_agent/
├── core/
│   └── agent.py          ← ⭐ 核心：手写 ReAct 循环（必须精读）
├── models/
│   └── schemas.py        ← Pydantic 数据模型，理解强类型建模
├── tools/
│   └── registry.py       ← 工具实现 + Schema 定义（理解 Function Calling）
├── server.py             ← FastAPI 服务，多会话管理
├── main.py               ← 命令行交互界面
└── requirements.txt
```

---

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置 API Key
export ANTHROPIC_API_KEY="sk-0402c2d39c1746a68fdd4dc59d1c61cf"

# 3a. 命令行模式（推荐先用这个）
python main.py

# 3b. API 服务模式
uvicorn server:app --reload
# 访问 http://localhost:8000/docs 查看接口文档
```

---

## 核心学习点

### 1. ReAct 循环（`core/agent.py`）

```
用户输入
   ↓
Claude 思考（stop_reason = "tool_use"）
   ↓
执行工具（_execute_tools）
   ↓
把结果作为 user 消息反馈（Observe）
   ↓
Claude 继续推理 → 再次判断是否需要工具
   ↓
Claude 直接回答（stop_reason = "end_turn"）
```

**关键代码位置：** `while iteration < MAX_ITERATIONS` 循环体

### 2. 消息历史管理

每次工具调用后，必须把以下两条消息加入 `state.messages`：
1. `{"role": "assistant", "content": response.content}` — Claude 的工具调用决定
2. `{"role": "user", "content": tool_results}` — 工具执行结果

顺序错误或遗漏任何一条，API 会报错。

### 3. Pydantic 的作用（`models/schemas.py`）

- `Transaction` 验证用户输入的交易数据（amount 不能为 0）
- `AgentState` 统一管理消息历史和工具调用记录
- `MonthlyReport` 是结构化输出的目标格式（进阶：让 Claude 直接输出 JSON 并用 Pydantic 解析）

### 4. 工具描述质量（`tools/registry.py`）

工具描述越清晰，Agent 调用越准确。关键要素：
- **何时调用**：`所有需要计算的运算必须通过此工具`
- **参数格式**：给出具体示例 `如 '(5000 - 3200) / 5000'`
- **限制说明**：`不要自行心算`

---

## 挑战练习（完成基础后尝试）

### 🟡 中级：结构化输出
让 Claude 直接输出 `MonthlyReport` JSON，用 Pydantic 解析验证：

```python
# 在 System Prompt 中加入：
"当用户请求月度报告时，输出符合以下 JSON Schema 的内容：{MonthlyReport.model_json_schema()}"

# 解析 Claude 输出
import json
from models.schemas import MonthlyReport
from core.agent import FinanceAgent
raw = FinanceAgent.chat("给我生成一份月度报告")
report = MonthlyReport.model_validate(json.loads(raw))  
```

### 🟠 高级：并行工具调用
当前实现是串行处理 tool_use。Claude 有时会在一次响应中请求多个工具（如同时查汇率+查基金），改为并行执行：

```python
import asyncio
# 提示：用 asyncio.gather(*[async_tool(t) for t in tool_blocks])
```

### 🔴 进阶：添加 Write 操作（Context Engineering 预习）
在 `AgentState` 中加入 `scratchpad: str` 字段，
给 Agent 增加 `save_note(content: str)` 工具，
让 Agent 在多步任务中主动记录中间推理结果。

---

## API 接口示例

```bash
# 发起对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "月收入12000，支出8000，存款5万，评估健康度"}'

# 继续同一会话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我制定预算方案", "session_id": "上一步返回的session_id"}'

# 查看会话详情
curl http://localhost:8000/session/{session_id}
```

---

## 验收标准

完成项目后，你应该能清楚回答：

1. `stop_reason == "tool_use"` 和 `stop_reason == "end_turn"` 分别代表什么？
2. 工具调用结果为什么要用 `role: "user"` 而不是 `role: "tool"` 发回给 Claude？
3. 为什么要设 `MAX_ITERATIONS` 上限？什么情况下 Agent 会无限循环？
4. Pydantic 的 `field_validator` 在 Agent 系统中解决什么问题？
5. 工具的 `description` 字段对 Agent 行为有多大影响？（试着故意写一个模糊的描述，观察 Claude 的行为变化）
