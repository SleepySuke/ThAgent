# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-10 22:08:25
@Description：rag核心服务，主要进行检索等操作
'''

import os
import re
from datetime import datetime
from operator import itemgetter
from typing import List

from file_history_store import FileChatMessageHistory
from langchain_community.chat_models import ChatTongyi
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnableParallel, RunnableWithMessageHistory
from vector_stores import VectorStoreService


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAT_HISTORY_DIR = os.path.join(BASE_DIR, "chat_history")


def _normalize_session_id(session_id: str) -> str:
    '''
    将会话ID转换为安全的文件名
    '''
    normalized_session_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", session_id.strip())
    return normalized_session_id or "default"


def _get_session_history(session_id: str) -> FileChatMessageHistory:
    '''
    根据会话ID获取对应的历史消息存储
    '''
    safe_session_id = _normalize_session_id(session_id)
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{safe_session_id}.json")
    return FileChatMessageHistory(file_path=file_path)


class RAGService(object):
    '''
    RAG核心服务类，主要进行检索等操作
    '''
    def __init__(self):
        self.vector_store_service = VectorStoreService()
        self.model = ChatTongyi(
            model="qwen-plus",
            dashscope_api_key=""
        )
        self.rewrite_prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你负责将用户当前问题改写为适合知识库检索的独立问题。"
                    "如果当前问题已经足够完整，则原样返回。"
                    "只输出改写后的检索问题，不要添加解释。",
                ),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个服装客服助手，协助客户解答关于服装的相关问题。"
                    "请优先依据资料库内容回答；若资料库没有足够信息，明确说明。",
                ),
                (
                    "system",
                    "资料库内容如下：\n{context}",
                ),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )
        self.chain = self._get_chain()

    def _get_chain(self):
        retriever_chain = self.vector_store_service.get_retriever()
        history_aware_question_chain = RunnableBranch(
            (
                lambda inputs: bool(inputs.get("chat_history")),
                self.rewrite_prompt_template | self.model | StrOutputParser(),
            ),
            itemgetter("question"),
        )
        chain = (
            RunnableParallel(
                {
                    "question": itemgetter("question"),
                    "chat_history": itemgetter("chat_history"),
                    "context": history_aware_question_chain | retriever_chain | RunnableLambda(self._format_docs),
                }
            )
            | self.prompt_template
            | self.model
            | StrOutputParser()
        )

        conversation_chain = RunnableWithMessageHistory(
            chain,
            get_session_history=_get_session_history,
            input_messages_key='question',
            history_messages_key='chat_history',
        )

        return conversation_chain

    def ask(self, question: str, session_id: str = "default") -> str:
        '''
        基于会话ID进行提问，并自动读写历史记录
        '''
        question = question.strip()
        if not question:
            raise ValueError("问题内容不能为空")

        return self.chain.invoke(
            {"question": question},
            config={"configurable": {"session_id": session_id}},
        )

    def get_session_messages(self, session_id: str = "default") -> List[BaseMessage]:
        '''
        获取指定会话的历史消息
        '''
        return list(_get_session_history(session_id).messages)

    def clear_session_history(self, session_id: str = "default") -> None:
        '''
        清空指定会话的历史记录
        '''
        _get_session_history(session_id).clear()

    def list_sessions(self) -> List[dict]:
        '''
        获取可切换的历史会话列表
        '''
        if not os.path.exists(CHAT_HISTORY_DIR):
            return []

        session_items = []
        for file_name in os.listdir(CHAT_HISTORY_DIR):
            if not file_name.endswith(".json"):
                continue

            session_id = os.path.splitext(file_name)[0]
            file_path = os.path.join(CHAT_HISTORY_DIR, file_name)
            messages = self.get_session_messages(session_id)
            preview = "空白会话"
            for message in messages:
                if message.type == "human" and message.content:
                    preview = str(message.content).strip()
                    break

            if len(preview) > 20:
                preview = preview[:20] + "..."

            session_items.append(
                {
                    "session_id": session_id,
                    "preview": preview,
                    "updated_at": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%m-%d %H:%M"),
                    "sort_key": os.path.getmtime(file_path),
                }
            )

        session_items.sort(key=lambda item: item["sort_key"], reverse=True)
        for item in session_items:
            item.pop("sort_key", None)
        return session_items

    def _format_docs(self, docs: List[Document]) -> str:
        '''
        格式化检索到的文档内容
        '''
        if not docs:
            return "无相关资料库内容"

        formatted_docs = []
        for index, doc in enumerate(docs, start=1):
            source = doc.metadata.get("source", "未知来源")
            formatted_docs.append(f"[资料{index}] 来源: {source}\n{doc.page_content}")
        return "\n\n".join(formatted_docs)
