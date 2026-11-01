"""Memory 骨架：调用点固定 + Noop 实现。

# ponytail: NoopMemory 是刻意的空实现，别删；它是 eval A/B 的对照组基线。
后续换 Qdrant/文件实现时 engine 不用改。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypedDict

from harness.contract import AgentOutput

if TYPE_CHECKING:
    from harness.knowledge import BM25Scorer, KnowledgeBase


class Experience(TypedDict):
    kind: str          # "team_convention" | "past_review" | ...
    content: str
    source_run_id: str


@dataclass
class RecallSpec:
    node_id: str
    payload: dict
    context_id: str = ""                 # 跨 run 上下文 key（召回 past_reviews 用）
    kinds: frozenset[str] | None = None  # None = 不过滤（向后兼容 / 测试）


class MemoryStore(Protocol):
    def recall(self, spec: RecallSpec) -> list[Experience]: ...
    def record(self, trace_id: str, output: AgentOutput | None, *,
               context_id: str = "", commit: str = "") -> None: ...


class NoopMemory:
    """第一期实现：不写不读。"""

    def recall(self, spec: RecallSpec) -> list[Experience]:
        return []

    def record(self, trace_id: str, output: AgentOutput | None, *,
               context_id: str = "", commit: str = "") -> None:
        pass


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[dict[int, float]]: ...


class TfidfEmbedder:
    """char n-gram TF-IDF，纯 stdlib，batch-local IDF（召回内相对排序足够）。

    # ponytail: corpus-wide IDF 是升级路径（语料稳定后 fit 一次缓存 df）
    """

    def __init__(self, ngram: tuple[int, int] = (2, 3)) -> None:
        self.ngram = ngram

    def _tokenize(self, text: str) -> list[str]:
        s = text.lower()
        out: list[str] = []
        for n in range(self.ngram[0], self.ngram[1] + 1):
            out.extend(s[i:i + n] for i in range(len(s) - n + 1))
        return out

    def embed(self, texts: list[str]) -> list[dict[int, float]]:
        docs = [self._tokenize(t) for t in texts]
        vocab: dict[str, int] = {}
        for toks in docs:
            for t in toks:
                vocab.setdefault(t, len(vocab))
        n = len(texts)
        df: dict[int, int] = {}
        for toks in docs:
            for t in set(toks):
                df[vocab[t]] = df.get(vocab[t], 0) + 1
        vecs: list[dict[int, float]] = []
        for toks in docs:
            tf: dict[int, int] = {}
            for t in toks:
                tf[vocab[t]] = tf.get(vocab[t], 0) + 1
            raw = {tid: c * (math.log((1 + n) / (1 + df[tid])) + 1.0)
                   for tid, c in tf.items()}
            norm = math.sqrt(sum(w * w for w in raw.values())) or 1.0
            vecs.append({tid: w / norm for tid, w in raw.items()})
        return vecs


def _cosine(a: dict[int, float], b: dict[int, float]) -> float:
    # embed 已 L2 归一，dot 即 cosine
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def _rrf(score_lists: list[list[float]], k: int = 60) -> list[float]:
    """Reciprocal Rank Fusion：每条腿的分数转排名后融合（分数越高越好）。"""
    n = len(score_lists[0])
    ranks = [[0] * n for _ in score_lists]
    for lst, out in zip(score_lists, ranks, strict=True):
        for pos, j in enumerate(sorted(range(n), key=lambda j: -lst[j])):
            out[j] = pos + 1
    return [sum(1.0 / (k + ranks[i][j]) for i in range(len(score_lists)))
            for j in range(n)]


class HybridMemory:
    """真实实现：conventions（种子）+ past_reviews（record 追加），hybrid 检索。"""

    def __init__(self, runs_root: Path, conventions_path: Path, *,
                 embedder: Embedder | None = None, top_k: int = 3,
                 knowledge: KnowledgeBase | None = None,
                 scorer: BM25Scorer | None = None) -> None:
        self.runs_root = Path(runs_root)
        self.conventions_path = Path(conventions_path)
        self.experiences_path = self.runs_root / "memory" / "experiences.jsonl"
        self.embedder = embedder or TfidfEmbedder()
        self.top_k = top_k
        self.knowledge = knowledge  # 推通道知识腿（None = 无此腿，三期行为不变）
        # 语义腿打分器：非 None 用 BM25 关键词腿替换 TF-IDF 语义腿；None = 既有路径
        self.scorer = scorer

    def _load_conventions(self) -> list[dict]:
        if not self.conventions_path.exists():
            return []
        try:
            data = json.loads(self.conventions_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [c for c in data if isinstance(c, dict)]  # 损坏条目跳过（设计 §9）

    def _load_experiences(self) -> list[dict]:
        if not self.experiences_path.exists():
            return []
        out: list[dict] = []
        for line in self.experiences_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):  # 损坏行跳过（设计 §9：损坏 → 返回 []）
                out.append(parsed)
        return out

    def _candidates(self, spec: RecallSpec) -> list[dict]:
        kinds, repo = spec.kinds, spec.payload.get("repo", "")
        cands: list[dict] = []
        for conv in self._load_conventions():
            if kinds is not None and conv.get("kind") not in kinds:
                continue
            if conv.get("repo") not in (None, "", repo):
                continue
            cand = dict(conv)
            cand.setdefault("source_run_id", "")
            cand["content"] = cand.get("text", "")
            cands.append(cand)
        for exp in self._load_experiences():
            if kinds is not None and exp.get("kind") not in kinds:
                continue
            if exp.get("context_id") and spec.context_id and exp["context_id"] != spec.context_id:
                continue
            cand = dict(exp)
            cand.setdefault("source_run_id", "")
            cands.append(cand)
        if self.knowledge is not None and (kinds is None or "knowledge" in kinds):
            # 推通道（设计 §2）：payload 拼串作 query 检索知识库，命中即候选，
            # 与 conventions/experiences 同池走 exact/sem/RRF 与 per-kind 配额
            query = " ".join(str(v) for v in spec.payload.values())
            for hit in self.knowledge.search(query, top_k=self.top_k):
                cands.append({"kind": "knowledge", "content": hit["snippet"],
                              "source_run_id": "", "path": hit["path"]})
        return cands

    def _exact_scores(self, spec: RecallSpec, cands: list[dict]) -> list[float]:
        repo = spec.payload.get("repo", "")
        scores: list[float] = []
        for c in cands:
            s = 0.0
            if c.get("repo") and c.get("repo") == repo:
                s += 1.0
            for tag in c.get("tags", []):
                if tag in str(spec.payload):
                    s += 1.0
            scores.append(s)
        return scores

    def recall(self, spec: RecallSpec) -> list[Experience]:
        cands = self._candidates(spec)
        if not cands:
            return []
        exact = self._exact_scores(spec, cands)
        query = " ".join(str(v) for v in spec.payload.values())
        if self.scorer is not None:
            # BM25 关键词腿（八期）：中文词面命中比 char-ngram cosine 更锐
            sem = self.scorer.score(query, [c.get("content", "") for c in cands])
        else:
            vecs = self.embedder.embed([query] + [c.get("content", "") for c in cands])
            sem = [_cosine(vecs[0], cv) for cv in vecs[1:]]
        fused = _rrf([exact, sem])
        order = sorted(range(len(cands)), key=lambda j: -fused[j])[: self.top_k]
        # per-kind 配额：spec.kinds 内有候选却没进 top_k 的 kind，用其最高融合分
        # 候选换掉已选中同类不止一条的最低分项——约定不得靠 tie-break 运气存活
        if spec.kinds:
            for kind in sorted(spec.kinds - {cands[j]["kind"] for j in order}):
                spare = [j for j in range(len(cands))
                         if j not in order and cands[j]["kind"] == kind]
                dupes = [j for j in order
                         if sum(1 for k in order
                                if cands[k]["kind"] == cands[j]["kind"]) > 1]
                if not spare or not dupes:
                    continue
                order[order.index(min(dupes, key=lambda j: fused[j]))] = max(
                    spare, key=lambda j: fused[j])
            order.sort(key=lambda j: -fused[j])
        return [Experience(kind=c["kind"], content=c.get("content", ""),
                           source_run_id=c.get("source_run_id", ""))
                for c in (cands[j] for j in order)]

    def record(self, trace_id: str, output: AgentOutput | None, *,
               context_id: str = "", commit: str = "") -> None:
        if output is None or output.status != "ok":
            return
        issues = (output.output_data or {}).get("issues", [])
        if not issues:
            return
        if any(e.get("context_id") == context_id and e.get("commit") == commit
               for e in self._load_experiences()):
            return  # ponytail: 同 (context_id, commit) 重跑幂等；要 TTL/去重升级在此扩
        content = "; ".join(
            f"{i.get('file', '')}:{i.get('line', '')} {i.get('desc', '')}" for i in issues)
        line = {"kind": "past_review", "content": content, "source_run_id": trace_id,
                "context_id": context_id, "commit": commit}
        self.experiences_path.parent.mkdir(parents=True, exist_ok=True)
        with self.experiences_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def build_memory(runs_root: Path, *, enabled: bool,
                 conventions_path: Path | None = None,
                 knowledge: KnowledgeBase | None = None) -> MemoryStore:
    if not enabled:
        return NoopMemory()
    # 惰性 import：knowledge → memory 单向依赖（Embedder/_cosine），反向只在工厂走
    from harness.knowledge import BM25Scorer
    from harness.knowledge import KnowledgeBase as _KB

    root = Path(__file__).resolve().parent.parent
    return HybridMemory(
        runs_root, conventions_path or root / "eval" / "conventions.json",
        knowledge=knowledge if knowledge is not None else _KB(runs_root),
        scorer=BM25Scorer())
