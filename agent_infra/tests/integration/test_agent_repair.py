"""集成：契约修复轮按 agent 自己的契约判定（V3 申报）。

cr 保持 parse_output 严格契约 + 字段点名修复提示（行为不变）；做实 agent 按
自身 finalize 契约判定 + 通用修复提示。fake Runner 按脚本回放每轮回复。
"""
import json
from types import SimpleNamespace

import pytest

from agent_server import (
    _GENERIC_REPAIR,
    _REPAIR_PROMPT,
    _make_validator,
    load_agent_by_name,
    make_adk_run,
)
from harness.contract import RunContext

VALID_CR = {"issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                        "type": "exception", "desc": "bare except"}],
            "verdict": "request_changes", "summary": "s"}
REQ = {"task_type": "feature", "scope": ["shop/pricing.py"],
       "risks": [], "acceptance": ["折扣率不超过 0.20 上限"]}


class _Ev:
    def __init__(self, text):
        part = SimpleNamespace(text=text, thought=False)
        self.content = SimpleNamespace(parts=[part])

    def is_final_response(self):
        return True


class _Sessions:
    async def get_session(self, **kw):
        return None

    async def create_session(self, **kw):
        return SimpleNamespace(id="s1")


class _ScriptedRunner:
    """每次 run_async 弹一个脚本回复；记录每轮收到的 user 文本。"""

    def __init__(self, replies, prompts):
        self._replies = list(replies)
        self.prompts = prompts
        self.session_service = _Sessions()
        self.closed = False

    def run_async(self, **kw):
        self.prompts.append(kw["new_message"].parts[0].text)

        async def gen():
            yield _Ev(self._replies.pop(0))
        return gen()

    async def close(self):
        self.closed = True   # adk_run 的 finally 必调（t7-rev Important 修复）


async def _drive(monkeypatch, policy, replies, *,
                 validate=None, repair_prompt=None):
    """跑一次 adk_run：返回 (最终回复, 每轮 prompt, 事件名列表)。"""
    prompts: list[str] = []
    events: list[str] = []
    runner = _ScriptedRunner(replies, prompts)
    from google.adk import runners, sessions
    monkeypatch.setattr(runners, "Runner", lambda **kw: runner)
    monkeypatch.setattr(sessions, "DatabaseSessionService", lambda **kw: None)
    run = RunContext(trace_id="t", repo_path="x", commit="d",
                     event_sink=lambda e, p: events.append(e))
    adk = make_adk_run(lambda *a: None, policy,
                       validate=validate, repair_prompt=repair_prompt)
    out = await adk(run, "处理以下任务")
    assert runner.closed is True   # t7-rev Important：toolset 回收靠 runner.close
    return out, prompts, events


async def test_cr_drift_repaired_with_field_named_prompt(monkeypatch):
    from harness.policy import NODE_POLICIES
    final, prompts, events = await _drive(
        monkeypatch, NODE_POLICIES["cr_agent"],
        ["我今天审完了，没大问题", json.dumps(VALID_CR)])
    assert json.loads(final)["verdict"] == "request_changes"
    assert prompts[1] == _REPAIR_PROMPT             # cr 用字段点名的修复提示
    assert "contract_repair" in events


async def test_cr_valid_output_never_repairs(monkeypatch):
    from harness.policy import NODE_POLICIES
    _final, prompts, events = await _drive(
        monkeypatch, NODE_POLICIES["cr_agent"], [json.dumps(VALID_CR)])
    assert len(prompts) == 1 and "contract_repair" not in events  # cr 零行为变化


async def test_requirement_valid_output_skips_repair(monkeypatch):
    spec = load_agent_by_name("requirement_agent")
    final, prompts, events = await _drive(
        monkeypatch, spec.policy, [json.dumps(REQ)],
        validate=spec.validate, repair_prompt=spec.repair_prompt)
    assert json.loads(final)["task_type"] == "feature"
    assert len(prompts) == 1 and "contract_repair" not in events  # 合法输出不误修


async def test_requirement_drift_triggers_generic_repair(monkeypatch):
    spec = load_agent_by_name("requirement_agent")
    final, prompts, events = await _drive(
        monkeypatch, spec.policy,
        ["这次改动是把折扣率上限调整一下", json.dumps(REQ)],
        validate=spec.validate, repair_prompt=spec.repair_prompt)
    assert prompts[1] == _GENERIC_REPAIR            # 非 cr 用通用修复提示
    assert json.loads(final)["task_type"] == "feature"
    assert "contract_repair" in events


def test_make_validator_wraps_json_errors():
    v = _make_validator(load_agent_by_name("requirement_agent").parse)
    v(json.dumps(REQ))                              # 合法不抛
    with pytest.raises(ValueError):
        v("不是 json 的陈述文字")                     # JSONDecodeError 即 ValueError
