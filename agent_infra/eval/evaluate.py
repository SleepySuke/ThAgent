"""V 层：CR 输出 vs golden 对答案。"""
from __future__ import annotations

import json
from pathlib import Path

LINE_TOLERANCE = 6
GOLDEN_PATH = Path(__file__).parent / "golden.json"


def load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def match_issue(g: dict, a: dict) -> bool:
    """命中 = 找对了地方（file + 行号容差）。type 不做硬条件：type 是分类
    口径（bug/consistency/maintainability 的边界因模型而异），位置命中而
    type 不符说明"审对了、分类口径不同"，计 miss 会低估命中率。
    alt_files：golden issue 可列替代锚点文件（如把测试未同步报到测试文件）。
    替代锚点是 file 级匹配——它的行号与主锚点不同轴（测试文件里的旧断言
    vs 实现文件的改动行），共享行号会把审对的报成 miss；行号容差只对主
    锚点生效。
    # ponytail: 容差 6 覆盖"函数头 vs 逻辑行"的定位差；desc 语义匹配是升级路径
    """
    if a.get("file") == g["file"]:
        return abs(g["line"] - a.get("line", -10**9)) <= LINE_TOLERANCE
    return a.get("file") in g.get("alt_files", [])


def evaluate_commit(golden: dict, actual: dict) -> dict:
    actual_issues = actual.get("issues", [])
    hits, matched = 0, []
    for g in golden.get("issues", []):
        hit = next((a for a in actual_issues
                    if match_issue(g, a) and id(a) not in matched), None)
        if hit is not None:
            hits += 1
            matched.append(id(hit))
    false_positives = [a for a in actual_issues if id(a) not in matched]
    return {"hits": hits, "misses": len(golden.get("issues", [])) - hits,
            "false_positives": false_positives,
            "verdict_ok": actual.get("verdict") == golden.get("verdict")}


def evaluate_report(golden_all: dict, reports: dict[str, dict]) -> dict:
    per_commit, hit_sum, miss_sum, fp_sum, ok_sum = {}, 0, 0, 0, 0
    for tag, golden in golden_all.items():
        r = evaluate_commit(golden, reports.get(tag, {}))
        per_commit[tag] = r
        hit_sum += r["hits"]
        miss_sum += r["misses"]
        fp_sum += len(r["false_positives"])
        ok_sum += int(r["verdict_ok"])
    total = hit_sum + miss_sum
    return {"per_commit": per_commit,
            "total_hit_rate": hit_sum / total if total else 0.0,
            "total_false_positives": fp_sum,
            "verdict_accuracy": ok_sum / len(golden_all) if golden_all else 0.0}
