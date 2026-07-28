# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17
@Description：
配置文件处理 — YAML加载 + Pydantic校验 + 环境变量API Key
'''

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from utils.logger_handler import get_logger
from utils.path_tool import get_abs_path


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1)
    chat_model: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0, le=2)


class AgentLoopConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    poll_interval_seconds: int = Field(default=60, ge=10)
    max_concurrent_emails: int = Field(default=1, ge=1)


class RagConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection_name: str = Field(default="email_kb")
    embedding_model: str = Field(default="text-embedding-v2")
    n_results: int = Field(default=5, ge=1, le=20)


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: ProjectInfo
    model: ModelConfig
    agent_loop: AgentLoopConfig | None = None
    rag: RagConfig | None = None


def load_project_config(config_path: str | None = None) -> ProjectConfig:
    logger = get_logger(__name__)
    path = config_path or get_abs_path("config/project_config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    config = ProjectConfig.model_validate(data)
    logger.info("项目配置加载完成: %s", config)
    return config


def load_model_api_key(config: ProjectConfig | None = None) -> SecretStr:
    logger = get_logger(__name__)
    project_config = config or load_project_config()

    env_file = get_abs_path(".env")
    if env_file and Path(env_file).exists():
        load_dotenv(env_file, override=False)

    key_name = project_config.model.api_key_env
    key_value = os.getenv(key_name)
    if not key_value:
        raise ValueError(f"Missing API key: {key_name}")
    logger.info("模型 API Key 加载完成: %s", key_name)
    return SecretStr(key_value)
