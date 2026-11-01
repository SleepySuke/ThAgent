"""smoke_rag 纯函数自检：defect-5 命中谓词收紧 + 检索失败扫描（离线，不烧 LLM）。"""
import importlib.util
from pathlib import Path


def _load_smoke_rag():
    # scripts/ 不是包，按文件路径加载（module 级只做 import，不触发 main）
    p = Path(__file__).resolve().parents[2] / "scripts" / "smoke_rag.py"
    spec = importlib.util.spec_from_file_location("smoke_rag", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _issue(**override):
    base = {"file": "shop/promo.py", "line": 6, "severity": "mid",
            "desc": "促销折扣 30% 超过折扣率上限 20%"}
    return {**base, **override}


def test_hit_defect5_requires_keyword_and_severity():
    m = _load_smoke_rag()
    assert m._hit_defect5([_issue()])                       # 文件+severity+违规语义
    assert m._hit_defect5([_issue(severity="MID")])         # severity 大小写宽容
    assert not m._hit_defect5([_issue(severity="info")])    # severity 低于下限
    assert not m._hit_defect5([_issue(desc="命名不达意")])  # promo 文件但无违规语义
    assert not m._hit_defect5([_issue(file="shop/pricing.py")])  # 非 promo 文件
    # 终审取证的对抗样本：死代码角度（low + 只谈折扣话题词）不得算命中
    assert not m._hit_defect5([_issue(
        severity="low",
        desc="promo_rate() 是死代码：docstring 声称的'全场统一 30% 折扣'"
             "没有任何运行时效果，未与阶梯折扣协调")])
    # 知识驱动的真实命中（mid + 绕过/唯一折扣来源）必须算
    assert m._hit_defect5([_issue(
        desc="硬编码 0.30 无门槛折扣，绕过《折扣规范》规定的"
             "唯一折扣来源，形成第二个折扣来源")])


def test_search_failures_only_flags_failed_search_results():
    m = _load_smoke_rag()
    events = [
        {"event": "tool_result", "payload": {
            "tool": "search_knowledge", "result": "(知识库检索失败: 401 unauthorized)"}},
        {"event": "tool_result", "payload": {
            "tool": "search_knowledge", "result": "[1] discount-policy.md ..."}},
        {"event": "tool_call", "payload": {
            "tool": "search_knowledge", "args": "折扣上限"}},
    ]
    errs = m._search_failures(events)
    assert errs == ["(知识库检索失败: 401 unauthorized)"]
    assert m._search_failures(events[1:]) == []
