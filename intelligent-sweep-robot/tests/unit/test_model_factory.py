# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 21:13:17
@Description：
model factory单元测试
'''
import inspect

import pytest

from model.factory import ModelFactory, TongyiModelFactory, get_model_factory
from utils.config_handler import ProjectConfig


def _build_project_config(provider="tongyi"):
    """构建测试用项目配置。"""
    return ProjectConfig.model_validate(
        {
            "project": {
                "name": "intelligent-sweep-robot",
                "version": "1.0",
                "description": "智扫通Agent实验项目",
            },
            "paths": {
                "data_dir": "data",
                "logs_dir": "logs",
                "prompts_dir": "prompts",
                "vector_store_dir": "chroma_db",
            },
            "model": {
                "provider": provider,
                "chat_model": "qwen-plus",
                "embedding_model": "text-embedding-v4",
                "api_key_env": "DASHSCOPE_API_KEY",
                "temperature": 0.2,
            },
        }
    )


@pytest.fixture(autouse=True)
def clear_model_factory_singletons():
    """清理工厂单例缓存，避免测试之间共享实例。"""
    ModelFactory._instances.clear()
    yield
    ModelFactory._instances.clear()


def test_model_factory_is_abstract_class():
    """ModelFactory应该是抽象基类，不能直接实例化。"""
    assert inspect.isabstract(ModelFactory)

    with pytest.raises(TypeError):
        ModelFactory(_build_project_config())


def test_tongyi_model_factory_is_singleton():
    """TongyiModelFactory应该按具体工厂类实现单例。"""
    config = _build_project_config()

    first_factory = TongyiModelFactory(config)
    second_factory = TongyiModelFactory(config)

    assert first_factory is second_factory
    assert first_factory.config is config


def test_get_model_factory_returns_provider_factory():
    """get_model_factory应该根据provider返回对应的具体工厂。"""
    config = _build_project_config(provider="tongyi")

    factory = get_model_factory(config=config)

    assert isinstance(factory, TongyiModelFactory)


def test_get_model_factory_rejects_unsupported_provider():
    """不支持的provider应该抛出明确异常。"""
    config = _build_project_config(provider="unknown")

    with pytest.raises(ValueError, match="Unsupported model provider"):
        get_model_factory(config=config)
