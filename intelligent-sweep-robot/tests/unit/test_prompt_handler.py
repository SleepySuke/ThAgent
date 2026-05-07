# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:47:15
@Description：
prompt_handler单元测试
'''
from pathlib import Path

from utils.config_handler import load_prompts_config
from utils.path_tool import get_project_root
from utils.prompt_handler import PromptBundle, PromptTemplate, load_prompt_bundle


def test_prompt_config_points_to_prompt_files():
    """prompt配置应该只保存提示词文件路径。"""
    prompt_config = load_prompts_config()

    assert prompt_config == {
        "main_prompt_file": "prompts/main_prompt.txt",
        "rag_prompt_file": "prompts/rag_prompt.txt",
        "report_prompt_file": "prompts/report_prompt.txt",
    }

    project_root = Path(get_project_root())
    for prompt_file in prompt_config.values():
        assert (project_root / prompt_file).exists()


def test_load_prompt_bundle_returns_pydantic_models():
    """prompt加载结果应该是强类型Pydantic模型。"""
    prompt_bundle = load_prompt_bundle()

    assert isinstance(prompt_bundle, PromptBundle)
    assert isinstance(prompt_bundle.main_prompt, PromptTemplate)
    assert prompt_bundle.rag_prompt.path.exists()
    assert prompt_bundle.rag_prompt.path.is_file()
    assert "智扫通" in prompt_bundle.main_prompt.content
    assert "RAG" in prompt_bundle.rag_prompt.content
    assert "月度使用报告" in prompt_bundle.report_prompt.content


def test_each_prompt_declares_tools_and_call_timing():
    """每个提示词都应该明确可用工具和调用时机。"""
    prompt_bundle = load_prompt_bundle()

    prompts = [
        prompt_bundle.main_prompt.content,
        prompt_bundle.rag_prompt.content,
        prompt_bundle.report_prompt.content,
    ]
    for prompt_content in prompts:
        assert "可用工具" in prompt_content
        assert "调用时机" in prompt_content


def test_main_prompt_declares_all_agent_tools():
    """主提示词应该列出Agent可调用的全部工具。"""
    prompt_bundle = load_prompt_bundle()
    main_prompt = prompt_bundle.main_prompt.content

    for tool_name in [
        "rag_summarize",
        "get_weather",
        "get_user_location",
        "get_user_id",
        "get_current_month",
        "generate_external_data",
    ]:
        assert tool_name in main_prompt
