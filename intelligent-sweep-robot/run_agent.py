# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-10
@Description：
智扫通 Agent 交互式命令行。
启动后进入对话循环，输入 quit / exit / q 退出。
'''
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from react_agent import create_sweep_robot_agent, execute_stream


def main():
    print("🤖 智扫通 Agent 交互式命令行")
    print("   输入 quit / exit / q 退出\n")

    print("🔄 正在初始化 Agent ...")
    agent = create_sweep_robot_agent()
    print("✅ Agent 就绪\n")

    while True:
        try:
            user_input = input("🧑 用户: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("👋 再见")
            break

        print("🤖 Agent: ", end="", flush=True)
        final_answer = ""
        for chunk in execute_stream(agent, user_input):
            for node_name, node_data in chunk.items():
                if node_name == "tools":
                    for msg in node_data.get("messages", []):
                        tool_name = getattr(msg, "name", "unknown")
                        print(f"\n  🔧 [{tool_name}]", end=" ")
                elif node_name == "agent":
                    for msg in node_data.get("messages", []):
                        content = getattr(msg, "content", "")
                        if content:
                            final_answer = content
                            print(content, end="", flush=True)
        if not final_answer:
            print()
        print("\n")


if __name__ == "__main__":
    main()
