"""Task 5：review API（POST /runs/{id}/review）+ run_status 审阅面。

矩阵 #2（审阅裁决）/#3（非审阅态幂等拒绝）：accept 200 → run 终态 ok；
replan+feedback → 新一轮 park（round=2）；重复裁决第二个 409；
无此 run 404；非审阅态 409；action 出域 422（pydantic Literal）。
"""
import json
import time
import unittest.mock

from starlette.testclient import TestClient

from app import create_app


def _save_cp(runs, tid, state, round_=1):
    from harness.checkpoint import save_checkpoint
    save_checkpoint(runs, tid, {
        "run_id": tid, "context_id": "repo:demo_repo",
        "current_node": "report", "harness_state": state,
        "completed_nodes": ["cr"], "node_outputs": {},
        "round": round_, "version": 2, "created_at": time.time()})


class ReviewEngine:
    """最小审阅语义 fake：pending 集合 + 裁决落盘（accept=completed /
    replan=executing round+1），与真实 engine 的 park/裁决闭环同形状。"""

    def __init__(self, runs_root):
        self.runs_root = runs_root
        self.pending: set[str] = set()
        self.verdicts: list[tuple] = []

    def review_run(self, trace_id, action, feedback=""):
        if trace_id not in self.pending:
            return False
        self.pending.discard(trace_id)
        self.verdicts.append((trace_id, action, feedback))
        if action == "accept":   # 终态收尾：checkpoint 出审阅态
            _save_cp(self.runs_root, trace_id, "completed")
        else:                    # replan：round+1，执行中（下一轮再 park）
            cp = json.loads((self.runs_root / trace_id / "checkpoint.json")
                            .read_text(encoding="utf-8"))
            _save_cp(self.runs_root, trace_id, "executing", round_=cp["round"] + 1)
        return True


def make_client(tmp_path):
    runs = tmp_path / "runs"
    app = create_app(engine=ReviewEngine(runs), fixture_repo=tmp_path,
                     runs_root=runs)
    return TestClient(app), runs


def _park_review(runs, tid, round_=1):
    """模拟 engine 报告已出 park 在审阅态：checkpoint + 报告产物。"""
    (runs / tid / "artifacts").mkdir(parents=True, exist_ok=True)
    (runs / tid / "artifacts" / "cr_report.json").write_text(
        '{"verdict": "approve"}', encoding="utf-8")
    (runs / tid / "artifacts" / "execution_report.md").write_text(
        "# 执行报告\n全部通过", encoding="utf-8")
    _save_cp(runs, tid, "review_pending", round_=round_)


def test_review_accept_200_then_status_ok(tmp_path):
    c, runs = make_client(tmp_path)
    _park_review(runs, "t1")
    c.app.state.engine.pending.add("t1")
    with c:
        r = c.post("/runs/t1/review", json={"action": "accept"})
        assert r.status_code == 200
        assert r.json() == {"reviewed": True, "action": "accept"}
        st = c.get("/runs/t1").json()
        assert st["status"] == "ok"   # 矩阵 #2 前半：accept → 终态


def test_review_replan_round2_and_repark(tmp_path):
    c, runs = make_client(tmp_path)
    _park_review(runs, "t2")
    c.app.state.engine.pending.add("t2")
    with c:
        r = c.post("/runs/t2/review",
                   json={"action": "replan", "feedback": "报告缺 pass_rate"})
        assert r.status_code == 200
        # app 层 replan 翻译为 engine 事件词汇 reject（Task 4 语义不动）
        assert c.app.state.engine.verdicts == [
            ("t2", "reject", "报告缺 pass_rate")]
        assert c.get("/runs/t2").json()["status"] != "review_pending"
        # 新一轮报告再 park（设计 §1：每轮都可裁决）→ run_status round=2
        _park_review(runs, "t2", round_=2)
        c.app.state.engine.pending.add("t2")
        st = c.get("/runs/t2").json()
        assert st["status"] == "review_pending"
        assert st["round"] == 2
        assert st["report"] == "# 执行报告\n全部通过"


def test_review_idempotent_second_409(tmp_path):
    c, runs = make_client(tmp_path)
    _park_review(runs, "t3")
    c.app.state.engine.pending.add("t3")
    with c:
        assert c.post("/runs/t3/review",
                      json={"action": "accept"}).status_code == 200
        r = c.post("/runs/t3/review", json={"action": "accept"})
        assert r.status_code == 409   # 矩阵 #2：首个生效，后续幂等拒绝
        assert r.json() == {"error": "run not awaiting review"}


def test_review_404_unknown_run_and_409_not_awaiting(tmp_path):
    c, runs = make_client(tmp_path)
    (runs / "t4").mkdir(parents=True)   # run 存在但从未进审阅态
    _park_review(runs, "t4")
    _save_cp(runs, "t4", "completed")   # 已跑完（非审阅态）
    with c:
        r = c.post("/runs/nope/review", json={"action": "accept"})
        assert r.status_code == 404
        assert r.json() == {"error": "no such run"}
        r2 = c.post("/runs/t4/review", json={"action": "accept"})
        assert r2.status_code == 409   # 矩阵 #3：非审阅态拒绝
        assert r2.json() == {"error": "run not awaiting review"}


def test_review_action_out_of_domain_422(tmp_path):
    c, runs = make_client(tmp_path)
    _park_review(runs, "t5")
    c.app.state.engine.pending.add("t5")
    with c:
        r = c.post("/runs/t5/review", json={"action": "rework"})
        assert r.status_code == 422   # Literal["accept","replan"] 出域


def test_run_status_review_pending_shape(tmp_path):
    """V2c-2：审阅面形状（status/round/report=execution_report.md 全文）。"""
    c, runs = make_client(tmp_path)
    _park_review(runs, "t6", round_=3)
    with c:
        st = c.get("/runs/t6").json()
        assert st["status"] == "review_pending"
        assert st["round"] == 3
        assert st["report"] == "# 执行报告\n全部通过"
    # 无报告的旧链（V2c-2 申报）：review_pending 但产物缺失 → report=None
    (runs / "t7").mkdir(parents=True)
    _save_cp(runs, "t7", "review_pending")
    with c:
        st = c.get("/runs/t7").json()
        assert st["status"] == "review_pending" and st["report"] is None


async def test_session_message_accept_routes_to_review(tmp_path):
    """t5-rev Important：review_pending 的「接受」经聊天直达审阅 accept。

    修复前 resume 分支调 resume_run——审阅态 handle 的 resume_event 为 None
    恒 False → 409，intake 教学承诺脱节。"""
    from harness.engine import HarnessEngine
    from harness.intake import classify_intent

    calls = []

    class _Engine(HarnessEngine):
        def paused_runs(self, context_id):
            return [{"trace_id": "t1", "current_node": "report",
                     "state": "review_pending", "context_id": "ctx"}]

        def review_run(self, trace_id, action, feedback=""):
            calls.append((trace_id, action))
            return True

    engine = _Engine(None, tmp_path)
    app = create_app(engine=engine, fixture_repo=tmp_path, runs_root=tmp_path)
    from starlette.testclient import TestClient
    with TestClient(app) as client, unittest.mock.patch(
            "harness.intake.classify_intent", classify_intent):
        # classify 用注入 complete 的真函数（app 内 to_thread 调它）
        from harness import intake
        intake._default_complete = lambda p: (
            '{"intent":"resume","trace_id":"t1"}')
        r = client.post("/session/ctx/message",
                        json={"query": "接受那份报告"})
    assert r.status_code == 200 and r.json()["intent"] == "review_accepted"
    assert calls == [("t1", "accept")]
