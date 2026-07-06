"""
RAGAS 评估前置验证 —— 在跑完整的 RAGAS evaluate（~112 次 LLM 调用）之前，
用快速检查避免浪费 API 费用。

检查项：
  1. 文档可用性 —— PDF 存在、Qdrant 有 chunks
  2. 检索覆盖 —— 每个 QA 对的 reference 能否在检索结果中找到
  3. 诚实性探针 —— 答案不在文档中的问题，检索结果不应包含答案
  4. 生成器抽查 —— 跑 3 对代表性 QA，人工 spot-check 生成质量

运行：python tools/ragas_eval_verify.py
"""
from __future__ import annotations

import os
import sys
import difflib

# 确保项目根目录在 sys.path 中（从 tools/ 向上找）
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from tools.qa_pairs import FINANCIAL_QA_PAIRS, get_pairs_by_category
from tools.rag_pipeline import get_store

EVAL_USER_ID = "ragas_eval_user"

# 需导入的 PDF（相对于项目根目录）
PDFS = [
    "ABC_Tech_2024_Annual_Report.pdf",
    "Huaxia_Stable_Growth_365_Prospectus.pdf",
]


def check_docs_available() -> bool:
    """检查 1：PDF 文件存在 + Qdrant 入库成功。"""
    print("=" * 60)
    print("检查 1：文档可用性")
    print("=" * 60)

    store = get_store()

    all_ok = True
    for pdf_name in PDFS:
        pdf_path = os.path.join(_PROJ_ROOT, pdf_name)
        if not os.path.exists(pdf_path):
            print(f"  [FAIL] PDF 不存在：{pdf_path}")
            all_ok = False
            continue

        # 幂等入库
        if not store.has_documents(EVAL_USER_ID):
            print(f"  首次入库：{pdf_name} ...")
            result = store.ingest_pdf(pdf_path, user_id=EVAL_USER_ID)
            print(f"    → {result['chunks']} chunks（来源：{result['doc_name']}）")
        else:
            # 检查具体文档
            chunks = store.retrieve("test", user_id=EVAL_USER_ID, top_k=1, top_n=1)
            if chunks:
                print(f"  [OK] {pdf_name} — Qdrant 中已有数据（示例 chunk: {chunks[0].text[:60]}...）")
            else:
                print(f"  [WARN] {pdf_name} — has_documents=True 但检索返回空，重新入库...")
                store.ingest_pdf(pdf_path, user_id=EVAL_USER_ID)

    if all_ok:
        print("  → 文档可用性检查通过\n")
    return all_ok


def check_retrieval_coverage() -> dict:
    """检查 2：每个 QA 对的 reference 能否在检索结果中找到。"""
    print("=" * 60)
    print("检查 2：检索覆盖（reference 是否在 top-10 chunks 中）")
    print("=" * 60)

    store = get_store()
    passed = 0
    failed = []

    for i, qa in enumerate(FINANCIAL_QA_PAIRS, 1):
        chunks = store.retrieve(
            qa["question"], user_id=EVAL_USER_ID, top_k=20, top_n=10
        )
        if not chunks:
            failed.append((i, qa, "检索返回 0 条结果"))
            continue

        # 模糊匹配：reference 是否出现在任一 chunk 中
        best_sim = 0.0
        for c in chunks:
            sim = difflib.SequenceMatcher(
                None, qa["reference"], c.text
            ).ratio()
            if sim > best_sim:
                best_sim = sim

        threshold = 0.4 if qa["category"] == "multi_chunk" else 0.5
        if best_sim >= threshold:
            passed += 1
            marker = "✓"
            detail = f"sim={best_sim:.2f}"
        else:
            marker = "✗"
            detail = f"sim={best_sim:.2f} (threshold={threshold})"
            failed.append((i, qa, detail))

        print(f"  [{marker}] [{i:02d}/{len(FINANCIAL_QA_PAIRS):02d}] "
              f"{qa['question'][:50]:50s} {detail}")

    pct = passed / len(FINANCIAL_QA_PAIRS) * 100
    print(f"\n  → 检索覆盖：{passed}/{len(FINANCIAL_QA_PAIRS)} 通过 ({pct:.1f}%)")

    if failed:
        print(f"\n  未通过详情：")
        for idx, qa, reason in failed:
            cat = qa["category"]
            is_expected = (cat == "honesty_probe" or cat == "multi_chunk")
            tag = "(预期: 诚实性探针)" if cat == "honesty_probe" else \
                  "(预期: 多块合成，需生成器推理)" if cat == "multi_chunk" else ""
            print(f"    [{qa['category']}] Q{idx}: {qa['question'][:60]} — {reason} {tag}")

    print()
    return {"passed": passed, "total": len(FINANCIAL_QA_PAIRS), "failed": failed}


