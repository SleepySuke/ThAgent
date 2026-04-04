# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from agents import Agent,Runner,function_tool
import os
from agents.extensions.models.litellm_model import LitellmModel


@function_tool
def get_total():
    return "简单统计一个各个能源车的规模大小"

qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01")
os.environ["OPENAI_API_KEY"] = ""
agent = Agent(name="Financial Analyst", instructions="你是一个专业的金融分析师，请根据提供的信息生成报告。",model=qwen_model,tools=[get_total])
result = Runner.run_sync(agent, "分析一下当前新能源车板块的风险点")
print(result.final_output)
