# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-11
@Description：
智扫通 Middleware 包入口。

基于 LangChain middleware 装饰器（before_model / after_model /
wrap_tool_call / dynamic_prompt）实现：
- AgentMiddleware: 执行链路观测（日志 + 工具监控）
- prompt_switcher: Prompt 动态切换（main / report）
'''
from middleware.agent_middleware import (
    create_middleware_from_config,
    load_middleware_config,
)
from middleware.prompt_switcher import build_prompt_middleware

__all__ = [
    "build_prompt_middleware",
    "create_middleware_from_config",
    "load_middleware_config",
]
