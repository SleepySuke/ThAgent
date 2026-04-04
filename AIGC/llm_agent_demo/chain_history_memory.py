# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
@Date ：2026-03-28 00:06:51
@Description：临时会话记忆的多轮对话
'''
from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser
model = ChatTongyi(api_key="",model="qwen-plus")

def print_prompt(full_prompt):
    print("="*20,full_prompt.to_string(),"="*20)
    return full_prompt

prompt = PromptTemplate.from_template(
    "你根据历史对话回答用户问题，历史对话如下：{chat_history}，请根据历史对话回答用户问题：{input}"
)
base_chain = prompt| print_prompt | model | StrOutputParser()

chat_history = {}

def get_history(user_id):
    if user_id not in chat_history:
        chat_history[user_id] = InMemoryChatMessageHistory()
    return chat_history[user_id]    


conversation_chain = RunnableWithMessageHistory(
    base_chain,
    get_history,
    input_messages_key='input',
    history_messages_key='chat_history',
)

if __name__ == "__main__":
    session_config = {
        "configurable":{
            "session_id": "user_123"
        }
    }
    print("第一次对话：")
    res = conversation_chain.invoke({"input": "你是谁？能帮我做什么，我是suke"}, session_config)
    print(res)
    print("第二次对话：")
    res = conversation_chain.invoke({"input": "你还记得我是谁吗？"},session_config)
    print(res)