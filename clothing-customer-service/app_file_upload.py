# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-10 22:07:29
@Description：基于Streamlit的文件上传服务，用户可以通过该服务上传文件到知识库中
'''

import streamlit as st

from config import load_config
from knowledge_base import KnowledgeBaseService


st.set_page_config(page_title="资料上传与初始化", page_icon="📚", layout="wide")
st.title("资料上传与初始化")
st.caption("可先初始化默认衣品资料，也可以继续上传新的 txt/csv 文件补充资料库。")


def _render_init_result(result: dict) -> None:
    '''
    展示单个初始化结果
    '''
    message = result.get("message", "未知结果")
    status = result.get("status")
    if status == "success":
        st.success(message)
    elif status == "skipped":
        st.info(message)
    else:
        st.error(message)


if "kb_service" not in st.session_state:
    with st.spinner("正在准备资料中心..."):
        st.session_state["kb_service"] = KnowledgeBaseService()

kb_service = st.session_state["kb_service"]
config = load_config()

with st.sidebar:
    st.subheader("默认资料")
    for file_name in config.get("files", {}).keys():
        st.write(f"- {file_name}")

    if st.button("初始化默认资料", use_container_width=True):
        with st.spinner("正在整理并导入基础衣品资料..."):
            init_results = kb_service.initialize_knowledge_base()

        success_count = sum(1 for item in init_results if item["status"] == "success")
        skipped_count = sum(1 for item in init_results if item["status"] == "skipped")
        error_count = sum(1 for item in init_results if item["status"] == "error")

        st.write("初始化结果：")
        st.write(f"成功 {success_count} 份，跳过 {skipped_count} 份，失败 {error_count} 份")
        for result in init_results:
            _render_init_result(result)

upload_file = st.file_uploader(
    "选择要补充到资料库的文件",
    type=["txt", "csv"],
    accept_multiple_files=False,
)

if upload_file is not None:
    file_name = upload_file.name
    file_size = upload_file.size / 1024
    file_type = upload_file.type

    st.subheader("文件信息")
    st.write(f"文件名：{file_name}")
    st.write(f"文件大小：{file_size:.2f} KB")
    st.write(f"文件类型：{file_type or '未知类型'}")

    if st.button("导入当前文件", use_container_width=True):
        file_content = upload_file.getvalue().decode("utf-8", errors="ignore")
        with st.spinner("正在整理并录入新的衣品资料..."):
            result = kb_service.update_knowledge_base(file_content, file_name)

        _render_init_result(result)
