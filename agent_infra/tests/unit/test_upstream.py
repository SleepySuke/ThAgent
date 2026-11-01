"""upstream 语义结论注入的单测：契约字段 + 截断守卫（矩阵 #1/#2/#4/#7）。"""
import json

from harness.contract import AgentInput
from harness.engine import UPSTREAM_MAX_CHARS, _build_upstream, _clip_upstream

BY_ID = {"cr": {"id": "cr", "agent": "cr_agent"},
         "req": {"id": "req", "agent": "requirement_agent"},
         "bad": {"id": "bad", "agent": "strategy_agent"},
         "empty": {"id": "empty", "agent": "report_agent"}}


def test_agent_input_upstream_default_and_roundtrip():  # 矩阵 #7
    ai = AgentInput(run_id="t", node_id="cr_agent", input_data={"commit": "d"})
    assert ai.upstream == {}                       # 默认空，向后兼容
    ai.upstream = {"requirement_agent": {"task_type": "bugfix"}}
    assert AgentInput(**json.loads(ai.to_json())).upstream == {
        "requirement_agent": {"task_type": "bugfix"}}   # JSON 序列化往返不丢


def test_clip_upstream_passthrough_short():
    data = {"task_type": "feature", "scope": ["shop/pricing.py"]}
    assert _clip_upstream(data) == data            # ≤500 字原样


def test_clip_upstream_truncates_over_limit():  # 矩阵 #1
    data = {"summary": "甲" * (UPSTREAM_MAX_CHARS + 100)}
    out = _clip_upstream(data)
    assert out["_truncated"] is True               # 诚实标注
    assert len(out["head"]) == UPSTREAM_MAX_CHARS  # 头部截断


def test_clip_upstream_non_dict_or_empty_returns_none():
    assert _clip_upstream("garbage") is None
    assert _clip_upstream(None) is None
    assert _clip_upstream({}) is None              # 空结论无语义


def test_build_upstream_skips_and_counts_corrupt():  # 矩阵 #4
    node_outputs = {"cr": "garbage",                       # 条目非 dict
                    "req": {"output_data": "oops"},        # 结论非 dict
                    "bad": {"output_data": {"a": 1}},
                    "empty": {}}                           # 无结论，静默跳过
    upstream, nodes, corrupt = _build_upstream(
        node_outputs, ["cr", "req", "bad", "empty"], BY_ID)
    assert corrupt == 2                            # 两个坏条目计数
    assert upstream == {"strategy_agent": {"a": 1}}  # 键 = registry 名
    assert nodes == ["strategy_agent"]


def test_build_upstream_missing_entry_tolerated():  # 矩阵 #2
    upstream, _nodes, corrupt = _build_upstream({"cr": {"output_data": {}}},
                                                ["cr", "req"], BY_ID)
    assert upstream == {} and corrupt == 0         # 缺条目/空结论不炸不计数
