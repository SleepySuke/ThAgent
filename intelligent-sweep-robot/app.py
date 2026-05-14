# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-12
@Description：
智扫通 Streamlit 前端页面。
功能：对话式交互、文件上传、历史对话持久化。
运行：make run-web 或 streamlit run app.py
'''
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from react_agent import create_sweep_robot_agent, execute_stream
from utils.file_handler import load_file

HISTORY_FILE = Path(__file__).resolve().parent / "logs" / "conversations.json"

# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def _load_conversations() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_conversations():
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(st.session_state.conversations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_uploaded_file(uploaded_file) -> str:
    suffix = "." + uploaded_file.name.rsplit(".", 1)[-1] if "." in uploaded_file.name else ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
    try:
        loaded = load_file(tmp_path)
        return loaded.content
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------

st.set_page_config(page_title="智扫通 Agent", page_icon="🤖", layout="wide")

# ---------------------------------------------------------------------------
# Agent 单例
# ---------------------------------------------------------------------------


@st.cache_resource
def get_agent():
    return create_sweep_robot_agent()


# ---------------------------------------------------------------------------
# 会话状态初始化（首次从文件加载）
# ---------------------------------------------------------------------------

if "conversations" not in st.session_state:
    st.session_state.conversations = _load_conversations()
if "current_conv_id" not in st.session_state:
    st.session_state.current_conv_id = None

_current = None
if st.session_state.current_conv_id is not None:
    for c in st.session_state.conversations:
        if c["id"] == st.session_state.current_conv_id:
            _current = c
            break


def _current_messages():
    if _current is not None:
        return _current["messages"]
    conv = _new_conversation()
    return conv["messages"]


def _new_conversation():
    conv = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "title": "新对话",
        "messages": [],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    st.session_state.conversations.insert(0, conv)
    st.session_state.current_conv_id = conv["id"]
    _save_conversations()
    return conv


def _update_title(messages):
    if _current is None or _current["title"] != "新对话":
        return
    for m in messages:
        if m["role"] == "user" and not m.get("from_file"):
            _current["title"] = m["content"][:30]
            break
    _save_conversations()


# ---------------------------------------------------------------------------
# 侧边栏 — 历史对话
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🤖 智扫通 Agent")

    if st.button("＋ 新建对话", use_container_width=True):
        _new_conversation()
        st.rerun()

    st.divider()
    st.caption("📋 历史对话")

    if not st.session_state.conversations:
        st.caption("  暂无历史对话")
    else:
        for conv in st.session_state.conversations:
            is_active = conv["id"] == st.session_state.current_conv_id
            cols = st.columns([0.82, 0.18])
            with cols[0]:
                label = f"{'🔵 ' if is_active else ''}{conv['title']}"
                if st.button(
                    label,
                    key=f"hist_{conv['id']}",
                    use_container_width=True,
                    type="secondary" if not is_active else "primary",
                ):
                    st.session_state.current_conv_id = conv["id"]
                    st.rerun()
            with cols[1]:
                if st.button("🗑", key=f"del_{conv['id']}", help="删除此对话"):
                    st.session_state.conversations.remove(conv)
                    if conv["id"] == st.session_state.current_conv_id:
                        st.session_state.current_conv_id = None
                    _save_conversations()
                    st.rerun()

    st.divider()
    st.caption(f"共 {len(st.session_state.conversations)} 个对话")

# ---------------------------------------------------------------------------
# 主区域
# ---------------------------------------------------------------------------

st.title("🤖 智扫通 Agent")
st.caption("扫地机器人智能客服 — 支持产品咨询、故障排查、使用报告生成")

# ---------------------------------------------------------------------------
# 消息历史
# ---------------------------------------------------------------------------

messages = _current_messages()
for msg in messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# 对话输入区（文件上传 + 消息输入）
# ---------------------------------------------------------------------------

# 文件上传（紧凑行，紧贴输入框）
uploaded_file = st.file_uploader(
    "📎 上传文件（支持 txt / pdf）",
    type=["txt", "pdf"],
    key="file_uploader",
)
if uploaded_file is not None:
    st.session_state.selected_file_name = uploaded_file.name

prompt = st.chat_input("输入你的问题...")

if prompt:
    display = prompt
    agent_input = prompt

    # 附加文件内容
    if st.session_state.get("selected_file_name") and uploaded_file is not None:
        file_content = _read_uploaded_file(uploaded_file)
        if file_content:
            display = f"{prompt}\n\n📎 已上传 `{uploaded_file.name}`"
            agent_input = f"{prompt}\n\n[用户上传文件: {uploaded_file.name}]\n{file_content}"

    # 清空文件选择
    st.session_state.selected_file_name = None

    # 渲染用户消息
    messages.append({"role": "user", "content": display})
    with st.chat_message("user"):
        st.markdown(display)

    _update_title(messages)

    # 调用 Agent
    agent = get_agent()

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("🤖 正在思考...")
        streamed = ""
        tool_call_status = ""

        try:
            for chunk in execute_stream(agent, agent_input):
                for node_name, node_data in chunk.items():
                    if node_name == "tools":
                        for msg in node_data.get("messages", []):
                            tool_name = getattr(msg, "name", "unknown")
                            tool_call_status = f"\n\n🔧 正在调用工具: `{tool_name}` ..."
                            placeholder.markdown(streamed + tool_call_status)
                    elif node_name == "model":
                        for msg in node_data.get("messages", []):
                            content = getattr(msg, "content", "")
                            if content:
                                streamed += content
                                placeholder.markdown(streamed)

            if not streamed:
                streamed = "⚠️ 未获取到回答，请重试"
                placeholder.markdown(streamed)
        except Exception as e:
            streamed = f"❌ 调用出错: {e}"
            placeholder.markdown(streamed)

    messages.append({"role": "assistant", "content": streamed})
    _save_conversations()
    st.rerun()
