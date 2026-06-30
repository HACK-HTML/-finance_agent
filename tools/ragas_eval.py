"""
RAGAS 评估主脚本 —— 基础 RAG vs Agentic RAG 对比评估
=====================================================

基于 28 个财务 QA 对，用 RAGAS 四指标（faithfulness / answer_relevancy /
context_precision / context_recall）对比两种检索配置：

  - Baseline：固定 top_k=20 / top_n=5，无 Router / Critic
  - Agentic：QueryRouter 动态选策略 + RetrievalCritic 质量门控 + 改写重检

运行前先跑前置验证：python tools/ragas_eval_verify.py

用法：
  python tools/ragas_eval.py              # 全量跑（baseline + agentic）
  python tools/ragas_eval.py --baseline   # 只跑 baseline
  python tools/ragas_eval.py --agentic    # 只跑 agentic

输出：
  course/ragas_finance_baseline_summary.txt  + _per_sample.csv
  course/ragas_finance_agentic_summary.txt   + _per_sample.csv
  course/ragas_finance_comparison.txt        （对比报告）
"""
from __future__ import annotations

import os
import sys
import time
import argparse
from datetime import datetime

# 确保项目根目录在 sys.path 中
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# ── 导入项目模块 ──────────────────────────────────────────────────────────
from tools.qa_pairs import FINANCIAL_QA_PAIRS, get_pairs_by_category
from tools.rag_pipeline import get_store
from tools.retrieve_tool import retrieve_document_structured

EVAL_USER_ID = "ragas_eval_user"
OUTPUT_DIR = os.path.join(_PROJ_ROOT, "course")

# ── 检索函数（两种配置）────────────────────────────────────────────────────

def retrieve_baseline(query: str) -> list[str]:
    """基础 RAG：固定参数，无 Router / Critic。"""
    store = get_store()
    chunks = store.retrieve(query, user_id=EVAL_USER_ID, top_k=20, top_n=5)
    return [c.text for c in chunks]


def retrieve_agentic(query: str) -> list[str]:
    """Agentic RAG：Router 分类 + Critic 评估 + 可能改写重检。"""
    chunks, _ = retrieve_document_structured(query, user_id=EVAL_USER_ID)
    return [c.text for c in chunks]


# ── LLM 组件 ──────────────────────────────────────────────────────────────

