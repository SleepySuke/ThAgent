"""V 层：检索 Benchmark——golden 查询 × KnowledgeBase，hit@1/@3 + MRR 门禁。

纯检索不烧生成 LLM；embedding 走 sha256 缓存（首跑建索引后重复查询零 API），
无 API key 时 KnowledgeBase 自动降级 Tfidf（CI 可离线高频跑）。should-miss
（无对应文档的查询）按 score 阈值判正确拒绝，计入准确率分母（矩阵 #11）。
门禁基线以 tfidf 降级模式为准（语义 embedding 模式跑通后另行校准阈值——
miss_threshold 0.45 按 tfidf 分数分布校准）。
掉点 exit 1（CI 门禁）；阈值命令行可覆盖（首跑校准后固化进 DEFAULTS）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import runs_root  # noqa: E402
from harness.knowledge import KnowledgeBase  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "retrieval_golden.json"
DEFAULTS = {"hit1": 0.75, "hit3": 0.90, "mrr": 0.80, "miss_threshold": 0.45}


def load_retrieval_golden(path: Path | None = None) -> list[dict]:
    return json.loads((path or GOLDEN_PATH).read_text(encoding="utf-8"))


def score_query(item: dict, hits: list[dict], miss_threshold: float) -> dict:
    """单查询打分：hit@1/@3 与 RR（should-miss 则判正确拒绝）。"""
    paths = [h["path"] for h in hits]
    if item.get("expect") is None:  # should-miss：top1 分数低于阈值才算对
        ok = (not hits) or hits[0]["score"] < miss_threshold
        return {"query": item["query"], "expect": None, "paths": paths,
                "hit1": False, "hit3": False, "rr": 0.0, "miss_ok": ok}
    rank = paths.index(item["expect"]) + 1 if item["expect"] in paths else 0
    return {"query": item["query"], "expect": item["expect"], "paths": paths,
            "hit1": rank == 1, "hit3": 1 <= rank <= 3,
            "rr": 1.0 / rank if rank else 0.0, "miss_ok": True}


def score_all(golden: list[dict], results: list[list[dict]],
              miss_threshold: float) -> dict:
    """聚合：hit@k/MRR 只在 should-hit 上平均；accuracy 全量（含正确拒绝）。"""
    rows = [score_query(g, r, miss_threshold)
            for g, r in zip(golden, results, strict=True)]
    hits = [r for r in rows if r["expect"] is not None]
    n_hit, n_all = len(hits), len(rows)
    correct = (sum(r["hit1"] for r in hits)
               + sum(r["miss_ok"] for r in rows if r["expect"] is None))
    return {"rows": rows,
            "hit1": sum(r["hit1"] for r in hits) / n_hit if n_hit else 0.0,
            "hit3": sum(r["hit3"] for r in hits) / n_hit if n_hit else 0.0,
            "mrr": sum(r["rr"] for r in hits) / n_hit if n_hit else 0.0,
            "accuracy": correct / n_all if n_all else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser(description="检索 Benchmark：hit@1/@3 + MRR 门禁")
    ap.add_argument("--hit1", type=float, default=DEFAULTS["hit1"])
    ap.add_argument("--hit3", type=float, default=DEFAULTS["hit3"])
    ap.add_argument("--mrr", type=float, default=DEFAULTS["mrr"])
    ap.add_argument("--miss-threshold", type=float,
                    default=DEFAULTS["miss_threshold"])
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--golden", type=Path, default=None)
    args = ap.parse_args()

    if not (ROOT / "knowledge").exists():
        sys.exit(f"知识语料缺失: {ROOT / 'knowledge'}（先落 knowledge/*.md）")
    golden = load_retrieval_golden(args.golden)
    kb = KnowledgeBase(runs_root())
    try:
        # 防线②语义面（t8-rev Important）：评测锚点是手写语料——distilled/
        # 飞轮条目挤进 top-k 会把 expect 顶出 rank（实测 20 条已挤掉 4/35
        # 的 rank1）。打分前过滤 distilled 命中，golden 不动，锚点回到外部。
        # 挤位检测本身归飞轮健康度看板（预研 §十），不在此门禁。
        results = [
            [h for h in kb.search(g["query"], top_k=args.topk)
             if not str(h.get("path", "")).startswith("distilled/")]
            for g in golden]
    except Exception as e:  # embedding/索引构建失败：响亮退出，绝不静默 0 分
        root = e
        while root.__cause__ is not None:  # 打到异常链末端（API 报的真实原因）
            root = root.__cause__
        print(f"检索索引构建/嵌入失败: {root}")
        print("提示：无 key 可 `env -u ZAI_API_KEY uv run python eval/retrieval.py` "
              "重跑为 Tfidf 降级模式")
        sys.exit(1)
    m = score_all(golden, results, args.miss_threshold)
    for r in m["rows"]:
        good = r["hit1"] or (r["expect"] is None and r["miss_ok"])
        print(f"{'ok  ' if good else 'miss'} {r['query']} -> {r['paths']}")
    # 与 scripts/knowledge_index.py 同款取法：embedder 的 model（tfidf 降级即
    # "tfidf"），与索引头 model 字段一致（不一致会被 _fresh 强制重建对齐）
    model = getattr(kb.embedder, "model", "tfidf")
    print(f"\nmodel={model} hit@1={m['hit1']:.2f} hit@3={m['hit3']:.2f} "
          f"mrr={m['mrr']:.2f} "
          f"accuracy={m['accuracy']:.2f} "
          f"(阈值 hit1>={args.hit1} hit3>={args.hit3} mrr>={args.mrr})")
    fails = []
    if m["hit1"] < args.hit1:
        fails.append(f"hit@1={m['hit1']:.2f} < {args.hit1}")
    if m["hit3"] < args.hit3:
        fails.append(f"hit@3={m['hit3']:.2f} < {args.hit3}")
    if m["mrr"] < args.mrr:
        fails.append(f"mrr={m['mrr']:.2f} < {args.mrr}")
    if fails:
        print("检索门禁未过:", "; ".join(fails))
        sys.exit(1)
    print("检索门禁通过")


if __name__ == "__main__":
    main()
