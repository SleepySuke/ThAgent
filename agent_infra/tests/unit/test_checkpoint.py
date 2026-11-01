import json
from dataclasses import asdict

from harness.checkpoint import (
    Checkpoint,
    idempotency_key,
    load_checkpoint,
    recover_interrupted,
    save_checkpoint,
)
from harness.policy import NodePolicy


def test_save_load_checkpoint(tmp_path):
    cp = Checkpoint(run_id="r1", context_id="r1", current_node="cr",
                    harness_state="executing", completed_nodes=["cr"])
    save_checkpoint(tmp_path, "r1", asdict(cp))
    loaded = load_checkpoint(tmp_path, "r1")
    assert loaded["run_id"] == "r1"
    assert loaded["current_node"] == "cr"
    assert loaded["completed_nodes"] == ["cr"]
    assert load_checkpoint(tmp_path, "missing") is None


def test_idempotency_key_format():
    assert idempotency_key("r1", "cr_agent", 2) == "r1:cr_agent:2"


def test_retry_config_from_policy():
    p = NodePolicy(allowed_tools=frozenset(), allowed_cmds=frozenset())
    assert p.max_attempts == 3
    assert p.backoff_s == 1.0


def test_recover_interrupted(tmp_path):
    # 有 checkpoint 无 run_end → 可恢复
    save_checkpoint(tmp_path, "r1", asdict(Checkpoint(
        run_id="r1", context_id="r1", current_node="cr",
        harness_state="executing")))
    # 已结束的 run（有 run_end）→ 不恢复
    save_checkpoint(tmp_path, "r2", asdict(Checkpoint(
        run_id="r2", context_id="r2", current_node="cr",
        harness_state="completed")))
    (tmp_path / "r2" / "trace.jsonl").write_text(
        json.dumps({"event": "run_end"}) + "\n")
    recovered = recover_interrupted(tmp_path)
    assert [r["run_id"] for r in recovered] == ["r1"]
