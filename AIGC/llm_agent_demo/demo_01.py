# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from openai import OpenAI

client: OpenAI = OpenAI(
    api_key='',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1'
)

response = client.chat.completions.create(
    model = 'qwen-plus-2025-12-01',
    messages = [
        {
            'role':'system','content':'你是一个python编程专家，不说废话，直接给出代码，并且注释'
        },
        {
            'role':'assistant','content':'好的，我是python编程专家，以下是我的代码：'
        },
        {
            'role':'user','content':'请编写一个python程序，实现一个函数，该函数接收一个字符串参数，返回该字符串的倒序。'
        }
    ]
)

print(response.choices[0].message.content)