# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
@Date ：2026-03-28 14:41:54
@Description：长期对话记录
'''

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import message_to_dict, messages_from_dict,BaseMessage
import json
import os
from typing import Sequence

from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser

class FileChatMessageHistory(BaseChatMessageHistory):
    def __init__(self,storage_path,session_id):
        self.storage_path = storage_path #存储对话记录的文件路径
        self.session_id = session_id #会话ID，用于区分不同用户的对话记录
        
        self.file_path = os.path.join(self.storage_path,self.session_id) #完整路径
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True) #确保存储目录存在

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        all_messages = list(self.messages) #已有的消息列表
        all_messages.extend(messages) #将新消息添加到当前记录中
        new_messages = [message_to_dict(msg) for msg in messages] #将新消息转换为字典格式
        #将新消息追加到文件中
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(new_messages, f, ensure_ascii=False)
    @property
    def messages(self) -> list[BaseMessage]:
        #将字典中的文件转换为消息列表     
        try:
            with open(os.path.join(self.file_path),'r',encoding='utf-8') as f:
                message_data = json.load(f)
                return messages_from_dict(message_data)
        except FileNotFoundError:
            return []       
    def clear(self):
        with open(self.file_path,'w',encoding='utf-8') as f:       
            f.write([],f)

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
    return FileChatMessageHistory(storage_path="./chat_history",session_id=user_id) 


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
