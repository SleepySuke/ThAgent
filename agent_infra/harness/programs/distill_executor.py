"""C 层：accept 后机械蒸馏（设计 §2.1 档 1，零 LLM——引入 LLM=引入新判断=新污染源）。

从**已人审**（accept = 认可该 run 全部结论）产物机械抽取知识条目写入
`knowledge/distilled/`：一条目一文件（frontmatter provenance + 正文），
KB mtime 惰性重建自动接上（五期机制零改动接线）。幂等：目标文件已存在跳过；
产物缺失的 kind 零条目不抛（矩阵 #7 诚实降级）。同时把当轮 execution_report
快照 copy 到 `runs/<tid>/review/accepted_r{N}.json` 做产物版本锚（replan
多轮可溯，裁定 3）。

provenance 单一事实源 = trace.jsonl 的 node_start 钉桩（Task 4 model/prompt_sha
的消费闭环；program 节点如实为空串）。本模块是纯函数，可离线单测，无 LLM。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

# 默认语料目录（仓库 knowledge/distilled/；测试注入 corpus_dir 或 monkeypatch 本值）
_CORPUS_DEFAULT = (Path(__file__).resolve().parent.parent.parent
                   / "knowledge" / "distilled")

_EXEMPLAR_HEAD = 400   # exemplar 正文摘报告要点预算（字符）


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _provenance(run_dir: Path) -> dict[str, dict]:
    """trace.jsonl node_start → {agent 名: {model, prompt_sha}}（钉桩消费）。"""
    prov: dict[str, dict] = {}
    trace = run_dir / "trace.jsonl"
    if not trace.exists():
        return prov
    try:
        lines = trace.read_text(encoding="utf-8").splitlines()
    except OSError:
        return prov
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") != "node_start":
            continue
        payload = e.get("payload") or {}
        agent = payload.get("agent")
        if agent:
            prov[agent] = {"model": payload.get("model", ""),
                           "prompt_sha": payload.get("prompt_sha", "")}
    return prov


def _node_outputs(run_dir: Path) -> dict:
    cp = _read_json(run_dir / "checkpoint.json")
    if not isinstance(cp, dict):
        return {}
    out = cp.get("node_outputs")
    return out if isinstance(out, dict) else {}


def _write(corpus: Path, name: str, fm: dict, body: str) -> bool:
    """一条目一文件落盘；已存在跳过（幂等）。返回是否新写。"""
    path = corpus / name
    if path.exists():
        return False
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in fm.items()]
    lines += ["---", "", body.strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def _base_fm(kind: str, tid: str, round_: int, prov: dict) -> dict:
    return {"kind": kind, "source_run_id": tid,
            "model": prov.get("model", ""), "prompt_sha": prov.get("prompt_sha", ""),
            "round": round_, "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "active": "true", "quality": "null"}


def _executor_exit_code(node_outputs: dict):
    """case_executor 的 exit_code（唯一源）；节点缺如实 None（不通过）。"""
    for entry in node_outputs.values():
        data = entry.get("output_data") if isinstance(entry, dict) else None
        if isinstance(data, dict) and "exit_code" in data:
            return data["exit_code"]
    return None


def _root_causes(node_outputs: dict) -> list:
    for entry in node_outputs.values():
        data = entry.get("output_data") if isinstance(entry, dict) else None
        if isinstance(data, dict) and isinstance(data.get("root_causes"), list):
            return data["root_causes"]
    return []


def _distill_issues(corpus, trace_id, round_, fm, report) -> int:
    """① cr_report issues → cr-issue 条目（正文含 desc + file:line 证据）。"""
    if not isinstance(report, dict):
        return 0
    n = 0
    for i, issue in enumerate(report.get("issues") or [], start=1):
        if not isinstance(issue, dict):
            continue
        evidence = f"{issue.get('file', '')}:{issue.get('line', '')}"
        body = (f"# CR Issue #{i}\n\n{issue.get('desc', '')}\n\n"
                f"证据：{evidence}（severity={issue.get('severity', '')}, "
                f"type={issue.get('type', '')}）")
        if _write(corpus, f"cr-issue-{trace_id}-r{round_}-{i}.md",
                  fm("cr-issue", "cr_agent"), body):
            n += 1
    return n


def _distill_cases(corpus, trace_id, round_, fm, artifacts, *,
                   node_outputs) -> int:
    """② reuse 用例 + executor 通过证据 → test-case 条目（失败不沉淀，#7）。"""
    if _executor_exit_code(node_outputs) != 0:
        return 0
    cases = _read_json(artifacts / "case_list.json")
    reuse = [c for c in (cases.get("case_list") or [])
             if isinstance(c, dict) and c.get("action") == "reuse"] \
        if isinstance(cases, dict) else []
    n = 0
    for i, case in enumerate(reuse, start=1):
        body = (f"# Test Case {case.get('id', '')}\n\n"
                f"场景：{case.get('scenario', '')}\n"
                f"复用自：{case.get('src', '')}\n"
                f"关联风险：{case.get('linked_risk', '')}\n\n"
                f"执行证据：case_executor exit_code=0（本轮通过）")
        if _write(corpus, f"test-case-{trace_id}-r{round_}-{i}.md",
                  fm("test-case", "case_agent"), body):
            n += 1
    return n


