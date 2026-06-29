"""
Agentic RAG 检索管线 —— Qdrant + 切块 + 两阶段 Rerank
================================================================

对应《冲刺计划》2.2 系统架构里的「📚 RAG 检索：Qdrant + 切块 + Rerank」一层。

设计取舍（面试可讲）：
  1. 向量库用 Qdrant（Rust 内核，原生 payload 过滤），不用 Chroma —— 支持
     按 session_id 过滤检索，天然适配多会话/多用户隔离。
  2. 检索是「两阶段」的：先用向量召回 top_k（粗排，召回优先），再用 Cross-Encoder
     Reranker 精排出 top_n（精度优先）。这是提升 RAGAS Context Precision 的标准手法。
  3. Embedding / Reranker 都走 FastEmbed（ONNX，本地推理，免 API key、可离线），
     默认中文模型 bge-small-zh-v1.5 + bge-reranker-base；想换 Cohere Rerank 只需
     替换 Reranker.rerank() 一处实现。
  4. 切块用「递归 + 重叠」：优先在段落/句子边界切，避免把一句话/一个数字切两半，
     重叠窗口保证跨块语义不丢。

这一层对 Agent 完全透明：Agent 只看到 registry 里的 `retrieve_document` 工具，
不关心底层是 Qdrant 还是 Chroma。
"""
from __future__ import annotations

import os
import re
import uuid
import threading
from dataclasses import dataclass, field
from typing import Optional, Iterable

from qdrant_client import QdrantClient, models


# ── 配置 ──────────────────────────────────────────────────────────────────────
@dataclass
class RAGConfig:
    """所有可调参数集中在此，便于做 Eval 时网格搜索（Week 2 用得上）。"""
    # 存储：默认本地持久化（关掉重开文档还在）；设为 ":memory:" 则纯内存，跑测试用。
    # 生产环境把它指向 Qdrant 服务地址（QdrantClient(url="http://...")）。
    qdrant_location: str = field(
        default_factory=lambda: os.getenv("QDRANT_PATH", "./storage/qdrant")
    )
    collection_name: str = field(
        default_factory=lambda: os.getenv("RAG_COLLECTION", "finance_docs")
    )

    # 模型
    embed_model: str = field(
        default_factory=lambda: os.getenv("RAG_EMBED_MODEL", "BAAI/bge-base-zh-v1.5")
    )
    rerank_model: str = field(
        default_factory=lambda: os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base")
    )

    # 切块
    chunk_size: int = 500          # 单块目标字符数
    chunk_overlap: int = 80        # 相邻块重叠字符数，跨块保语义

    # 检索：两阶段
    top_k: int = 20                # 第一阶段向量召回数（粗排，宽召回）
    top_n: int = 5                 # 第二阶段 rerank 后保留数（精排，进上下文）

    # bge 系列检索时官方建议给 query 加指令前缀，passage 不加
    query_instruction: str = "为这个句子生成表示以用于检索相关文章："


# ── 1. PDF 文本抽取（按页，保留页码做引用）──────────────────────────────────────
def extract_pdf_pages(pdf_path: str) -> list[tuple[int, str]]:
    """返回 [(page_number, page_text), ...]，页码从 1 开始。空白页自动跳过。"""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = _clean_text(text)
        if text.strip():
            pages.append((i, text))
    return pages


def _clean_text(text: str) -> str:
    """归一化空白：合并多余空行/空格，避免切块时被空白干扰。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── 2. 递归切块（优先在语义边界切 + 重叠窗口）────────────────────────────────────
# 分隔符按「语义强度」从强到弱排列：段落 > 换行 > 英文句子 > 中文句子 > 分号 > 空格
_SEPARATORS = ["\n\n", "\n", ".", "!", "?", "。", "！", ";", "；", " ", ""]


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    递归字符切块：尽量在高层级分隔符处切，块仍超长就降级到更细的分隔符。
    切完再做重叠拼接，保证相邻块共享 `overlap` 个字符的上下文。
    """
    raw = _recursive_split(text, _SEPARATORS, chunk_size)
    return _merge_with_overlap(raw, chunk_size, overlap)


