"""
FastAPI 服务 — 把 Agent 包装成 HTTP API
提供：多会话管理 / 流式响应 / 会话历史查询 / 健康检查
"""

import uuid
import os
import shutil
import asyncio
import tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

# 把项目根目录加入 Python 路径
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.agent import FinanceAgent
from tools.rag_pipeline import get_store

app = FastAPI(
    title="💰 个人财务 Agent API",
    description="基于 DeepSeek 的财务分析助手，手写 ReAct 循环，无框架依赖",
    version="1.0.0",
)

# 内存中维护多个会话（生产环境应用 Redis）
sessions: dict[str, FinanceAgent] = {}


# ── 请求/响应模型 ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # 不传则自动创建新会话


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    turn_count: int
    tool_calls_used: int


class SessionInfo(BaseModel):
    session_id: str
    turn_count: int
    total_tool_calls: int
    message_count: int
    history: list[dict]


# ── 路由 ──────────────────────────────────────────────────────────────────────

@app.get("/", summary="服务健康检查")
def root():
    return {
        "status": "✅ running",
        "agent": "Finance Assistant",
        "sessions_active": len(sessions),
    }


@app.post("/chat", response_model=ChatResponse, summary="发送消息给 Agent")
async def chat(req: ChatRequest):
    """
    主要对话接口。
    - session_id 不传时自动创建新会话
    - 同一 session_id 保持多轮对话记忆，并把文档检索限定在该会话上传的文档内
    """
    # 获取或创建会话
    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = FinanceAgent(session_id=sid)   # ★ 把会话 id 传进去
        print(f"[新会话] {sid}")

    agent = sessions[sid]

    # 执行 ReAct 循环（chat 是 async，必须 await）
    reply = await agent.chat(req.message)

    return ChatResponse(
        session_id=sid,
        reply=reply,
        turn_count=agent.state.turn_count,
        tool_calls_used=agent.state.total_tool_calls,
    )


@app.post("/upload", summary="上传 PDF 文档进入指定会话的知识库")
async def upload(file: UploadFile = File(...), session_id: str | None = Form(None)):
    """
    用户上传 PDF → 切块 + 向量化 → 写入该会话的 Qdrant 知识库。
    之后同一 session_id 的对话里，Agent 即可用 retrieve_document 检索这份文档。
    """
    sid = session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = FinanceAgent(session_id=sid)

    # 落到临时文件再交给 ingest（pypdf 需要文件路径）
    suffix = os.path.splitext(file.filename or "doc.pdf")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        # ingest 是同步且较重（模型推理），丢到线程池避免阻塞事件循环
        stats = await asyncio.to_thread(
            get_store().ingest_pdf, tmp_path, sid, file.filename
        )
    finally:
        os.unlink(tmp_path)

    # replaced_old_chunks > 0 说明同名文档已存在，本次为「替换」而非「新增」
    replaced = stats.get("replaced_old_chunks", 0)
    if replaced:
        message = (f"♻️ 检测到重复上传，已用新版本替换旧文档"
                   f"（清理旧片段 {replaced} 块，写入新片段 {stats['chunks']} 块）")
    else:
        message = f"✅ 文档已入库（{stats['chunks']} 块），可以开始提问"

    return {"session_id": sid, "message": message, **stats}


@app.get("/session/{session_id}", response_model=SessionInfo, summary="查看会话详情")
def get_session(session_id: str):
    """查看某个会话的完整对话历史和工具调用记录"""
    agent = sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = [
        {"turn": i + 1, "user": t.user, "assistant": t.assistant[:200] + "..."}
        for i, t in enumerate(agent.state.turns)
    ]

    return SessionInfo(
        session_id=session_id,
        turn_count=agent.state.turn_count,
        total_tool_calls=agent.state.total_tool_calls,
        message_count=len(agent.state.messages),
        history=history,
    )


@app.delete("/session/{session_id}", summary="重置会话")
def reset_session(session_id: str):
    """清空指定会话的对话历史"""
    if session_id in sessions:
        sessions[session_id].reset()
        return {"message": f"会话 {session_id} 已重置"}
    raise HTTPException(status_code=404, detail="会话不存在")


@app.get("/sessions", summary="列出所有活跃会话")
def list_sessions():
    return {
        "count": len(sessions),
        "sessions": [
            {"session_id": sid, "summary": agent.state.summary()}
            for sid, agent in sessions.items()
        ]
    }