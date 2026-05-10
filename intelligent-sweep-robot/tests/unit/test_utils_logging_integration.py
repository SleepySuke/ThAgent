# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:58:00
@Description：
utils工具日志集成单元测试
'''
import json

from utils import config_handler, file_handler, path_tool, prompt_handler


class FakeLogger:
    """测试用logger，记录被调用的方法。"""

    def __init__(self):
        self.calls = []

    def debug(self, message, *args, **kwargs):
        self.calls.append(("debug", message, args, kwargs))

    def info(self, message, *args, **kwargs):
        self.calls.append(("info", message, args, kwargs))

    def error(self, message, *args, **kwargs):
        self.calls.append(("error", message, args, kwargs))


def _patch_module_logger(monkeypatch, target_module):
    """替换目标模块的get_logger并返回fake logger。"""
    fake_logger = FakeLogger()
    monkeypatch.setattr(
        target_module,
        "get_logger",
        lambda name=None: fake_logger,
        raising=False,
    )
    return fake_logger


def test_path_tool_calls_logger(monkeypatch):
    """路径工具应该调用logger记录路径解析过程。"""
    fake_logger = _patch_module_logger(monkeypatch, path_tool)

    path_tool.get_abs_path("data")

    assert fake_logger.calls


def test_config_handler_calls_logger(tmp_path, monkeypatch):
    """配置工具应该调用logger记录配置加载过程。"""
    fake_logger = _patch_module_logger(monkeypatch, config_handler)
    config_path = tmp_path / "project_config.json"
    config_path.write_text(
        json.dumps(
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
                    "chat_model": "qwen-plus",
                    "embedding_model": "text-embedding-v4",
                    "api_key_env": "DASHSCOPE_API_KEY",
                    "temperature": 0.2,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config_handler.load_project_config(str(config_path))

    assert fake_logger.calls


def test_file_handler_calls_logger(tmp_path, monkeypatch):
    """文件工具应该调用logger记录文件读取过程。"""
    fake_logger = _patch_module_logger(monkeypatch, file_handler)
    txt_path = tmp_path / "knowledge.txt"
    txt_path.write_text("智扫通S1适合小户型。", encoding="utf-8")

    file_handler.load_file(str(txt_path))

    assert fake_logger.calls


def test_prompt_handler_calls_logger(tmp_path, monkeypatch):
    """提示词工具应该调用logger记录提示词加载过程。"""
    fake_logger = _patch_module_logger(monkeypatch, prompt_handler)
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("可用工具：rag_summarize\n调用时机：知识库问答", encoding="utf-8")

    prompt_handler.load_prompt_template("test_prompt", str(prompt_path))

    assert fake_logger.calls
