"""语料策展 CLI（九期设计 §2.3：回滚的操作面）。零依赖（纯 stdlib，无 LLM）。

用法：
    python scripts/corpus_tools.py list --run <trace_id>
    python scripts/corpus_tools.py quarantine <file>   # active: true→false（只翻标志不改内容）
    python scripts/corpus_tools.py restore <file>      # active: false→true
    python scripts/corpus_tools.py stats               # kind/active 计数 + use 旁路汇总

回滚语义：quarantine 只改 frontmatter 的 active 标志——mtime 变更触发 KB 重
索引、重索引跳过 inactive 条目（矩阵 #10 回滚生效机制）；不删文件保留审计痕。
run 级溯源：list --run 按 frontmatter source_run_id 列条目（矩阵 #11），支持
批量隔离。use 信号在旁路 counts.json（内容/信号分离，写回 md 会触发 re-embed）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "distilled"
COUNTS_PATH = CORPUS_DIR / ".counts.json"   # use 旁路计数（内容/信号分离）


def read_frontmatter(path: Path) -> dict[str, str]:
    """手解析 frontmatter（与 distill 同款零依赖约定：--- 包裹 + k: v）。"""
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


def _set_active(path: Path, value: str) -> bool:
    """翻 frontmatter 的 active 标志（只改这一行，其余字节不动）。文件缺失或
    无 frontmatter → False（调用方如实报告）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    end = next((i for i, line in enumerate(lines[1:], 1)
                if line.strip() == "---"), None)
    if end is None:
        return False
    changed = False
    for i in range(1, end):
        key, _, val = lines[i].partition(":")
        if key.strip() == "active" and val.strip() != value:
            lines[i] = f"active: {value}"
            changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def quarantine(path: Path) -> bool:
    """隔离条目：active: true→false（已是 false 也触发 mtime 变更→重索引）。"""
    return _set_active(Path(path), "false")


def restore(path: Path) -> bool:
    """复活条目：active: false→true。"""
    return _set_active(Path(path), "true")


def list_run(corpus: Path, run_id: str) -> list[dict]:
    """run 级溯源（矩阵 #11）：按 source_run_id 列出该 run 贡献的全部条目。"""
    out = []
    for p in sorted(Path(corpus).rglob("*.md")):
        fm = read_frontmatter(p)
        if fm.get("source_run_id") == run_id:
            out.append({"file": p.relative_to(corpus).as_posix(), **fm})
    return out


def stats(corpus: Path) -> dict:
    """kind/active 计数 + use 旁路汇总（飞轮健康度原料，§2.3 看板消费）。"""
    corpus = Path(corpus)
    by_kind: dict[str, int] = {}
    active = inactive = 0
    for p in corpus.rglob("*.md"):
        fm = read_frontmatter(p)
        kind = fm.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if fm.get("active", "true") == "false":
            inactive += 1
        else:
            active += 1
    try:
        # counts 在语料根（写方 _bump_use 的路径）；corpus 参数即 distilled/
        # 本身——旧实现拼成 distilled/distilled/ 双重嵌套恒读空（t6-rev Important）
        counts = json.loads((Path(corpus) / ".counts.json").read_text(
            encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        counts = {}
    use_total = sum(int(v.get("use", 0)) for v in counts.values()
                    if isinstance(v, dict))
    return {"total": active + inactive, "by_kind": by_kind,
            "active": active, "inactive": inactive, "use_total": use_total}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="knowledge/distilled 语料策展")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="按 run 溯源列条目")
    p_list.add_argument("--run", required=True, help="source_run_id (trace_id)")
    p_q = sub.add_parser("quarantine", help="隔离条目（active:false）")
    p_q.add_argument("file")
    p_r = sub.add_parser("restore", help="复活条目（active:true）")
    p_r.add_argument("file")
    sub.add_parser("stats", help="kind/active/use 计数")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for e in list_run(CORPUS_DIR, args.run):
            print(f"{e['file']}\tkind={e.get('kind', '')}\tactive={e.get('active', '')}"
                  f"\tmodel={e.get('model', '')}\tsha={e.get('prompt_sha', '')}")
    elif args.cmd == "quarantine":
        if not quarantine(args.file):
            print(f"quarantine 失败（文件缺失或无 frontmatter）：{args.file}")
            return 1
        print(f"quarantined: {args.file}")
    elif args.cmd == "restore":
        if not restore(args.file):
            print(f"restore 失败（文件缺失或无 frontmatter）：{args.file}")
            return 1
        print(f"restored: {args.file}")
    else:
        st = stats(CORPUS_DIR)
        print(f"total={st['total']} active={st['active']} "
              f"inactive={st['inactive']} use_total={st['use_total']}")
        for kind, n in sorted(st["by_kind"].items()):
            print(f"  {kind}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