def check_honesty_probes() -> bool:
    """检查 3：诚实性探针的检索结果不应包含答案。"""
    print("=" * 60)
    print("检查 3：诚实性探针")
    print("=" * 60)

    store = get_store()
    probes = get_pairs_by_category("honesty_probe")
    all_ok = True

    for qa in probes:
        chunks = store.retrieve(
            qa["question"], user_id=EVAL_USER_ID, top_k=20, top_n=5
        )
        if not chunks:
            print(f"  [OK] 「{qa['question'][:40]}」→ 检索无结果（理想情况）")
            continue

        # 检查 chunks 中是否包含任何类似答案的信息
        suspicious = False
        for c in chunks:
            sim = difflib.SequenceMatcher(
                None, qa["reference"], c.text
            ).ratio()
            if sim > 0.3:
                suspicious = True
                break

        if suspicious:
            print(f"  [WARN] 「{qa['question'][:40]}」→ chunks 中包含疑似答案信息")
            all_ok = False
        else:
            print(f"  [OK] 「{qa['question'][:40]}」→ chunks 不包含答案")

    if all_ok:
        print("  → 诚实性探针检查通过\n")
    return all_ok


def check_generator_sanity() -> None:
    """检查 4：跑 3 对代表性 QA，打印生成结果供人工 spot-check。"""
    print("=" * 60)
    print("检查 4：生成器抽查（需人工确认）")
    print("=" * 60)

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("  [SKIP] langchain_openai 未安装，跳过生成器抽查")
        print("    安装：pip install langchain-openai")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("  [SKIP] DEEPSEEK_API_KEY 未设置，跳过生成器抽查")
        return

    llm = ChatOpenAI(
        model="deepseek-v4-pro",
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com/",
        temperature=0,
    )

    # 选 3 对代表性 QA：direct_lookup + multi_chunk + honesty_probe
    samples = [
        FINANCIAL_QA_PAIRS[0],   # direct_lookup: 总营收
        FINANCIAL_QA_PAIRS[10],  # multi_chunk: 业务板块增长
        FINANCIAL_QA_PAIRS[26],  # honesty_probe: 历史年化收益
    ]

    store = get_store()

    for qa in samples:
        chunks = store.retrieve(
            qa["question"], user_id=EVAL_USER_ID, top_k=20, top_n=5
        )
        ctx_block = "\n\n---\n\n".join(
            f"[片段{i+1}] {c.text}" for i, c in enumerate(chunks)
        ) if chunks else "（无检索结果）"

        prompt = (
            "你是一个财务文档问答助手。请严格基于下面提供的文档片段回答用户的问题。\n"
            "要求：\n"
            "1. 如果片段中包含答案，直接回答并引用相关片段编号\n"
            "2. 如果片段中部分包含答案，回答已知部分并说明哪些信息缺失\n"
            "3. 如果片段中完全没有答案，诚实地说「根据提供的文档片段，无法回答此问题」，不要编造\n\n"
            f"文档片段：\n{ctx_block}\n\n"
            f"用户问题：{qa['question']}\n\n"
            "请回答："
        )

        print(f"\n  [{qa['category']}] Q: {qa['question']}")
        print(f"  Reference: {qa['reference'][:80]}...")

        try:
            resp = llm.invoke(prompt)
            answer = resp.content[:200]
            print(f"  Answer: {answer}")
        except Exception as e:
            print(f"  [ERROR] 生成失败：{e}")

    print("\n  → 请人工确认以上 3 条 Answer 是否合理")


def main():
    print("=== RAGAS 评估前置验证 ===\n")
    print(f"QA 对总数：{len(FINANCIAL_QA_PAIRS)}")
    print(f"  direct_lookup: {len(get_pairs_by_category('direct_lookup'))}")
    print(f"  multi_chunk:   {len(get_pairs_by_category('multi_chunk'))}")
    print(f"  honesty_probe: {len(get_pairs_by_category('honesty_probe'))}")
    print()

    check_docs_available()
    coverage = check_retrieval_coverage()
    check_honesty_probes()
    check_generator_sanity()

    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    print(f"  检索覆盖：{coverage['passed']}/{coverage['total']} 通过")

    # 排除诚实性探针和多块合成后的通过率
    normal_pairs = [p for p in FINANCIAL_QA_PAIRS
                    if p["category"] not in ("honesty_probe",)]
    normal_failed = sum(
        1 for _, qa, _ in coverage["failed"]
        if qa["category"] not in ("honesty_probe",)
    )
    normal_pct = (len(normal_pairs) - normal_failed) / len(normal_pairs) * 100
    print(f"  直接查找 + 多块合成通过率：{len(normal_pairs) - normal_failed}/{len(normal_pairs)} ({normal_pct:.1f}%)")
    print(f"  如果通过率 ≥ 85%，可以放心跑完整 RAGAS 评估。")
    print(f"  运行：python tools/ragas_eval.py")


if __name__ == "__main__":
    main()
