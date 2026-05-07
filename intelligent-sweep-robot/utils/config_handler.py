# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:40:08
@Description：
配置文件处理工具类
'''
import json
import os
from pathlib import Path
from typing import Optional, TypeVar

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from utils.logger_handler import get_logger
from utils.path_tool import get_abs_path


class ProjectInfo(BaseModel):
    """项目基础信息配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)


class PathConfig(BaseModel):
    """项目路径配置。"""

    model_config = ConfigDict(extra="forbid")

    data_dir: str = Field(min_length=1)
    logs_dir: str = Field(min_length=1)
    prompts_dir: str = Field(min_length=1)
    vector_store_dir: str = Field(min_length=1)


class ModelConfig(BaseModel):
    """模型配置。"""

    model_config = ConfigDict(extra="forbid")

    chat_model: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0, le=2)


class RagConfig(BaseModel):
    """RAG配置。"""

    model_config = ConfigDict(extra="forbid")

    collection_name: str = Field(min_length=1)
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_chunk_overlap(self):
        """验证chunk_overlap必须小于chunk_size。"""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self


class ProjectConfig(BaseModel):
    """项目总配置。"""

    model_config = ConfigDict(extra="forbid")

    project: ProjectInfo
    paths: PathConfig
    model: ModelConfig
    rag: RagConfig


class EnvSecret(BaseModel):
    """环境变量密钥配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: SecretStr


ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


def _get_logger():
    """获取配置工具logger。"""
    return get_logger(__name__)


def _load_config_data(config_path: str) -> dict:
    """根据文件后缀加载JSON或YAML配置。"""
    logger = _get_logger()
    path = Path(config_path).expanduser().resolve()
    suffix = path.suffix.lower()
    logger.debug("开始加载配置文件: %s", path)

    with path.open("r", encoding="utf-8") as config_file:
        if suffix == ".json":
            config_data = json.load(config_file)
            logger.info("JSON配置文件加载完成: %s", path)
            return config_data
        if suffix in {".yaml", ".yml"}:
            config_data = yaml.safe_load(config_file) or {}
            logger.info("YAML配置文件加载完成: %s", path)
            return config_data

    logger.error("不支持的配置文件类型: %s", suffix)
    raise ValueError(f"Unsupported config file type: {suffix}")


def load_config(config_path: str, model_cls: type[ConfigModel]) -> ConfigModel:
    """加载配置文件并解析为指定Pydantic模型。"""
    logger = _get_logger()
    logger.debug("开始解析配置模型: path=%s, model=%s", config_path, model_cls.__name__)
    config_data = _load_config_data(config_path)
    config = model_cls.model_validate(config_data)
    logger.info("配置模型解析完成: model=%s", model_cls.__name__)
    return config


def load_project_config(
        config_path: Optional[str] = None,
) -> ProjectConfig:
    """加载项目总配置。"""
    logger = _get_logger()
    target_config_path = config_path or get_abs_path("config/project_config.yaml")
    logger.debug("加载项目总配置: %s", target_config_path)
    config = load_config(target_config_path, ProjectConfig)
    logger.info("项目总配置加载完成: %s", config.project.name)
    return config


def load_model_api_key(
        config: Optional[ProjectConfig] = None,
        env_file: Optional[str] = None,
) -> EnvSecret:
    """从环境变量或.env文件加载模型API Key。"""
    logger = _get_logger()
    project_config = config or load_project_config()
    target_env_file = env_file or get_abs_path(".env")

    if target_env_file and Path(target_env_file).exists():
        logger.debug("加载.env文件: %s", target_env_file)
        load_dotenv(target_env_file, override=False)

    api_key_name = project_config.model.api_key_env
    api_key_value = os.getenv(api_key_name)
    if not api_key_value:
        logger.error("模型API Key缺失: %s", api_key_name)
        raise ValueError(f"Missing API key: {api_key_name}")

    logger.info("模型API Key加载完成: %s", api_key_name)
    return EnvSecret(name=api_key_name, value=api_key_value)


def _load_yaml_dict(config_path: Optional[str]) -> Optional[dict]:
    """加载YAML配置并返回普通字典，兼容现有工具调用。"""
    logger = _get_logger()
    if config_path is None:
        logger.debug("配置路径为空，返回None")
        return None

    logger.debug("加载YAML字典配置: %s", config_path)
    config_data = _load_config_data(config_path)
    logger.info("YAML字典配置加载完成: %s", config_path)
    return config_data


def load_rag_config(
        config_path: Optional[str] = None,
) -> Optional[dict]:
    """加载RAG配置文件。"""
    target_config_path = config_path or get_abs_path("config/rag_config.yaml")
    return _load_yaml_dict(target_config_path)


def load_chroma_config(
        config_path: Optional[str] = None,
) -> Optional[dict]:
    """加载Chroma配置文件。"""
    target_config_path = config_path or get_abs_path("config/chroma_config.yaml")
    return _load_yaml_dict(target_config_path)


def load_prompts_config(
        config_path: Optional[str] = None,
) -> Optional[dict]:
    """加载Prompts配置文件。"""
    target_config_path = config_path or get_abs_path("config/prompts.yaml")
    return _load_yaml_dict(target_config_path)


def load_agent_config(
        config_path: Optional[str] = None,
) -> Optional[dict]:
    """加载Agent配置文件。"""
    target_config_path = config_path or get_abs_path("config/agent_config.yaml")
    return _load_yaml_dict(target_config_path)