def _distill_patterns(corpus, trace_id, round_, fm, node_outputs) -> int:
    """③ diagnose root_causes → pattern 条目。"""
    n = 0
    for i, rc in enumerate(_root_causes(node_outputs), start=1):
        if not isinstance(rc, dict):
            continue
        body = (f"# Pattern #{i}\n\n案例：{rc.get('case', '')}\n"
                f"根因：{rc.get('cause', '')}\n证据：{rc.get('evidence', '')}")
        if _write(corpus, f"pattern-{trace_id}-r{round_}-{i}.md",
                  fm("pattern", "diagnose_agent"), body):
            n += 1
    return n


def _distill_exemplar(corpus, trace_id, round_, fm, *, run_dir, prov) -> int:
    """产物版本锚（accepted 快照 copy，裁定 3）+ ④ exemplar 条目（快照指引）。"""
    try:
        report_md = (run_dir / "artifacts" / "execution_report.md").read_text(
            encoding="utf-8")
    except OSError:
        return 0
    snap_dir = run_dir / "review"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / f"accepted_r{round_}.json"
    if not snap.exists():
        snap.write_text(json.dumps(
            {"round": round_, "provenance": prov.get("report_agent", {}),
             "report_md": report_md}, ensure_ascii=False), encoding="utf-8")
    head = " ".join(report_md.split())[:_EXEMPLAR_HEAD]
    body = ("# 认可报告范例（质量基准非格式示范——参考组织结构，不抄内容）\n\n"
            f"要点：{head}\n\n全文见 runs/{trace_id}/review/"
            f"accepted_r{round_}.json")
    return 1 if _write(corpus, f"exemplar-{trace_id}-r{round_}-1.md",
                       fm("exemplar", "report_agent"), body) else 0


def distill(runs_root, trace_id, round_, corpus_dir=None) -> dict:
    """accept 后机械蒸馏：返回 {"entries": N, "by_kind": {...}}（零 token）。

    抽取源：cr_report.json issues → cr-issue；case_list.json reuse 条目 +
    case_executor 通过证据（exit_code==0）→ test-case；diagnose root_causes →
    pattern；report 快照指引 → exemplar。产物缺失的 kind 如实零条目不抛。
    """
    runs_root = Path(runs_root)
    run_dir = runs_root / trace_id
    corpus = Path(corpus_dir) if corpus_dir else _CORPUS_DEFAULT
    corpus.mkdir(parents=True, exist_ok=True)
    prov = _provenance(run_dir)

    def fm(kind, agent):
        return _base_fm(kind, trace_id, round_, prov.get(agent, {}))

    node_outputs = _node_outputs(run_dir)
    report = _read_json(run_dir / "artifacts" / "cr_report.json")
    by_kind: Counter[str] = Counter()
    for kind, n in (("cr-issue", _distill_issues(corpus, trace_id, round_, fm, report)),
                    ("test-case", _distill_cases(corpus, trace_id, round_, fm,
                                                 run_dir / "artifacts",
                                                 node_outputs=node_outputs)),
                    ("pattern", _distill_patterns(corpus, trace_id, round_, fm,
                                                  node_outputs)),
                    ("exemplar", _distill_exemplar(corpus, trace_id, round_, fm,
                                                   run_dir=run_dir,
                                                   prov=prov))):
        if n:
            by_kind[kind] = n
    return {"entries": sum(by_kind.values()), "by_kind": dict(by_kind)}
