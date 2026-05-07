# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:48:00
@Description：
提示词文件加载工具类
'''
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, FilePath

from utils.config_handler import load_prompts_config
from utils.logger_handler import get_logger
from utils.path_tool import get_abs_path


class PromptConfig(BaseModel):
    """提示词文件路径配置。"""

    model_config = ConfigDict(extra="forbid")

    main_prompt_file: str = Field(min_length=1)
    rag_prompt_file: str = Field(min_length=1)
    report_prompt_file: str = Field(min_length=1)


class PromptTemplate(BaseModel):
    """已加载的提示词模板。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    path: FilePath
    content: str = Field(min_length=1)


class PromptBundle(BaseModel):
    """项目提示词集合。"""

    model_config = ConfigDict(extra="forbid")

    main_prompt: PromptTemplate
    rag_prompt: PromptTemplate
    report_prompt: PromptTemplate


def _get_logger():
    """获取提示词工具logger。"""
    return get_logger(__name__)


def _resolve_prompt_path(prompt_file: str) -> str:
    """将提示词相对路径解析为项目绝对路径。"""
    logger = _get_logger()
    logger.debug("开始解析提示词路径: %s", prompt_file)
    path = Path(prompt_file)
    if path.is_absolute():
        resolved_path = str(path)
        logger.debug("提示词路径为绝对路径: %s", resolved_path)
        return resolved_path

    resolved_path = get_abs_path(prompt_file)
    logger.debug("提示词路径解析完成: %s -> %s", prompt_file, resolved_path)
    return resolved_path


def load_prompt_template(name: str, prompt_file: str) -> PromptTemplate:
    """加载单个提示词文件。"""
    logger = _get_logger()
    logger.debug("开始加载提示词模板: name=%s, file=%s", name, prompt_file)
    prompt_path = _resolve_prompt_path(prompt_file)
    content = Path(prompt_path).read_text(encoding="utf-8").strip()
    prompt_template = PromptTemplate(
        name=name,
        path=prompt_path,
        content=content,
    )
    logger.info("提示词模板加载完成: name=%s, chars=%s", name, len(content))
    return prompt_template


def load_prompt_bundle(
        config_path: Optional[str] = None,
) -> PromptBundle:
    """加载项目全部提示词。"""
    logger = _get_logger()
    logger.debug("开始加载提示词集合: config_path=%s", config_path)
    prompt_config_data = load_prompts_config(config_path)
    prompt_config = PromptConfig.model_validate(prompt_config_data)

    prompt_bundle = PromptBundle(
        main_prompt=load_prompt_template("main_prompt", prompt_config.main_prompt_file),
        rag_prompt=load_prompt_template("rag_prompt", prompt_config.rag_prompt_file),
        report_prompt=load_prompt_template("report_prompt", prompt_config.report_prompt_file),
    )
    logger.info("提示词集合加载完成")
    return prompt_bundle
