# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-22 21:59:07
@Description：用户提问界面
'''

from uuid import uuid4

import streamlit as st
from rag import RAGService


st.set_page_config(page_title="服装客服问答", page_icon="👕", layout="wide")
st.title("服装客服问答")
st.caption("结合资料检索与历史对话的服装顾问页面")


def _get_message_content(content) -> str:
    '''
    兼容 LangChain 消息内容的展示格式
    '''
    if isinstance(content, str):
        return content
    return str(content)


def _get_query_session_id() -> str | None:
    '''
    从 URL 中读取会话ID，支持刷新后恢复当前会话
    '''
    session_id = st.query_params.get("session_id")
    if session_id:
        return str(session_id).strip()
    return None


def _set_current_session_id(session_id: str) -> None:
    '''
    同步当前会话ID到页面状态和 URL
    '''
    st.session_state["session_id"] = session_id
    st.query_params["session_id"] = session_id


def _format_session_label(session_item: dict) -> str:
    '''
    展示历史会话标签
    '''
    return f"{session_item['preview']} | {session_item['updated_at']}"


if "rag_service" not in st.session_state:
    with st.spinner("正在准备服装顾问服务..."):
        st.session_state["rag_service"] = RAGService()

rag_service = st.session_state["rag_service"]

if "session_id" not in st.session_state:
    query_session_id = _get_query_session_id()
    if query_session_id:
        _set_current_session_id(query_session_id)
    else:
        _set_current_session_id(uuid4().hex)

session_id = st.session_state["session_id"]
session_items = rag_service.list_sessions()
session_lookup = {item["session_id"]: item for item in session_items}

if session_id not in session_lookup:
    session_lookup[session_id] = {
        "session_id": session_id,
        "preview": "当前新会话",
        "updated_at": "未开始",
    }

session_options = list(session_lookup.keys())
current_index = session_options.index(session_id)

with st.sidebar:
    st.subheader("会话设置")
    st.text_input("当前会话ID", value=session_id, disabled=True)

    if st.button("开始新对话", use_container_width=True):
        new_session_id = uuid4().hex
        _set_current_session_id(new_session_id)
        st.rerun()

    selected_session_id = st.selectbox(
        "切换历史对话",
        options=session_options,
        index=current_index,
        format_func=lambda option: _format_session_label(session_lookup[option]),
    )
    if selected_session_id != session_id:
        _set_current_session_id(selected_session_id)
        st.rerun()

    if st.button("清空当前会话历史", use_container_width=True):
        rag_service.clear_session_history(session_id)
        st.rerun()

messages = rag_service.get_session_messages(session_id)

if not messages:
    st.info("当前还没有历史对话，你可以直接咨询尺码、面料、退换货或搭配问题。")

for message in messages:
    role = "user" if message.type == "human" else "assistant"
    with st.chat_message(role):
        st.markdown(_get_message_content(message.content))

question = st.chat_input("请输入你的问题，例如：这件衣服支持退货吗？")

if question:
    with st.spinner("正在查找相关衣品信息并整理回答..."):
        try:
            rag_service.ask(question, session_id=session_id)
        except Exception as error:
            st.error(f"问答失败：{error}")
        else:
            st.rerun()
