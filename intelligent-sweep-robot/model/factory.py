# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 21:13:17
@Description：
模型工厂抽象基类与具体模型工厂实现
'''
from abc import ABC, abstractmethod
from threading import Lock
from typing import ClassVar


from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings

from utils.config_handler import ProjectConfig, load_model_api_key, load_project_config
from utils.logger_handler import get_logger


class ModelFactory(ABC):
    """模型工厂抽象基类，按具体子类实现单例。"""

    _instances: ClassVar[dict[type, "ModelFactory"]] = {}
    _lock: ClassVar[Lock] = Lock()

    def __new__(cls, *args, **kwargs):
        """为每个具体工厂类创建唯一实例。"""
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]

    def __init__(self, config: ProjectConfig | None = None):
        """初始化工厂公共依赖。"""
        if getattr(self, "_initialized", False):
            return

        self.config = config or load_project_config()
        self.logger = get_logger(__name__)
        self._initialized = True

    @abstractmethod
    def create_chat_model(self, chat_model: str | None = None, temperature: float | None = None):
        """创建聊天模型。"""

    @abstractmethod
    def create_embedding_model(self):
        """创建Embedding模型。"""


class TongyiModelFactory(ModelFactory):
    """通义模型工厂。"""

    def create_chat_model(self, chat_model: str | None = None, temperature: float | None = None):
        """创建通义聊天模型。"""
        target_chat_model = chat_model or self.config.model.chat_model
        target_temperature = temperature if temperature is not None else self.config.model.temperature
        self.logger.info("开始创建Tongyi chat_model: %s", target_chat_model)
        api_key = load_model_api_key(config=self.config).value.get_secret_value()
        return ChatTongyi(
            model=target_chat_model,
            dashscope_api_key=api_key,
            model_kwargs={"temperature": target_temperature},
        )

    def create_embedding_model(self):
        """创建通义Embedding模型。"""
        self.logger.info("开始创建Tongyi embedding_model: %s", self.config.model.embedding_model)
        api_key = load_model_api_key(config=self.config).value.get_secret_value()
        return DashScopeEmbeddings(
            model=self.config.model.embedding_model,
            dashscope_api_key=api_key,
        )


def get_model_factory(config: ProjectConfig | None = None) -> ModelFactory:
    """根据配置中的provider返回具体模型工厂。"""
    project_config = config or load_project_config()
    provider = project_config.model.provider.lower()

    if provider == "tongyi":
        return TongyiModelFactory(project_config)

    raise ValueError(f"Unsupported model provider: {project_config.model.provider}")
