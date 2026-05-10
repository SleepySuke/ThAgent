# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:46:52
@Description：
智扫通 Agent Tool Calling 验证脚本。
用于验证 LLM 是否能正确识别工具、选择工具并执行调用。
运行前请确保：
1. .env 中 DASHSCOPE_API_KEY 有效且账户余额充足
2. 如需测试 RAG 工具，请先构建向量库（python -c "from service.vector_store import ChromaVectorStoreService; ..."）
'''
import os
import sys
from pathlib import Path
from langgraph.prebuilt import create_react_agent

from model.factory import get_model_factory
from tools import get_agent_tools
from utils.prompt_handler import load_prompt_bundle

# 将项目根目录加入 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))




def check_vector_store():
    """检查向量库是否已构建。"""
    chroma_dir = PROJECT_ROOT / "chroma_db"
    if not chroma_dir.exists() or not any(chroma_dir.iterdir()):
        print("⚠️  警告：chroma_db 向量库未构建或为空。")
        print("   RAG 工具 (rag_summarize) 将无法正常工作。")
        print("   其他工具（天气、位置、报告生成）仍可正常演示。\n")
        return False
    print("✅ 向量库已构建\n")
    return True


def create_agent():
    """创建智扫通 ReAct Agent。"""
    print("🔄 正在初始化 Agent ...")
    model_factory = get_model_factory()
    chat_model = model_factory.create_chat_model()
    tools = get_agent_tools()
    prompt_bundle = load_prompt_bundle()
    system_prompt = prompt_bundle.main_prompt.content

    agent = create_react_agent(
        model=chat_model,
        tools=tools,
        prompt=system_prompt,
    )
    print(f"✅ Agent 初始化完成，已加载 {len(tools)} 个工具\n")
    return agent


def run_test_case(agent, case_id, user_query):
    """运行单个测试用例，打印完整的 Tool Calling 过程。"""
    print(f"{'=' * 60}")
    print(f"📝 测试用例 {case_id}: {user_query}")
    print(f"{'=' * 60}")

    messages = [("user", user_query)]
    tool_calls = []
    final_answer = ""

    # 使用 stream 模式观察每一步的工具调用
    for step in agent.stream({"messages": messages}, stream_mode="updates"):
        for node_name, node_data in step.items():
            if node_name == "tools":
                # 提取工具调用结果
                for msg in node_data.get("messages", []):
                    tool_name = getattr(msg, "name", "unknown")
                    tool_content = getattr(msg, "content", "")
                    tool_calls.append((tool_name, tool_content))
                    print(f"  🔧 工具调用: {tool_name}")
                    # 截断过长的工具返回，避免刷屏
                    display = tool_content[:300] + "..." if len(tool_content) > 300 else tool_content
                    for line in display.split("\n"):
                        print(f"      {line}")

    # 获取最终答案
    final_state = agent.invoke({"messages": messages})
    for msg in reversed(final_state["messages"]):
        if getattr(msg, "type", None) == "ai" and getattr(msg, "content", None):
            final_answer = msg.content
            break

    print(f"\n  🤖 最终回答:")
    for line in final_answer.split("\n"):
        print(f"      {line}")

    if tool_calls:
        print(f"\n  📊 本次调用工具: {[name for name, _ in tool_calls]}")
    else:
        print(f"\n  📊 本次未调用工具（直接回答）")
    print()


def main():
    print("🚀 智扫通 Agent Tool Calling 验证脚本\n")

    check_vector_store()
    agent = create_agent()

    # 定义测试用例：覆盖不同意图和工具组合
    test_cases = [
        (
            1,
            "智扫通 S1 和 S1 Max 有什么区别？",
        ),
        (
            2,
            "今天适合拖地吗？",
        ),
        (
            3,
            "帮我生成本月的扫地机器人使用报告",
        ),
    ]

    for case_id, query in test_cases:
        try:
            run_test_case(agent, case_id, query)
        except Exception as e:
            print(f"❌ 测试用例 {case_id} 执行失败: {e}\n")

    print("🏁 所有测试用例执行完毕")


if __name__ == "__main__":
    main()
