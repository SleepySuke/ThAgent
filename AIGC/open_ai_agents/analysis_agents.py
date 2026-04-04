# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

import asyncio
import os
from agents import Agent, Runner, handoff, GuardrailFunctionOutput, InputGuardrailTripwireTriggered, output_guardrail, \
    tool_output_guardrail, input_guardrail,RunContextWrapper,TResponseInputItem
from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)

class FinancialOutput(BaseModel):
    reasoning: str
    is_legal:bool

guardrail_agent = Agent(
    name="Guardrail check",
    instructions="""你是一个财务 Guardrail 检查者。
    任务：检查用户的输入是否包含“全仓”、“买入”、“卖出”、“操作股票”等具体的投资建议或交易指令。
    输出规则：
    1. 如果包含上述危险内容，请仅输出 "BLOCKED"。
    2. 如果不包含，请仅输出 "ALLOWED"。
    不要输出任何其他解释或文字。""",
    model=qwen_model,
    output_type=FinancialOutput
)

@input_guardrail
async def investment_input_guardrail(
    ctx: RunContextWrapper[None], agent: Agent, input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    # 运行 guardrail agent 进行检查
    result = await Runner.run(guardrail_agent, input, context=ctx.context)

    # 获取检查结果文本
    analysis = result.final_output

    # 判断是否触发拦截
    is_triggered = not analysis.is_legal

    return GuardrailFunctionOutput(
        output_info="合规检查通过" if not is_triggered else "触发金融合规拦截",
        tripwire_triggered=is_triggered
    )


def transfer_to_analyst():
    return analyst_agent


# --- 定义 Agent B：金融分析师 (专家) ---
analyst_agent = Agent(
    name="Financial Analyst",
    instructions="""你是一个专业的股票分析师。
    你会接收到接待员传来的公司名称，请给出该公司的模拟财务评价。
    最后请礼貌地结束对话。""",
    model=qwen_model,

)

# --- 定义 Agent A：接待员 (负责引导) ---
triage_agent = Agent(
    name="Triage Agent",
    instructions="""你是金融咨询公司的前台。
    你的唯一任务：一旦用户提供了公司名称，**必须立即调用 `transfer_to_analyst` 工具**，将用户移交给分析师。
    你绝对不能自己回答任何财务问题，也不能输出任何多余内容。
    如果用户未提供公司名称，你才询问。""",
    # 核心：定义 Handoff
    handoffs=[
        handoff(agent=analyst_agent)
    ],
    model=qwen_model,
    input_guardrails=[investment_input_guardrail]
)


async def main():
    handoff_tools = [h.tool_name for h in triage_agent.handoffs]
    print("Handoff tools:", handoff_tools)
    # 初始化 Runner
    # Runner 会自动处理 Triage -> Analyst 的切换逻辑
    print("--- 启动 Agent 系统 ---")

    #user_input = "我想全仓买入特斯拉(Tesla)，你觉得怎么样？"
    user_input = "特斯拉(Tesla)去年的利润是多少？"

    try:
        result = await Runner.run(
            triage_agent,
            input=user_input
        )
        # 打印最终结果
        print(f"\n[最终回复]:\n{result.final_output}")
    except InputGuardrailTripwireTriggered as e:
         print(f"\n[安全拦截]: 很抱歉，我不能为您提供任何关于“买入”或“卖出”的操作建议。")


if __name__ == "__main__":
    asyncio.run(main())
