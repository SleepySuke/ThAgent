# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17
@Description：
LLM 模型创建 — 基于项目配置 + ChatTongyi
'''

from langchain_community.chat_models.tongyi import ChatTongyi

from utils.config_handler import ProjectConfig, load_model_api_key, load_project_config


def create_model(config: ProjectConfig | None = None) -> ChatTongyi:
    """从项目配置创建 ChatTongyi 模型实例。"""
    project_config = config or load_project_config()
    api_key = load_model_api_key(project_config).get_secret_value()

    return ChatTongyi(
        model=project_config.model.chat_model,
        dashscope_api_key=api_key,
        model_kwargs={"temperature": project_config.model.temperature},
    )
