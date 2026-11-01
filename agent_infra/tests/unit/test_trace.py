import json

from harness.trace import Tracer


def test_emit_writes_jsonl_with_trace_fields(tmp_path):
    t = Tracer(tmp_path, "trace-1")
    span = t.emit("run_start", repo="fixtures/demo_repo", commit="defect-1")
    child = t.emit("tool_call", node_id="cr_agent", parent_span_id=span, tool="run_cmd")
    lines = (tmp_path / "trace-1" / "trace.jsonl").read_text().splitlines()
    assert len(lines) == 2
    first, second = (json.loads(x) for x in lines)
    assert first["trace_id"] == "trace-1" and first["event"] == "run_start"
    assert first["span_id"] and first["ts"]
    assert second["parent_span_id"] == span
    assert second["payload"] == {"tool": "run_cmd"}
    assert child == second["span_id"]
