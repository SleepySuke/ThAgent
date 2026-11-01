"""tool_calling scorer 单测：四指标 + 节点归属 + 容错（矩阵 #1/#2/#3）。"""
import json

import pytest

from eval.evaluate import load_golden
from eval.tool_calling import load_trace, score_tool_calling

MUST_USE = {"cr_agent": ["read_diff"],
            "testing_agent": ["read_artifact", "write_file"]}


def _ev(event, node_id=None, **payload):
    return {"event": event, "node_id": node_id, "payload": payload}


def _chain_events(with_agent=True):
    """cr（read_diff + 越权 run_cmd + turn budget 拒绝 + 2 轮）→ testing（3 工具）。"""
    def _start(nid, agent):
        p = {"upstream": {}} if with_agent else {}
        if with_agent:
            p["agent"] = agent
        return _ev("node_start", nid, **p)

    return [
        _ev("run_start", commit="defect-1"),
        _ev("policy_deny", where="before_agent", reason="no policy"),
        _ev("plan_ready", nodes=[{"id": "cr", "agent": "cr_agent"},
                                 {"id": "testing", "agent": "testing_agent"}]),
        _start("cr", "cr_agent"),
        _ev("llm_call", turn=1),
        _ev("tool_call", tool="read_diff", call_id="c1"),
        _ev("llm_call", turn=2),
        _ev("tool_call", tool="run_cmd", call_id="c2"),
        _ev("policy_deny", where="before_tool",
            reason="tool not allowed: run_cmd"),
        _ev("policy_deny", where="before_model",
            reason="turn budget exceeded: 3 > 2"),   # 矩阵 #2：不计
        _ev("node_end", "cr", status="ok"),
        _start("testing", "testing_agent"),
        _ev("llm_call", turn=1),
        _ev("tool_call", tool="read_artifact", call_id="c3"),
        _ev("tool_call", tool="write_file", call_id="c4"),
        _ev("node_end", "testing", status="ok"),
        _ev("run_end", status="ok"),
    ]


def test_legality_denied_excludes_turn_budget():  # 矩阵 #2
    m = score_tool_calling(_chain_events(), MUST_USE)
    assert m["denied"] == 1                    # 3 条 policy_deny 只计 before_tool
    assert m["tool_calls"] == 4
    assert m["legality"] == pytest.approx(3 / 4)
    assert m["must_use_hit"] == 1.0            # 3/3 条目全命中
    assert m["turns_per_node"] == {"cr_agent": 2, "testing_agent": 1}


def test_zero_tool_calls_no_division_error():  # 矩阵 #3
    events = [e for e in _chain_events() if e["event"] != "tool_call"]
    m = score_tool_calling(events, MUST_USE)
    assert m["tool_calls"] == 0 and m["denied"] == 0
    assert m["legality"] == 1.0                # 空集不除零
    assert m["must_use_hit"] == 0.0            # 没干活如实 0（3 条目全 miss）


def test_agent_absent_from_run_counts_miss():
    m = score_tool_calling(_chain_events(), {**MUST_USE,
                                             "report_agent": ["read_artifact"]})
    assert m["must_use_hit"] == pytest.approx(3 / 4)   # report 没跑 → 条目 miss


def test_legacy_trace_falls_back_to_plan_ready_map():
    m = score_tool_calling(_chain_events(with_agent=False), MUST_USE)
    assert m["must_use_hit"] == 1.0            # 无 agent 键也能按 plan_ready 归属
    assert m["turns_per_node"] == {"cr_agent": 2, "testing_agent": 1}


def test_load_trace_skips_half_lines(tmp_path):  # 矩阵 #1
    run = tmp_path / "r"
    run.mkdir()
    (run / "trace.jsonl").write_text(
        json.dumps(_ev("run_start")) + "\n{broken-half-line\n\n",
        encoding="utf-8")
    assert load_trace(run) == [_ev("run_start")]


def test_load_trace_missing_file_raises_loud(tmp_path):  # 矩阵 #1
    with pytest.raises(FileNotFoundError, match="不能静默 0 分"):
        load_trace(tmp_path / "nope")


def test_golden_has_must_use_for_all_defects():
    for tag, entry in load_golden().items():
        assert entry["must_use"], tag
        assert all(isinstance(v, list) and v
                   for v in entry["must_use"].values()), tag
