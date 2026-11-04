"""V 层：报告质量打分器（设计 §2.2 三件套的打分段）。

两消费面分离（裁定 A）：engine 手动 accept 路径把分挂进 review_accepted
事件 payload（人工在环，烧 1 次 judge 可接受）；REVIEW_AUTO / benchmark 走
hard-only（complete=None，不烧 judge token）。

维度：
- evidence（硬，零 LLM）：cr issues 的 file 在 `git show <commit>:<file>` 存在
  且 line 在文件行数内 → 命中比例；file 缺/line 越界记 0 分条目。确定性，
  进 benchmark 漂移门禁（裁定 B：门禁只挂硬维度，judge 方差不进回归判据）。
- coverage/consistency/readability（软，judge LLM 按 rubric）：记录不门禁。

回音室防线①进 prompt 文本：rubric 只度量绝对质量维度，不度量与任何范例的
相似度（相似度分数会随飞轮自涨，真实质量反跌）。

backfill_quality：exemplar 条目 quality 回填（null→值是一次性慢变更，写回
触发 KB 重索引可接受）；低于 EXEMPLAR_MIN_QUALITY 置 active:false——只翻
标志永不删文件（审计保留）。
"""
from __future__ import annotations

import contextlib
import json
import subprocess
from pathlib import Path

# 换 judge prompt 版本 = 基线重建申报，不许静默换（坑 #24 同款自盲钉桩）
JUDGE_VERSION = "q1"

# exemplar 准入阈值：hard-only total（evidence 比例）≥0.6 才可教下一代。
# 依据：单 issue 报告 1/2 命中即 0.5 不及格、全命中 1.0——0.6 挡住「一半证据
# 编造」的报告，全对与单点小错都放行。可调：回填后看 corpus 分布再校准。
EXEMPLAR_MIN_QUALITY = 0.6

_RUBRIC_PROMPT = """你是代码审查执行报告的质量评审。**只度量报告的绝对质量维度**，
不得度量它与任何范例、模板或其他报告的相似度（相似不是质量）。

按以下三个维度打分，各 0.0-1.0：
- coverage：报告是否覆盖了执行面全部关键结论（通过率、失败用例、根因、风险），
  有无遗漏明显应报告的信息。
- consistency：报告内部以及与上游结论（CR issues、用例结果）是否自洽，
  数字与结论无矛盾。
- readability：结构清晰、结论先行、表述准确不含糊。

只输出 JSON，不要解释：{"coverage": x, "consistency": y, "readability": z}

报告内容：
{report}"""


def _git_line_count(repo: str, commit: str, file: str) -> int | None:
    """commit 里该文件的行数；文件不存在 / git 失败 → None（0 分条目）。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "show", f"{commit}:{file}"],
            capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.count(b"\n") + (0 if r.stdout.endswith(b"\n") or not r.stdout
                                    else 1)


def score_evidence(issues, repo, commit) -> float:
    """硬维度（纯机械零 LLM）：file:line 可在 commit 产物中落实的比例。

    空 issues 如实 0 分（无可验证证据，不送 1.0 满分）。"""
    issues = [i for i in (issues or []) if isinstance(i, dict)]
    if not issues:
        return 0.0
    hits = 0
    for i in issues:
        n = _git_line_count(repo, commit, str(i.get("file", "")))
        try:
            line = int(i.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        if n is not None and 1 <= line <= n:
            hits += 1
    return round(hits / len(issues), 4)


def _parse_scores(text: str) -> dict:
    """judge 输出 → 三软维度；缺键/解析失败如实 None（记录面不猜）。"""
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}
    out = {}
    for k in ("coverage", "consistency", "readability"):
        v = data.get(k)
        out[k] = round(min(max(float(v), 0.0), 1.0), 4) \
            if isinstance(v, (int, float)) else None
    return out


def _llm_complete(prompt: str) -> str:
    """默认 judge 通道（litellm）；测试/离线注入 fake 替代。"""
    import litellm

    from harness.config import resolve_model
    r = litellm.completion(model=resolve_model("judge", ""), max_tokens=512,
                           temperature=0.0,
                           messages=[{"role": "user", "content": prompt}])
    return r.choices[0].message.content or ""


def score_report(report, repo, commit, *, complete=None) -> dict:
    """rubric 分维打分：{"evidence", "coverage", "consistency", "readability",
    "total", "judge_version"}。

    complete=None（hard-only，benchmark/无人值守默认）：软维度 None，total 只
    计硬维度——评测不烧 judge token（裁定 A/B）。注入 complete 时 total 为四维
    均值（软维度等权，judge 主观维度不加权的克制面）。"""
    report = report if isinstance(report, dict) else {}
    evidence = score_evidence(report.get("issues") or [], repo, commit)
    if complete is None:
        coverage = consistency = readability = None
    else:
        # replace 而非 format：rubric 里的输出示例 JSON 花括号会被 format 吃掉
        prompt = _RUBRIC_PROMPT.replace(
            "{report}", json.dumps(report, ensure_ascii=False))
        scores = _parse_scores(complete(prompt))
        coverage = scores.get("coverage")
        consistency = scores.get("consistency")
        readability = scores.get("readability")
    dims = [evidence, coverage, consistency, readability]
    total = round(sum(d for d in dims if d is not None)
                  / max(sum(1 for d in dims if d is not None), 1), 4)
    return {"evidence": evidence, "coverage": coverage,
            "consistency": consistency, "readability": readability,
            "total": total, "judge_version": JUDGE_VERSION}


def _frontmatter(path: Path) -> dict[str, str]:
    """手解析 frontmatter（与 distill/corpus_tools 同款零依赖约定）。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        k, _, v = line.partition(":")
        if v.strip():
            out[k.strip()] = v.strip()
    return out


