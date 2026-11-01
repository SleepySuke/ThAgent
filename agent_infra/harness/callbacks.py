"""通用三层 callback 约束框架（harness 供给，所有 agent 共用）。

agent 定义只做组装；治理逻辑归 harness：before/after_agent（节点级）、
before/after_model（轮次级）、before/after_tool（动作级）。
agent 特有的 callback 才留在 agent 侧，叠加在通用层之上。

ADK 原生能力的使用口径：
- 轮次计数放 `callback_context.state`（ADK session state，跨轮持久），
  不自造计数器；harness key 加前缀避免与业务 state 冲突
- tool 调用取 `tool_context.function_call_id` 关联同一函数调用的
  before/after 事件；tool_context.state 与 callback state 是同一份
- RunContext 只保留 ADK 没有的东西：trace_id / repo / commit / event_sink
  （跨进程身份，经 A2A 传来的 harness 契约）
"""
from __future__ import annotations

from typing import Any

from harness.contract import RunContext
from harness.policy import (
    NodePolicy,
    PolicyViolation,
    TurnBudgetExceeded,
    check_run,
    check_tool,
    check_turn,
)

_TURN_KEY = "harness.turn"


def _short(x: Any) -> str:
    return str(x)[:300]


def build_callbacks(run: RunContext, policy: NodePolicy) -> dict:
    """构造六个 ADK callback，键名与 LlmAgent 构造参数一致。

    闭包参数名必须是 ADK 的关键字调用名——SDK 按关键字传参，名字对不上会在
    运行期 TypeError（单测直接位置调用测不出来）。注意 tool 回调不传
    callback_context，after_tool 的结果参数名是 tool_response（ADK 2.7 源码）。
    """
    return {
        "before_agent_callback": _before_agent(run, policy),
        "after_agent_callback": _after_agent(run),
        "before_model_callback": _before_model(run, policy),
        "after_model_callback": _after_model(run),
        "before_tool_callback": _before_tool(run, policy),
        "after_tool_callback": _after_tool(run),
    }


# ---- 三层 callback（玻璃盒：全部发事件，治理点三处） ----

def _before_agent(run: RunContext, policy: NodePolicy):
    def cb(callback_context):
        run.event_sink("agent_start", {"trace_id": run.trace_id})
        d = check_run(policy)
        if not d.allowed:
            run.event_sink("policy_deny", {"where": "before_agent", "reason": d.reason})
            raise PolicyViolation(d.reason)
        # 身份注入 ADK session state：后续任何 callback / tool 的
        # tool_context.state 都能取到（参数注入，ADK 原生机制）
        callback_context.state["harness.trace_id"] = run.trace_id
        callback_context.state["harness.commit"] = run.commit
    return cb


def _after_agent(run: RunContext):
    def cb(callback_context):
        run.event_sink("agent_end", {})
    return cb


def _before_model(run: RunContext, policy: NodePolicy):
    def cb(callback_context, llm_request):
        turn = int(callback_context.state.get(_TURN_KEY, 0)) + 1
        callback_context.state[_TURN_KEY] = turn
        run.event_sink("llm_call", {"turn": turn})
        d = check_turn(policy, turn)
        if not d.allowed:
            run.event_sink("policy_deny", {"where": "before_model", "reason": d.reason})
            raise TurnBudgetExceeded(d.reason)
    return cb


def _after_model(run: RunContext):
    def cb(callback_context, llm_response):
        # genai usage 字段名：prompt/candidates/total（litellm→ADK 映射，
        # 见 google/adk/models/lite_llm.py UsageMetadataChunk 分支）
        um = getattr(llm_response, "usage_metadata", None)
        usage = {"req": getattr(um, "prompt_token_count", None),
                 "res": getattr(um, "candidates_token_count", None),
                 "total": getattr(um, "total_token_count", None)} if um else {}
        run.event_sink("llm_end", usage)
    return cb


def _before_tool(run: RunContext, policy: NodePolicy):
    def cb(tool, args, tool_context):
        call_id = getattr(tool_context, "function_call_id", None)
        run.event_sink("tool_call", {"tool": tool.name, "call_id": call_id,
                                     "args": _short(args)})
        d = check_tool(policy, tool.name, args if isinstance(args, dict) else {})
        if not d.allowed:
            run.event_sink("policy_deny", {"where": "before_tool", "reason": d.reason})
            return {"error": f"policy denied: {d.reason}"}  # 跳过实际执行
        return None
    return cb


def _after_tool(run: RunContext):
    def cb(tool, args, tool_context, tool_response):
        call_id = getattr(tool_context, "function_call_id", None)
        run.event_sink("tool_result", {"tool": tool.name, "call_id": call_id,
                                       "result": _short(tool_response)})
    return cb
