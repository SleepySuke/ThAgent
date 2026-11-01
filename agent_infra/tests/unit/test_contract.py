import json

import pytest

from harness.contract import (
    AgentInput,
    AgentOutput,
    ExecutionPlan,
    OutputContractError,
    parse_output,
    parse_plan,
    parse_result,
    validate_output,
)
from harness.memory import NoopMemory, RecallSpec

VALID = {"issues": [{"file": "shop/pricing.py", "line": 3, "severity": "mid",
                     "type": "consistency", "desc": "x"}],
         "verdict": "request_changes", "summary": "ok"}


def test_parse_output_plain_and_fenced():
    a = parse_output(json.dumps(VALID))
    assert a.status == "ok" and a.output_data["verdict"] == "request_changes"
    b = parse_output(f"结论如下：\n```json\n{json.dumps(VALID)}\n```\n完")
    assert b.output_data == a.output_data


def test_parse_output_rejects_garbage():
    with pytest.raises(OutputContractError):
        parse_output("没有 json 的回答")


def test_validate_output_catches_bad_fields():
    errs = validate_output({"issues": [], "verdict": "maybe", "summary": ""})
    assert any("verdict" in e for e in errs)


def test_agent_input_roundtrip():
    ai = AgentInput(run_id="t", node_id="cr_agent", input_data={"commit": "defect-1"},
                    context_id="t", task_id="", artifact_refs=[], history=[],
                    hitl_feedback=None)
    assert AgentInput(**json.loads(ai.to_json())) == ai


def test_noop_memory_skeleton():
    m = NoopMemory()
    assert m.recall(RecallSpec(node_id="cr_agent", payload={})) == []
    m.record("t", None)  # no-op，不抛错


def test_parse_result_wrapper_contract():
    wrapped = json.dumps({"output_data": VALID, "artifact_url": "runs/x/cr_report.json",
                          "status": "ok"})
    out = parse_result(wrapped)
    assert out.status == "ok"
    assert out.output_data["verdict"] == "request_changes"
    assert out.artifact_url == "runs/x/cr_report.json"


def test_parse_result_surfaces_non_json_text():
    with pytest.raises(OutputContractError, match="non-json terminal text"):
        parse_result("cr_agent failed: boom")
    with pytest.raises(OutputContractError, match="missing output_data"):
        parse_result(json.dumps({"status": "ok"}))


def test_agent_input_new_fields():
    ai = AgentInput(run_id="t", node_id="testing", input_data={"commit": "d"},
                    context_id="t", task_id="task-1",
                    artifact_refs=[{"artifact_id": "A001", "type": "cr_report"}],
                    history=[], hitl_feedback={"ok": True})
    d = json.loads(ai.to_json())
    assert d["input_data"] == {"commit": "d"}
    assert d["context_id"] == "t" and d["task_id"] == "task-1"
    assert d["artifact_refs"] == [{"artifact_id": "A001", "type": "cr_report"}]
    assert d["hitl_feedback"] == {"ok": True}


def test_agent_output_new_fields():
    out = AgentOutput(output_data={"issues": []}, artifact_url="", status="ok",
                      artifacts=[{"artifact_id": "A001"}], metrics={"turns": 3},
                      next_hint={"suggest": "run_tests"})
    assert out.artifacts == [{"artifact_id": "A001"}]
    assert out.metrics == {"turns": 3}
    assert out.next_hint == {"suggest": "run_tests"}


PLAN = {"plan_id": "P001",
        "nodes": [{"id": "cr", "agent": "cr_agent"},
                  {"id": "test_recall", "agent": "test_recall_agent"},
                  {"id": "case", "agent": "case_agent"},
                  {"id": "script", "agent": "script_agent"},
                  {"id": "execute", "program": "case_executor"}],
        "edges": [["cr", "test_recall"], ["test_recall", "case"],
                  ["case", "script"], ["script", "execute"]]}


def test_execution_plan_parse():
    plan = parse_plan(json.dumps(PLAN))
    assert isinstance(plan, ExecutionPlan)
    assert plan.plan_id == "P001"
    assert len(plan.nodes) == 5
    assert plan.edges == [["cr", "test_recall"], ["test_recall", "case"],
                          ["case", "script"], ["script", "execute"]]
    # 带 fence 也能解析
    assert parse_plan(f"```json\n{json.dumps(PLAN)}\n```").nodes == plan.nodes


def test_parse_plan_rejects_unknown_node():
    bad = {"plan_id": "P", "nodes": [{"id": "x", "agent": "no_such_agent"}],
           "edges": []}
    with pytest.raises(OutputContractError, match="unknown node"):
        parse_plan(json.dumps(bad))


def test_parse_plan_rejects_invalid_edge():
    bad = {"plan_id": "P",
           "nodes": [{"id": "cr", "agent": "cr_agent"},
                     {"id": "test_recall", "agent": "test_recall_agent"}],
           "edges": [["test_recall", "cr"]]}  # 反向边不在 DAG
    with pytest.raises(OutputContractError, match="not in DAG"):
        parse_plan(json.dumps(bad))