def _recursive_split(text: str, separators: list[str], chunk_size: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep = separators[0]
    rest = separators[1:]

    if sep == "":
        # 最后兜底：硬切（极端长且无任何分隔符的串）
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    parts = text.split(sep)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        piece = part + sep
        if len(buf) + len(piece) <= chunk_size:
            buf += piece
        else:
            if buf.strip():
                chunks.append(buf)
            # 单个 part 自己就超长 → 用更细的分隔符继续递归切
            if len(piece) > chunk_size:
                chunks.extend(_recursive_split(piece, rest, chunk_size))
                buf = ""
            else:
                buf = piece
    if buf.strip():
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]


def _merge_with_overlap(chunks: list[str], chunk_size: int, overlap: int) -> list[str]:
    """给相邻块加重叠：每块开头接上一块的末尾 `overlap` 个字符。"""
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for cur in chunks[1:]:
        prev_tail = out[-1][-overlap:]
        out.append((prev_tail + cur)[:chunk_size + overlap])
    return out


# ── 3. Embedding / Reranker 封装（FastEmbed，可替换）──────────────────────────────
class _Embedder:
    """延迟加载的向量编码器。passage 与 query 分别编码（bge 建议给 query 加指令）。"""

    def __init__(self, model_name: str, query_instruction: str = ""):
        self.model_name = model_name
        self.query_instruction = query_instruction
        self._model = None
        self._dim: Optional[int] = None

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(self.model_name)
            # 探测维度，避免硬编码（不同模型维度不同）
            probe = next(iter(self._model.embed(["dim_probe"])))
            self._dim = len(probe)

    @property
    def dim(self) -> int:
        self._ensure()
        return self._dim  # type: ignore[return-value]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self._ensure()
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        self._ensure()
        q = f"{self.query_instruction}{text}" if self.query_instruction else text
        return next(iter(self._model.embed([q]))).tolist()