def _build_llm_components():
    """创建 generator LLM + judge LLM + evaluator embeddings。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY 环境变量未设置。请设置后再运行。\n"
            "  export DEEPSEEK_API_KEY=your-key"
        )

    # Generator：生成回答（temperature 可以非零，但 0 更可复现）
    from langchain_openai import ChatOpenAI
    generator_llm = ChatOpenAI(
        model="deepseek-v4-pro",
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com/",
        temperature=0,
    )

    # Judge：RAGAS 评分（必须 temperature=0）
    from ragas.llms import LangchainLLMWrapper
    judge_llm = LangchainLLMWrapper(ChatOpenAI(
        model="deepseek-v4-pro",
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com/",
        temperature=0,
    ))

    # Embeddings：RAGAS context_precision / context_recall 用
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    evaluator_emb = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-base-zh-v1.5")
    )

    return generator_llm, judge_llm, evaluator_emb


# ── 生成器 ────────────────────────────────────────────────────────────────

_GENERATOR_PROMPT = (
    "你是一个财务文档问答助手。请严格基于下面提供的文档片段回答用户的问题。\n"
    "要求：\n"
    "1. 如果片段中包含答案，直接回答并引用相关片段编号\n"
    "2. 如果片段中部分包含答案，回答已知部分并说明哪些信息缺失\n"
    "3. 如果片段中完全没有答案，诚实地说「根据提供的文档片段，无法回答此问题」，不要编造\n\n"
    "文档片段：\n{contexts}\n\n"
    "用户问题：{question}\n\n"
    "请回答："
)


def generate_answer(question: str, contexts: list[str], llm) -> str:
    """基于检索到的 contexts 生成回答。"""
    if not contexts:
        return "根据提供的文档片段，无法回答此问题。"

    ctx_block = "\n\n---\n\n".join(
        f"[片段{i+1}] {c}" for i, c in enumerate(contexts)
    )
    prompt = _GENERATOR_PROMPT.format(contexts=ctx_block, question=question)

    try:
        resp = llm.invoke(prompt)
        return resp.content
    except Exception as e:
        print(f"  [WARN] 生成失败：{e}")
        return f"（生成错误：{e}）"


# ── 主评估流程 ─────────────────────────────────────────────────────────────

def run_evaluation(
    qa_pairs: list[dict],
    retrieve_fn,
    generator_llm,
    judge_llm,
    evaluator_emb,
    label: str,
) -> tuple[list[dict], object]:
    """
    对全部 QA 对跑一轮完整评估：
      retrieve → generate → build dataset → RAGAS evaluate

    返回：(records, ragas_result)
    """
    from ragas import EvaluationDataset, evaluate, RunConfig
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )

    print(f"\n{'=' * 60}")
    print(f"开始评估：{label}")
    print(f"{'=' * 60}")

    records = []
    for i, qa in enumerate(qa_pairs, 1):
        t0 = time.time()
        contexts = retrieve_fn(qa["question"])
        answer = generate_answer(qa["question"], contexts, generator_llm)
        elapsed = time.time() - t0

        records.append({
            "user_input": qa["question"],
            "retrieved_contexts": contexts,
            "response": answer,
            "reference": qa["reference"],
        })

        ctx_count = len(contexts)
        ans_preview = answer[:60].replace("\n", " ")
        print(f"  [{label}] [{i:02d}/{len(qa_pairs):02d}] "
              f"{qa['question'][:40]:40s} "
              f"ctx={ctx_count} {elapsed:.1f}s "
              f"→ {ans_preview}...")

    # 构建数据集 + 跑 RAGAS
    print(f"\n  构建 EvaluationDataset（{len(records)} 条）...")
    dataset = EvaluationDataset.from_list(records)

    print(f"  跑 RAGAS evaluate（4 指标）...")
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=evaluator_emb,
        run_config=RunConfig(max_workers=4, timeout=120),
    )

    print(f"\n  [{label}] 评估结果：")
    print(f"  {result}")
    return records, result


# ── 保存结果 ───────────────────────────────────────────────────────────────

def save_results(records: list[dict], result, label: str, config: dict) -> str:
    """保存聚合分数 + 逐样本 CSV。返回 summary 文件路径。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 逐样本 CSV
    df = result.to_pandas()
    csv_path = os.path.join(OUTPUT_DIR, f"ragas_finance_{label}_per_sample.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 聚合 summary
    summary_path = os.path.join(OUTPUT_DIR, f"ragas_finance_{label}_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"=== RAGAS Finance Evaluation: {label} ===\n")
        f.write(f"时间: {ts}\n")
        f.write(f"样本数: {len(records)}\n")
        f.write(f"配置:\n")
        for k, v in config.items():
            f.write(f"  {k} = {v}\n")
        f.write(f"\n{result}\n")

    print(f"  已保存：{summary_path}")
    print(f"  已保存：{csv_path}")
    return summary_path


# ── 对比报告 ───────────────────────────────────────────────────────────────

def save_comparison(result_baseline, result_agentic, records: list[dict]):
    """生成 side-by-side delta 表 + 分层分析。"""
    comp_path = os.path.join(OUTPUT_DIR, "ragas_finance_comparison.txt")

    def _get_score(result, metric_name: str) -> float:
        try:
            return float(result[metric_name])
        except (KeyError, TypeError, IndexError):
            return float("nan")

    metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    metric_labels = {
        "faithfulness": "忠实度（测幻觉）",
        "answer_relevancy": "答案相关性",
        "context_precision": "检索精度（信噪比）",
        "context_recall": "检索召回（覆盖率）",
    }

    with open(comp_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  RAGAS 评估对比：基础 RAG vs Agentic RAG（智能检索）\n")
        f.write("=" * 70 + "\n")
        f.write(f"样本数: {len(records)}\n")
        f.write("judge: deepseek-v4-pro (temperature=0)\n")
        f.write("embedding: BAAI/bge-base-zh-v1.5\n")
        f.write("chunk_size=500, chunk_overlap=80\n")
        f.write("baseline: top_k=20, top_n=5（固定）\n")
        f.write("agentic: Router 动态 + Critic 门控 + 最多 1 次改写重检\n\n")

        f.write(f"{'指标':<25s} {'基础RAG':>10s} {'智能RAG':>10s} {'提升':>10s}\n")
        f.write("-" * 55 + "\n")
        for m in metrics:
            b = _get_score(result_baseline, m)
            a = _get_score(result_agentic, m)
            delta = a - b if not (pd.isna(b) or pd.isna(a)) else float("nan")  # noqa: F821
            b_str = f"{b:.4f}" if not pd.isna(b) else "N/A"  # noqa: F821
            a_str = f"{a:.4f}" if not pd.isna(a) else "N/A"
            d_str = f"{delta:+.4f}" if not pd.isna(delta) else "N/A"
            f.write(f"{m:<25s} {b_str:>10s} {a_str:>10s} {d_str:>10s}\n")

        # 分层分析（按 category）
        f.write("\n" + "-" * 55 + "\n")
        f.write("按问题类型分层\n")
        f.write("-" * 55 + "\n")

        cats = ["direct_lookup", "multi_chunk", "honesty_probe"]
        for cat in cats:
            pairs = get_pairs_by_category(cat)
            f.write(f"\n{cat} ({len(pairs)}对):\n")
            if cat == "honesty_probe":
                f.write("  （诚实性探针主要关注 faithfulness——系统是否诚实说无法回答）\n")
            else:
                f.write(f"  context_precision / context_recall 有待后续分层评估时细化\n")

        # 面试解读提示
        f.write("\n" + "-" * 55 + "\n")
        f.write("解读提示（面试时讲）:\n")
        f.write("• context_recall 提升 → Router 扩大的 top_k 覆盖了更多跨块信息\n")
        f.write("• context_precision 持平或提升 → Critic 改写没有引入噪声\n")
        f.write("• faithfulness 持平或更好 → Agentic 不损害忠实度\n")
        f.write("• 诚实性探针 faithfulness → 评估系统对无法回答场景的处理\n")

    print(f"  已保存：{comp_path}")


# ── 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估：Baseline vs Agentic RAG")
    parser.add_argument("--baseline", action="store_true", help="只跑 baseline")
    parser.add_argument("--agentic", action="store_true", help="只跑 agentic")
    args = parser.parse_args()

    run_both = not args.baseline and not args.agentic

    # 确保文档已入库
    store = get_store()
    if not store.has_documents(EVAL_USER_ID):
        print("首次运行：将财务 PDF 入库到 Qdrant ...")
        _proj = _PROJ_ROOT
        for pdf_name in ["ABC_Tech_2024_Annual_Report.pdf",
                         "Huaxia_Stable_Growth_365_Prospectus.pdf"]:
            pdf_path = os.path.join(_proj, pdf_name)
            if os.path.exists(pdf_path):
                r = store.ingest_pdf(pdf_path, user_id=EVAL_USER_ID)
                print(f"  {pdf_name}: {r['chunks']} chunks")

    # 构建 LLM 组件
    print("初始化 LLM 组件 ...")
    generator_llm, judge_llm, evaluator_emb = _build_llm_components()
    print("  generator: deepseek-v4-pro")
    print("  judge:     deepseek-v4-pro (temperature=0)")
    print("  embedding: BAAI/bge-base-zh-v1.5")

    config = {
        "generator": "deepseek-v4-pro",
        "judge": "deepseek-v4-pro (temperature=0)",
        "embedding": "BAAI/bge-base-zh-v1.5",
        "chunk_size": 500,
        "chunk_overlap": 80,
        "qa_pairs": len(FINANCIAL_QA_PAIRS),
    }

    result_baseline = None
    result_agentic = None

    # Baseline
    if run_both or args.baseline:
        records_bl, result_baseline = run_evaluation(
            FINANCIAL_QA_PAIRS, retrieve_baseline,
            generator_llm, judge_llm, evaluator_emb,
            label="baseline",
        )
        save_results(records_bl, result_baseline, "baseline", {
            **config, "retrieval": "固定 top_k=20, top_n=5（无 Router/Critic）",
        })

    # Agentic
    if run_both or args.agentic:
        records_ag, result_agentic = run_evaluation(
            FINANCIAL_QA_PAIRS, retrieve_agentic,
            generator_llm, judge_llm, evaluator_emb,
            label="agentic",
        )
        save_results(records_ag, result_agentic, "agentic", {
            **config, "retrieval": "Router 动态策略 + Critic 门控 + 最多 1 次改写重检",
        })

    # 对比报告
    if result_baseline is not None and result_agentic is not None:
        print(f"\n{'=' * 60}")
        print("生成对比报告 ...")
        save_comparison(result_baseline, result_agentic, FINANCIAL_QA_PAIRS)

    print("\n完成。输出文件在 course/ 目录下。")


if __name__ == "__main__":
    # pandas 在 save_comparison 中用到，顶部 lazy import 避免脚本启动慢
    import pandas as pd
    main()
