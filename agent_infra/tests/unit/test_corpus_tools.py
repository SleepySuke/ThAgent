"""九期 Task 6：语料策展 CLI + 回滚生效证明（矩阵 #10/#11/#21b）。

核心断言：quarantine（active:false）后**真 KnowledgeBase 不再召回该条目**——
回滚生效的机制证明（mtime 变更触发重索引 + 索引跳过 inactive）；use_count 走
旁路 counts.json，md mtime 不变（内容/信号分离，不触发 re-embed）。
"""
import importlib.util
import json
from pathlib import Path


def _load_tools():
    p = Path(__file__).resolve().parents[2] / "scripts" / "corpus_tools.py"
    spec = importlib.util.spec_from_file_location("corpus_tools", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EXEMPLAR = """---
kind: exemplar
source_run_id: t1
model: zai/glm-4.6
prompt_sha: abc123def456
round: 1
reviewed_at: 2026-10-29T16:00:00
active: true
quality: null
---

# 认可报告范例

执行报告要点：新增 50 档折扣与用例库 TC-002 契约冲突，需同步。
见 runs/t1/review/accepted_r1.json
"""

OTHER = """---
kind: pattern
source_run_id: t0
model: zai/glm-4.6
prompt_sha: abc123def456
round: 1
reviewed_at: 2026-10-29T16:00:00
active: true
quality: null
---

# 模式

断言漂移与阶梯契约冲突时先同步用例库。
"""


def _corpus(tmp_path):
    corpus = tmp_path / "knowledge"
    (corpus / "distilled").mkdir(parents=True)
    (corpus / "distilled" / "exemplar-t1-1.md").write_text(EXEMPLAR,
                                                           encoding="utf-8")
    (corpus / "distilled" / "pattern-t0-1.md").write_text(OTHER,
                                                        encoding="utf-8")
    return corpus


def _kb(tmp_path, corpus):
    from harness.knowledge import KnowledgeBase
    from harness.memory import TfidfEmbedder
    return KnowledgeBase(tmp_path / "runs", corpus, embedder=TfidfEmbedder())


def test_quarantine_flips_active_and_kb_drops_entry(tmp_path):
    """矩阵 #10 核心：隔离后 KB search 不再召回（回滚生效证明）。"""
    tools = _load_tools()
    corpus = _corpus(tmp_path)
    target = corpus / "distilled" / "exemplar-t1-1.md"

    kb = _kb(tmp_path, corpus)
    hits = kb.search("认可报告范例")
    assert any(h["path"] == "distilled/exemplar-t1-1.md" for h in hits)

    assert tools.quarantine(target) is True
    assert tools.read_frontmatter(target)["active"] == "false"
    # 内容不动，只翻标志
    assert "认可报告范例" in target.read_text(encoding="utf-8")
    # 新实例（模拟重启/惰性重建）：mtime 漂移触发重索引，inactive 不入索引
    hits = _kb(tmp_path, corpus).search("认可报告范例")
    assert not any(h["path"] == "distilled/exemplar-t1-1.md" for h in hits)
    # 其它条目不受牵连
    assert any(h["path"] == "distilled/pattern-t0-1.md"
               for h in _kb(tmp_path, corpus).search("阶梯契约冲突 同步用例库"))


def test_restore_revives_entry(tmp_path):
    tools = _load_tools()
    corpus = _corpus(tmp_path)
    target = corpus / "distilled" / "exemplar-t1-1.md"
    tools.quarantine(target)
    assert tools.restore(target) is True
    assert tools.read_frontmatter(target)["active"] == "true"
    hits = _kb(tmp_path, corpus).search("认可报告范例")
    assert any(h["path"] == "distilled/exemplar-t1-1.md" for h in hits)


def test_quarantine_missing_file_raises_clean(tmp_path):
    tools = _load_tools()
    assert tools.quarantine(tmp_path / "nope.md") is False


def test_list_by_run(tmp_path):
    """矩阵 #11：run 级溯源——列出该 run 贡献的全部条目。"""
    tools = _load_tools()
    corpus = _corpus(tmp_path)
    (corpus / "distilled" / "cr-issue-t1-1.md").write_text(
        EXEMPLAR.replace("kind: exemplar", "kind: cr-issue"), encoding="utf-8")
    entries = tools.list_run(corpus, "t1")
    assert sorted(e["file"] for e in entries) == [
        "distilled/cr-issue-t1-1.md", "distilled/exemplar-t1-1.md"]
    assert all(e["source_run_id"] == "t1" for e in entries)
    assert tools.list_run(corpus, "no-such-run") == []


def test_stats_counts(tmp_path):
    tools = _load_tools()
    corpus = _corpus(tmp_path)
    tools.quarantine(corpus / "distilled" / "exemplar-t1-1.md")
    (corpus / "distilled" / ".counts.json").write_text(json.dumps(
        {"distilled/exemplar-t1-1.md": {"use": 3}}), encoding="utf-8")
    # 生产形态：stats 传 distilled/ 目录（main() 的 CORPUS_DIR）——counts
    # 就在语料根（t6-rev Important：旧实现双重嵌套恒读空，测试同错互证）
    st = tools.stats(corpus / "distilled")
    assert st["by_kind"]["exemplar"] == 1
    assert st["by_kind"]["pattern"] == 1
    assert st["active"] == 1 and st["inactive"] == 1
    assert st["use_total"] == 3


async def test_use_count_bypass_md_mtime_unchanged(tmp_path, monkeypatch):
    """矩阵 #21b：search_knowledge 命中 distilled 条目 → counts.json +1，
    md 文件 mtime 不变（不写回 md = 不触发重索引）。"""
    from harness.contract import RunContext
    from harness.tools import knowledge as tk

    corpus = _corpus(tmp_path)
    monkeypatch.setattr(tk, "_KB", _kb(tmp_path, corpus))
    target = corpus / "distilled" / "exemplar-t1-1.md"
    mtime_before = target.stat().st_mtime

    tool = tk.search_knowledge(
        RunContext(trace_id="t", repo_path="x", commit="d"), None)
    out = await tool("认可报告范例")
    assert "exemplar-t1-1.md" in out

    counts = json.loads(
        (corpus / "distilled" / ".counts.json").read_text(encoding="utf-8"))
    assert counts["distilled/exemplar-t1-1.md"]["use"] == 1
    assert target.stat().st_mtime == mtime_before   # 旁路计数不碰 md
