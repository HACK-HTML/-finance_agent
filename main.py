"""
命令行交互界面 — 不需要启动 FastAPI，直接测试 Agent
运行：python main.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import asyncio
from core.agent import FinanceAgent


WELCOME = """
╔══════════════════════════════════════════════════════╗
║          💰 个人财务 Agent  —  ReAct 演示            ║
║  手写消息循环 | Claude Tool Use | Pydantic 验证       ║
╚══════════════════════════════════════════════════════╝

命令：
  /upload <PDF路径> — 上传财务文档进知识库（之后可直接提问文档内容）
  /reset   — 重置对话历史
  /stats   — 查看本次会话统计
  /demo    — 运行一组演示问题
  /quit    — 退出

推荐测试问题（观察 ReAct 多轮工具调用）：
  1. "我月收入12000，支出8500，存款3万，帮我评估财务健康度"
  2. "我想3年后买房首付60万，现在月薪15000，怎么规划预算？"
  3. "帮我分析这个月的支出：餐饮1200，交通450，娱乐800，房租3500，
      购物1100，收入-12000"
  4. "1000美元换成人民币是多少？同时查一下SPY的表现"（多工具并行）
"""

DEMO_QUESTIONS = [
    "我月收入10000，每月支出7500，目前存款15000元，帮我评估一下财务健康状况",
    "基于刚才的情况，帮我制定一个预算方案，目标是2年内存够10万应急资金",
    "顺便查一下现在美元对人民币的汇率，以及QQQ基金的情况",
]


def run_demo(agent: FinanceAgent):
    """运行预设演示，展示多工具、多轮对话能力"""
    print("\n🎬 开始演示模式（3 个预设问题）\n")
    for i, q in enumerate(DEMO_QUESTIONS, 1):
        print(f"\n{'═'*60}")
        print(f"演示问题 {i}/{len(DEMO_QUESTIONS)}：{q}")
        print('═'*60)
        reply = agent.chat(q)
        print(f"\n🤖 Agent 回答：\n{reply}")
        input("\n按 Enter 继续下一个问题...")


async def main():
    print(WELCOME)
    agent = FinanceAgent()

    while True:
        try:
            user_input = input("\n你：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("再见！")
            break
        elif user_input == "/reset":
            agent.reset()
            print("✅ 对话已重置")
            continue
        elif user_input == "/stats":
            print(f"\n📊 会话统计：{agent.state.summary()}")
            if agent.state.tool_history:
                print("最近工具调用：")
                for tr in agent.state.tool_history[-5:]:
                    print(f"  • {tr.tool_call.tool_name}: {str(tr.result)[:80]}")
            continue
        elif user_input == "/demo":
            run_demo(agent)
            continue
        elif user_input.startswith("/upload"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("用法：/upload <PDF文件路径>")
                continue
            from tools.rag_pipeline import get_store
            path = parts[1].strip().strip('"').strip("'")
            try:
                stats = get_store().ingest_pdf(path, session_id=agent.session_id)
                print(f"✅ 文档已入库：{stats}")
            except Exception as e:
                print(f"❌ 入库失败：{e}")
            continue

        # 正常对话
        print("\n" + "─"*60)
        reply = await agent.chat(user_input)
        print(f"\n🤖 Agent：\n{reply}")
        print(f"\n[会话状态] {agent.state.summary()}")


if __name__ == "__main__":
    asyncio.run(main())
