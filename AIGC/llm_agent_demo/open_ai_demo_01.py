# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

import openai
from openai import OpenAI, RateLimitError
import time

client = OpenAI(api_key="")


def chat_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                messages=messages,
                temperature=0.7
            )
            return response

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                print(f"Rate limit hit, waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise e
        except Exception as e:
            raise e


# 使用示例
try:
    response = chat_with_retry([
        {"role": "user", "content": "Hello!"}
    ])
    print(response.choices[0].message.content)
except RateLimitError as e:
    print("请充值或检查账户余额")
except Exception as e:
    print(f"其他错误: {e}")