# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

from langchain_community.llms.tongyi import Tongyi

model = Tongyi(api_key="", model="qwen-plus-2025-12-01")

res_stream = model.stream(input = "你是谁？能帮我做什么")

for chunk in res_stream:
    print(chunk, end="",flush=True)

# res = model.invoke(input = "你是谁？能帮我做什么")
#
#
#
# print(res)
