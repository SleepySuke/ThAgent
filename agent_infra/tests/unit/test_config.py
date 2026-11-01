"""两级模型解析：per-agent 覆盖 > 全局默认 > 代码默认值。"""
from __future__ import annotations

from harness.config import resolve_model


def test_falls_back_to_code_default(monkeypatch):
    monkeypatch.delenv("AGENT_INFRA_MODEL", raising=False)
    monkeypatch.delenv("AGENT_INFRA_MODEL_CR_AGENT", raising=False)
    assert resolve_model("cr_agent", "zai/glm-4.6") == "zai/glm-4.6"


def test_global_env_overrides_default(monkeypatch):
    monkeypatch.setenv("AGENT_INFRA_MODEL", "dashscope/qwen-plus")
    monkeypatch.delenv("AGENT_INFRA_MODEL_CR_AGENT", raising=False)
    assert resolve_model("cr_agent", "zai/glm-4.6") == "dashscope/qwen-plus"


def test_per_node_env_wins(monkeypatch):
    monkeypatch.setenv("AGENT_INFRA_MODEL", "dashscope/qwen-plus")
    monkeypatch.setenv("AGENT_INFRA_MODEL_CR_AGENT", "zai/glm-4.5-air")
    assert resolve_model("cr_agent", "zai/glm-4.6") == "zai/glm-4.5-air"


def test_register_model_capabilities_unlocks_tools():
    """xiaomi_mimo 缺 litellm 元数据导致 tools 被拒；注册后解锁。"""
    from litellm import get_supported_openai_params

    from harness.config import register_model_capabilities

    register_model_capabilities()
    assert "tools" in get_supported_openai_params("xiaomi_mimo/mimo-v2.5-pro")
    # 幂等：二次调用不抛
    register_model_capabilities()