def _rewrite_fm(path: Path, updates: dict[str, str]) -> None:
    """改 frontmatter 指定键；缺失的键插到 frontmatter 尾（t8-rev Minor：
    只改不插会让手写条目静默丢更新却计数 backfilled——伪幂等）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    end = next(i for i, line in enumerate(lines[1:], 1)
               if line.strip() == "---")
    seen: set[str] = set()
    for i in range(1, end):
        key = lines[i].partition(":")[0].strip()
        if key in updates:
            lines[i] = f"{key}: {updates[key]}"
            seen.add(key)
    for key in [k for k in updates if k not in seen]:
        lines.insert(end, f"{key}: {updates[key]}")
        end += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def backfill_quality(corpus_dir, runs_root, repo, *, scorer=None) -> dict:
    """exemplar 条目 quality 回填（幂等：已有 quality 跳过）。

    打分源：source_run_id 对应 run 的 cr_report.json + trace run_start 的
    commit（repo 由调用方给——本期 fixture 单仓，多仓时升级为 repo_by_run 映射）。
    低于 EXEMPLAR_MIN_QUALITY 置 active:false（只翻标志不删文件，审计保留；
    active 写回触发 mtime 重索引，KB 自动不再召回——回滚生效机制，矩阵 #10）。
    """
    corpus = Path(corpus_dir)
    runs = Path(runs_root)
    scorer = scorer or score_report
    out = {"backfilled": 0, "gated": 0}
    for path in sorted(corpus.glob("*.md")):
        fm = _frontmatter(path)
        if fm.get("kind") != "exemplar" or fm.get("quality", "null") != "null":
            continue   # 幂等：已回填/非 exemplar 跳过
        tid = fm.get("source_run_id", "")
        report_path = runs / tid / "artifacts" / "cr_report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue   # 快照缺失：留待下次（不猜不弃）
        commit = ""   # trace 缺失时空 commit：evidence 按实 0 分——若低于
                     # 阈值会被隔离（快照缺失本身说明 run 不完整，接受该
                     # 面而非「不挡回填」——t8-rev Minor #3 如实化）
        trace = runs / tid / "trace.jsonl"
        if trace.exists():
            with contextlib.suppress(json.JSONDecodeError, StopIteration):
                commit = next(
                    e.get("payload", {}).get("commit", "")
                    for e in (json.loads(line) for line in
                              trace.read_text(encoding="utf-8").splitlines())
                    if e.get("event") == "run_start")
        total = scorer(report, repo, commit).get("total")
        if total is None:
            continue
        updates = {"quality": f"{round(float(total), 4)}"}
        if float(total) < EXEMPLAR_MIN_QUALITY and \
                fm.get("active", "true") != "false":
            updates["active"] = "false"
            out["gated"] += 1
        _rewrite_fm(path, updates)
        out["backfilled"] += 1
    return out
