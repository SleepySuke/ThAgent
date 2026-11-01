"""运行配置：env 注入（.env / AGENT_INFRA_*），换配置不改码。

本地持久化口径：trace、artifacts、ADK session sqlite（adk_sessions.db）全部落
在 runs_root 下，不引外部 DB。

多模型口径：两级 env 解析——AGENT_INFRA_MODEL_<NODE>（按 agent 覆盖）→
AGENT_INFRA_MODEL（全局默认）→ 代码默认值。多 provider 的 key 由 litellm
按前缀各自读 env（ZAI_API_KEY / DASHSCOPE_API_KEY / ...），不建 key 管理层。
"""
from __future__ import annotations

import os
from pathlib import Path


def runs_root() -> Path:
    p = os.environ.get("AGENT_INFRA_RUNS_DIR")
    return Path(p).expanduser() if p else Path(__file__).resolve().parent.parent / "runs"


def resolve_model(node_id: str, default: str) -> str:
    """节点级模型解析：per-agent env 覆盖 > 全局 env > 代码默认值。

    值为 litellm 前缀路由格式（如 zai/glm-4.6、dashscope/qwen-plus）。
    # ponytail: 二期 router 多 agent 时升级为路由表（成本分级/降级链），接缝即此函数
    """
    per_node = os.environ.get(f"AGENT_INFRA_MODEL_{node_id.upper()}")
    return per_node or os.environ.get("AGENT_INFRA_MODEL") or default


# 能力补丁：litellm 的 model_cost 对 xiaomi_mimo 前缀无条目（只有 openrouter
# 别名），supports_function_calling 缺省 False → 拒绝 tools。端点实测支持
# function calling（tool_calls 正常返回），这里补元数据解锁。新增 provider
# 前先 curl 实测能力，缺元数据就在此登记。
_FC = {
    "supports_function_calling": True,
    "supports_tool_choice": True,
    "supports_parallel_function_calling": True,
    "supports_streaming": True,
}

_MODEL_CAPABILITY_PATCHES: dict[str, dict] = {
    "xiaomi_mimo/mimo-v2.5-pro": dict(_FC),
    # 模型对比评测（2026-10-23）接入的新前缀：同款补丁解锁 tools
    "xiaomi_mimo/mimo-v2.6-pro": dict(_FC),
    "zai/glm-5.1": dict(_FC),
    "dashscope/qwen3.7-max": dict(_FC),
    "anthropic/deepseek-v4-pro": dict(_FC),
    "anthropic/claude-opus-4-8": dict(_FC),
}


def register_model_capabilities() -> None:
    """把缺元数据的模型能力补进 litellm.model_cost（幂等，进程启动时调一次）。"""
    import litellm

    for model, caps in _MODEL_CAPABILITY_PATCHES.items():
        litellm.model_cost.setdefault(model, {}).update(caps)
