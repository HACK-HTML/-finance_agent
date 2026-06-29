"""
MemoryManager —— Mem0 跨会话记忆封装
=====================================

设计取舍（面试可讲）：
  1. 选用 Mem0 而非手写 extract + store：3 个 API（add/search/get_all）极简，
     内部的 LLM 提取 + embedding + 去重/合并（ADD/UPDATE/DELETE/NOOP）全自动，
     不需要我们维护提取 pipeline。
  2. 写入是 fire-and-forget 异步：add_async() 丢线程池执行，不阻塞 Agent 回答返回。
     这是 Letta/Mem0/Zep 等所有主流项目的共识——同步写入会阻塞响应链路。
  3. 检索走渐进式披露：search() 只返回轻量摘要注入 system prompt（~100 token），
     Agent 需要完整记忆时调 memory_recall 工具按需拉取。灵感来自 claude-mem（83k stars）
     的三层搜索架构，财务场景映射为两层。
  4. 相关性门控：threshold=0.7 过滤低相关记忆，防止"月薪12000"被注入到"SPY净值查询"中。
  5. 隔离维度用 user_id：和 Day 3-4 同步修复的 RAG 检索一致——文档和记忆都用 user_id 隔离，
     不再出现"新 session 找不到旧 session 上传的文档"的问题。
"""
from __future__ import annotations

import threading
from typing import Optional


class MemoryManager:
    """Mem0 记忆的读写封装。每个 user_id 一个实例。"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._memory = None
        self._lock = threading.Lock()

    def _ensure(self):
        """延迟初始化 Mem0 客户端（首次 add/search 时才加载模型）。"""
        if self._memory is None:
            with self._lock:
                if self._memory is None:
                    from mem0 import Memory
                    # Qdrant collection 和 finance_docs 隔离
                    # Mem0 内部用 SQLite 存元数据，Qdrant 存向量
                    config = {
                        "vector_store": {
                            "provider": "qdrant",
                            "config": {
                                "collection_name": "user_memories",
                                "path": "./storage/qdrant",
                            },
                        },
                        "history_db_path": "./storage/mem0_history.db",
                    }
                    self._memory = Memory.from_config(config)

    # ── 写入（异步 fire-and-forget）──────────────────────────────────────────────

    def add_async(self, text: str) -> None:
        """
        从文本中自动提取关键事实并持久化。
        内部流程：LLM 提取 → embedding → 去重/合并 → 写入 Qdrant。
        不返回任何值——调用方用 create_task + to_thread 包裹，不阻塞主循环。
        """
        try:
            self._ensure()
            self._memory.add(text, user_id=self.user_id)
        except Exception as e:
            print(f"[Mem0 add error] user={self.user_id}: {e}")

    # ── 检索（每轮对话前调用）────────────────────────────────────────────────────

    def search(self, query: str, threshold: float = 0.7,
               top_k: int = 3) -> list[dict]:
        """
        搜索与 query 相关的记忆，过滤低于 threshold 的结果。
        返回格式：[{"content": "...", "score": 0.92}, ...]
        空列表表示无相关记忆或知识库为空。
        """
        try:
            self._ensure()
            raw = self._memory.search(query, user_id=self.user_id, limit=top_k)
        except Exception as e:
            print(f"[Mem0 search error] user={self.user_id}: {e}")
            return []

        results = []
        for item in raw:
            score = item.get("score", 0.0)
            content = item.get("memory", "")
            if score >= threshold and content.strip():
                results.append({"content": content.strip(), "score": score})
        return results

    # ── 摘要格式化（注入 system prompt）───────────────────────────────────────────

    def format_summary(self, results: list[dict]) -> str:
        """
        把 search() 的返回格式化成注入 system prompt 的文本。
        空列表时返回一句话提示，避免 Agent 误以为系统出错。
        """
        if not results:
            return "（暂无相关用户记忆）"

        lines = [
            "以下是从之前对话中提取的用户信息摘要（按相关性排序）。",
            "如果和当前问题相关，请在回答中主动利用这些信息给出个性化建议；",
            "如果需要某个条目的完整上下文，调用 memory_recall 工具检索详情；",
            "如果和当前问题无关，忽略即可。",
            "",
        ]
        for r in results:
            lines.append(f"- [相关度 {r['score']:.2f}] {r['content']}")
        return "\n".join(lines)

    # ── 管理用 ──────────────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """获取该用户所有记忆（调试 / 管理用）。"""
        try:
            self._ensure()
            return self._memory.get_all(user_id=self.user_id)
        except Exception as e:
            print(f"[Mem0 get_all error] user={self.user_id}: {e}")
            return []
