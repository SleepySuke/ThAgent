# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from langchain_core.prompts import PromptTemplate
from langchain_community.llms import Tongyi

prompt_template = PromptTemplate.from_template(
    "我姓:{first_name},刚学习语言，请帮我生成一个{language}的姓名"
)
# template = prompt_template.format(first_name="张", language="中文")

model = Tongyi(api_key="",model="qwen-plus")
chain = prompt_template | model
res = chain.invoke(input = {"first_name":"张","language":"中文"})
print(res)