# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

chat = ChatTongyi(api_key="",model="qwen-plus")

messages = [
    SystemMessage(content="你是一名边塞诗人"),
    HumanMessage(content="帮我写一首唐诗"),
    AIMessage(content=""),
    HumanMessage(content="请将唐诗的开头部分写为："),
]

for chunk in chat.stream(input= messages):
    print(chunk.content, end="",flush=True)