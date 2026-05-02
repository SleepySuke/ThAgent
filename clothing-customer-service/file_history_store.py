# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-23 23:29:39
@Description：
历史会话记录
'''

import json
import os
from typing import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict


class FileChatMessageHistory(BaseChatMessageHistory):
    '''
    基于本地文件的历史会话记录
    '''
    def __init__(self, file_path: str):
        self.file_path = file_path

    @property
    def messages(self) -> list[BaseMessage]:
        '''
        加载历史会话记录
        '''
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            return messages_from_dict(history_data)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        '''
        添加新的会话记录
        '''
        if not messages:
            return

        all_messages = list(self.messages)
        all_messages.extend(messages)
        history_data = [message_to_dict(message) for message in all_messages]

        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        '''
        清空历史会话记录
        '''
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)
