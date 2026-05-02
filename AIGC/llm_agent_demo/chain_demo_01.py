# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.runnables.base import RunnableSerializable
from langchain_core.output_parsers import StrOutputParser

model = ChatTongyi(api_key="",model="qwen-plus")

chat_prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个懂得中华文化的小助手"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "请给我大概讲述一个关于“中国”的小故事")
    ]
)

history_data = [
    ("human","给我讲一个有关大禹治水的部分内容"),
    ("ai","大禹治水，是汉武帝于西元476年（476-479年），在河口河口（今河北河口河口）的河口河口（今河北河口河口）"),
]
parser = StrOutputParser()

chain : RunnableSerializable = chat_prompt_template | model | parser | model
for chunk in chain.stream({"history": history_data}):
    print(chunk.content, end="", flush=True)