class _Reranker:
    """
    第二阶段精排：Cross-Encoder 对 (query, passage) 直接打分，比双塔向量更准。
    默认本地 FastEmbed bge-reranker-base。
    想换 Cohere：把 rerank() 内部换成 cohere.Client().rerank(...) 即可，接口不变。
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            self._model = TextCrossEncoder(self.model_name)

    def rerank(self, query: str, docs: list[str], top_n: int) -> list[tuple[int, float]]:
        """返回 [(原始下标, 相关性分数), ...]，按分数降序，取前 top_n。"""
        if not docs:
            return []
        self._ensure()
        scores = list(self._model.rerank(query, docs))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]


# ── 4. 文档库：ingest（建库）+ retrieve（两阶段检索）─────────────────────────────
@dataclass
class RetrievedChunk:
    text: str
    source: str
    page: int
    score: float


class DocumentStore:
    """
    一个进程内单例就够用（见文件底部 get_store()）。
    Qdrant 用 payload 字段 session_id 做多会话隔离 —— 这是选 Qdrant 而非 Chroma 的核心理由之一。
    """

    def __init__(self, config: Optional[RAGConfig] = None):
        self.cfg = config or RAGConfig()
        self.client = QdrantClient(location=self.cfg.qdrant_location)
        self.embedder = _Embedder(self.cfg.embed_model, self.cfg.query_instruction)
        self.reranker = _Reranker(self.cfg.rerank_model)
        self._lock = threading.Lock()

    # —— 建库 ——
    def _ensure_collection(self):
        if not self.client.collection_exists(self.cfg.collection_name):
            self.client.create_collection(
                collection_name=self.cfg.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedder.dim,           # 维度从模型探测，不硬编码
                    distance=models.Distance.COSINE,  # bge 用余弦相似度
                ),
            )

    def ingest_pdf(self, pdf_path: str, user_id: str = "default",
                   session_id: str = "", doc_name: Optional[str] = None) -> dict:
        """抽取 → 切块 → 编码 → 写入 Qdrant。返回入库统计。"""
        doc_name = doc_name or os.path.basename(pdf_path)
        pages = extract_pdf_pages(pdf_path)
        if not pages:
            return {"doc_name": doc_name, "pages": 0, "chunks": 0,
                    "warning": "未抽取到任何文本（可能是扫描件，需要 OCR）"}

        records: list[tuple[str, int]] = []  # (chunk_text, page)
        for page_no, page_text in pages:
            for ch in chunk_text(page_text, self.cfg.chunk_size, self.cfg.chunk_overlap):
                records.append((ch, page_no))

        return self._upsert(records, user_id, session_id, doc_name)

    def ingest_text(self, text: str, user_id: str = "default",
                    session_id: str = "", doc_name: str = "inline_text") -> dict:
        """直接喂纯文本（测试 / 非 PDF 来源用）。"""
        chunks = chunk_text(_clean_text(text), self.cfg.chunk_size, self.cfg.chunk_overlap)
        records = [(c, 0) for c in chunks]
        return self._upsert(records, user_id, session_id, doc_name)

    def _upsert(self, records: list[tuple[str, int]], user_id: str,
                session_id: str, doc_name: str) -> dict:
        with self._lock:
            self._ensure_collection()

            # ★ 幂等：同一用户内重传同名文档 = 替换
            replaced = self._delete_by_source(user_id, doc_name)

            texts = [r[0] for r in records]
            vectors = self.embedder.embed_passages(texts)
            points = [
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={
                        "text": text,
                        "source": doc_name,
                        "page": page,
                        "user_id": user_id,           # ★ Day 3-4：检索隔离改按用户
                        "session_id": session_id,      # 保留供审计
                    },
                )
                for (text, page), vec in zip(records, vectors)
            ]
            self.client.upsert(self.cfg.collection_name, points=points)
        return {"doc_name": doc_name, "chunks": len(points), "replaced_old_chunks": replaced}

    def _delete_by_source(self, user_id: str, doc_name: str) -> int:
        """删除某用户下某文档已有的全部 chunk，返回删除前的数量（无则 0）。"""
        if not self.client.collection_exists(self.cfg.collection_name):
            return 0
        flt = models.Filter(must=[
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
            models.FieldCondition(key="source", match=models.MatchValue(value=doc_name)),
        ])
        existed = self.client.count(self.cfg.collection_name, count_filter=flt).count
        if existed:
            self.client.delete(self.cfg.collection_name,
                               points_selector=models.FilterSelector(filter=flt))
        return existed

    # —— 检索（两阶段）——
    def retrieve(self, query: str, user_id: str = "default",
                 top_k: Optional[int] = None, top_n: Optional[int] = None
                 ) -> list[RetrievedChunk]:
        top_k = top_k or self.cfg.top_k
        top_n = top_n or self.cfg.top_n

        if not self.client.collection_exists(self.cfg.collection_name):
            return []

        # 阶段一：向量粗召回（只在当前用户的文档里找）
        flt = models.Filter(must=[models.FieldCondition(
            key="user_id", match=models.MatchValue(value=user_id))])
        hits = self.client.query_points(
            collection_name=self.cfg.collection_name,
            query=self.embedder.embed_query(query),
            query_filter=flt,
            limit=top_k,
            with_payload=True,
        ).points
        if not hits:
            return []

        # 阶段二：Cross-Encoder 精排
        docs = [h.payload["text"] for h in hits]
        ranked = self.reranker.rerank(query, docs, top_n)
        out: list[RetrievedChunk] = []
        for idx, score in ranked:
            p = hits[idx].payload
            out.append(RetrievedChunk(
                text=p["text"], source=p["source"], page=p["page"], score=float(score)))
        return out

    # —— 杂项 ——
    def has_documents(self, user_id: str = "default") -> bool:
        if not self.client.collection_exists(self.cfg.collection_name):
            return False
        flt = models.Filter(must=[models.FieldCondition(
            key="user_id", match=models.MatchValue(value=user_id))])
        got, _ = self.client.scroll(self.cfg.collection_name, scroll_filter=flt, limit=1)
        return len(got) > 0


# ── 5. 进程内单例 ────────────────────────────────────────────────────────────────
_STORE: Optional[DocumentStore] = None
_STORE_LOCK = threading.Lock()


def get_store() -> DocumentStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = DocumentStore()
    return _STORE
