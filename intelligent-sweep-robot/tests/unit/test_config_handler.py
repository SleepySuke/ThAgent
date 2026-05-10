# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:38:38
@Description：
config_handler单元测试
'''
import json

import pytest
from pydantic import ValidationError

from utils.config_handler import (
    ChromaConfig,
    EnvSecret,
    ProjectConfig,
    RagRuntimeConfig,
    load_chroma_config,
    load_model_api_key,
    load_project_config,
    load_rag_config,
)


def _write_project_config(config_path):
    """写入测试用项目配置。"""
    config_data = {
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
            "provider": "tongyi",
            "chat_model": "qwen-plus",
            "embedding_model": "text-embedding-v4",
            "api_key_env": "DASHSCOPE_API_KEY",
            "temperature": 0.2,
        },
    }
    config_path.write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")


def _write_chroma_config(config_path, chunk_size=500, chunk_overlap=80):
    """写入测试用Chroma配置。"""
    config_data = {
        "persist_directory": "chroma_db",
        "collection_name": "sweep_robot_knowledge",
        "document_loader": {
            "supported_file_types": [".txt", ".pdf"],
            "deduplicate": True,
            "deduplicate_by": "content_md5",
        },
        "text_splitter": {
            "type": "recursive_character",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "separators": ["\n\n", "\n", "。", "，", " ", ""],
        },
        "retriever": {
            "search_type": "similarity",
            "top_k": 4,
            "score_threshold": None,
        },
        "metadata": {
            "hnsw_space": "cosine",
        },
    }
    config_path.write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")


def test_load_project_config_returns_project_config_model(tmp_path):
    """配置加载结果应该是强类型ProjectConfig模型。"""
    config_path = tmp_path / "project_config.json"
    _write_project_config(config_path)

    config = load_project_config(str(config_path))

    assert isinstance(config, ProjectConfig)
    assert config.project.name == "intelligent-sweep-robot"
    assert config.paths.data_dir == "data"
    assert config.model.chat_model == "qwen-plus"
    assert config.model.embedding_model == "text-embedding-v4"


def test_load_chroma_config_rejects_invalid_chunk_overlap(tmp_path):
    """Chroma切分配置中chunk_overlap不能大于或等于chunk_size。"""
    config_path = tmp_path / "chroma_config.json"
    _write_chroma_config(config_path, chunk_size=100, chunk_overlap=100)

    with pytest.raises(ValidationError):
        load_chroma_config(str(config_path))


def test_default_project_config_exists_and_loads():
    """项目默认配置文件应该存在并能被加载。"""
    config = load_project_config()

    assert isinstance(config, ProjectConfig)
    assert config.paths.data_dir == "data"
    assert config.model.api_key_env == "DASHSCOPE_API_KEY"
    assert config.model.embedding_model


def test_default_chroma_config_exists_and_loads():
    """默认Chroma配置应该只描述向量库、文档加载、切分和召回。"""
    config = load_chroma_config()

    assert isinstance(config, ChromaConfig)
    assert config.collection_name == "sweep_robot_knowledge"
    assert config.document_loader.supported_file_types == [".txt", ".pdf"]
    assert config.document_loader.deduplicate is True
    assert config.document_loader.deduplicate_by == "content_md5"
    assert config.text_splitter.chunk_size > config.text_splitter.chunk_overlap
    assert config.retriever.top_k == 4


def test_default_rag_config_exists_and_loads():
    """默认RAG配置应该只描述RAG编排、prompt、上下文、生成和输出策略。"""
    config = load_rag_config()

    assert isinstance(config, RagRuntimeConfig)
    assert config.model.use_project_default is True
    assert config.prompt.prompt_name == "rag_prompt"
    assert config.context.max_context_docs == 4
    assert config.generation.require_grounded_answer is True
    assert config.output.include_source_file_names is True


def test_load_model_api_key_reads_secret_from_env_file(tmp_path, monkeypatch):
    """模型API Key应该从.env文件读取，并用Pydantic SecretStr承载。"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("DASHSCOPE_API_KEY=test-secret-value\n", encoding="utf-8")
    config_path = tmp_path / "project_config.json"
    _write_project_config(config_path)
    config = load_project_config(str(config_path))

    env_secret = load_model_api_key(config=config, env_file=str(env_path))

    assert isinstance(env_secret, EnvSecret)
    assert env_secret.name == "DASHSCOPE_API_KEY"
    assert env_secret.value.get_secret_value() == "test-secret-value"


def test_load_model_api_key_raises_when_env_value_missing(tmp_path, monkeypatch):
    """缺少环境变量值时应该给出明确异常。"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    config_path = tmp_path / "project_config.json"
    _write_project_config(config_path)
    config = load_project_config(str(config_path))

    with pytest.raises(ValueError, match="Missing API key"):
        load_model_api_key(config=config, env_file=str(tmp_path / ".env"))
