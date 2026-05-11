# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:46:52
@Description：
智扫通 Agent Tool Calling 验证脚本。
通过 react_agent.py 封装的 Agent 链路，验证 LLM 是否能正确识别工具、选择工具并执行调用。
运行前请确保：
1. .env 中 DASHSCOPE_API_KEY 有效且账户余额充足
2. 如需测试 RAG 工具，请先构建向量库（make build-vector-store）
'''
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from react_agent import create_sweep_robot_agent, execute_stream


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


def run_test_case(agent, case_id, user_query):
    """运行单个测试用例，打印完整的 Tool Calling 过程。"""
    print(f"{'=' * 60}")
    print(f"📝 测试用例 {case_id}: {user_query}")
    print(f"{'=' * 60}")

    tool_calls = []
    final_answer = ""

    # 使用 execute_stream 观察每一步的工具调用并提取最终回答
    for chunk in execute_stream(agent, user_query):
        for node_name, node_data in chunk.items():
            if node_name == "tools":
                for msg in node_data.get("messages", []):
                    tool_name = getattr(msg, "name", "unknown")
                    tool_content = getattr(msg, "content", "")
                    tool_calls.append((tool_name, tool_content))
                    print(f"  🔧 工具调用: {tool_name}")
                    display = tool_content[:300] + "..." if len(tool_content) > 300 else tool_content
                    for line in display.split("\n"):
                        print(f"      {line}")
            elif node_name == "agent":
                for msg in node_data.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and getattr(msg, "type", None) == "ai":
                        final_answer = content

    print(f"\n  🤖 最终回答:")
    for line in final_answer.split("\n"):
        print(f"      {line}")

    if tool_calls:
        print(f"\n  📊 本次调用工具: {[name for name, _ in tool_calls]}")
    else:
        print(f"\n  📊 本次未调用工具（直接回答）")
    print()


def main():
    print("🚀 智扫通 Agent Tool Calling 验证脚本（react_agent 集成版）\n")

    check_vector_store()

    print("🔄 正在初始化 Agent ...")
    agent = create_sweep_robot_agent()
    print(f"✅ Agent 初始化完成\n")

    # 定义测试用例：覆盖不同意图和工具组合
    test_cases = [
        (1, "智扫通 S1 和 S1 Max 有什么区别？"),
        (2, "今天适合拖地吗？"),
        (3, "帮我生成本月的扫地机器人使用报告"),
    ]

    for case_id, query in test_cases:
        try:
            run_test_case(agent, case_id, query)
        except Exception as e:
            print(f"❌ 测试用例 {case_id} 执行失败: {e}\n")

    print("🏁 所有测试用例执行完毕")


if __name__ == "__main__":
    main()
