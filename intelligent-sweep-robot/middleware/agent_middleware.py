# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-11
@Description：
Agent Middleware 层 — 基于 LangChain middleware 装饰器实现执行链路观测。

包括：
1. LLM 调用前后日志（before_model / after_model）
2. 工具调用监控（wrap_tool_call）

调用方式：
    mw_list = create_middleware_from_config()
    agent = create_agent(model=model, tools=tools, middleware=[..., *mw_list])
'''
from langchain.agents.middleware import after_model, before_model, wrap_tool_call

from utils.config_handler import load_agent_config
from utils.logger_handler import get_logger

_logger = get_logger("middleware")


# ---------------------------------------------------------------------------
# Middleware 构建
# ---------------------------------------------------------------------------

def _build_before_model_middleware():
    """模型调用前记录日志。"""

    @before_model
    def _log_before_model(state, runtime):
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None
        _logger.info("[BeforeModel] 消息数: %s, 最后一条: %s", len(messages), last_msg)
        return None

    return _log_before_model


def _build_after_model_middleware():
    """模型调用后记录日志。"""

    @after_model
    def _log_after_model(state, runtime):
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None
        content = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
        preview = content[:200] if isinstance(content, str) else str(content)[:200]
        _logger.info("[AfterModel] 响应: %s", preview)
        return None

    return _log_after_model


def _build_tool_monitor_middleware():
    """工具调用前后记录日志。"""

    @wrap_tool_call
    def _log_tool_call(request, handler):
        tool_name = getattr(request, "tool_name", None) or getattr(request, "name", "unknown")
        tool_input = getattr(request, "tool_input", {}) or getattr(request, "input", "")
        _logger.info("[ToolMonitor] 调用工具: %s, 参数: %s", tool_name, tool_input)
        result = handler(request)
        _logger.info("[ToolMonitor] 工具结果: %s", str(result)[:200])
        return result

    return _log_tool_call


# ---------------------------------------------------------------------------
# 配置与工厂
# ---------------------------------------------------------------------------

def load_middleware_config() -> dict:
    """从 agent_config.yaml 加载 middleware 配置字典。"""
    config = load_agent_config()
    return config.get("middleware", {}) if config else {}


def create_middleware_from_config() -> list:
    """根据 agent_config.yaml 中的 middleware 配置创建 middleware 列表。

    配置项映射：
    - enable_log_before_model -> before_model middleware
    - enable_log_after_model  -> after_model middleware
    - enable_tool_monitor     -> tool monitor middleware

    当配置缺失时，默认全部开启。
    """
    mw_cfg = load_middleware_config()
    middleware_list = []

    if mw_cfg.get("enable_log_before_model", True):
        middleware_list.append(_build_before_model_middleware())
    if mw_cfg.get("enable_log_after_model", True):
        middleware_list.append(_build_after_model_middleware())
    if mw_cfg.get("enable_tool_monitor", True):
        middleware_list.append(_build_tool_monitor_middleware())

    return middleware_list
