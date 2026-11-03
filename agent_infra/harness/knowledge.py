"""C 层：知识层——团队文档 chunk → embed → JSON 向量库 → cosine 检索。

推通道：HybridMemory 并入 kind="knowledge" 候选（recall 注入，走既有 memory
kinds 门控）；拉通道：search_knowledge 工具（function calling 运行时检索）。
索引惰性重建：源 mtime 变更 / 索引损坏 / 模型或维度变更 → 整体重建
（embedding 磁盘缓存命中部分零 API 调用）；写盘 tmp+rename 原子替换。

# ponytail: JSON cosine 在 <1k chunk 规模毫秒级；>10k chunk 换 faiss，接口不变
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness.memory import Embedder, TfidfEmbedder, _cosine, _rrf

CHUNK_SIZE = 500      # 滑窗字符数（中文 demo 文档，字符窗实现 10 行）
CHUNK_OVERLAP = 50    # 窗口重叠

# provider 前缀 → API key env（缺 key 即降级，矩阵 #2）；新 provider 在此登记
_API_KEY_ENV = {"zai": "ZAI_API_KEY", "openai": "OPENAI_API_KEY",
                "dashscope": "DASHSCOPE_API_KEY"}


def embedding_model() -> str:
    """嵌入模型解析：AGENT_INFRA_EMBEDDING_MODEL > 默认值。

    默认走 openai 兼容路由 + ZAI_API_BASE 显式指定（litellm 的 zai provider
    未映射 embeddings 端点——实测 Unmapped provider；模型名是 embedding-3，
    非 glm-embedding-3）。注意：coding-plan key 对 embeddings 报 1113 资源包
    不足——有额度时语义路径即生效，无额度自动降级 Tfidf。
    """
    return os.environ.get("AGENT_INFRA_EMBEDDING_MODEL", "openai/embedding-3")


def build_embedder(cache_path: Path | None = None) -> Embedder:
    """key 在 → LiteLlmEmbedder；缺 → TfidfEmbedder 降级（可用性>纯度，矩阵 #2）。"""
    model = embedding_model()
    key_env = _API_KEY_ENV.get(model.split("/")[0], "")
    # openai 兼容路由 + ZAI_API_BASE 显式指向时，key 读 ZAI_API_KEY（见 _embed_async）
    if model.startswith("openai/") and os.environ.get("ZAI_API_BASE"):
        key_env = "ZAI_API_KEY"
    if key_env and os.environ.get(key_env):
        return LiteLlmEmbedder(model, cache_path)
    # 降级必须显性（脚本/CI 一眼可见，非静默质量受限）；与 scripts/ 的 print 习惯一致
    print(f"[knowledge] embedding key 缺失/不可用（{model}），"
          "降级 TfidfEmbedder（检索质量受限）")
    return TfidfEmbedder()


class LiteLlmEmbedder:
    """litellm aembedding + sha256 文本缓存（重复索引/重复查询零 API 调用）。

    Embedder 协议是同步的（recall/search 链路同步调用）；aembedding 在单飞
    线程的裸 loop 里驱动——engine 在主 loop 内同步调 recall，主 loop 不能再
    asyncio.run。
    """

    def __init__(self, model: str, cache_path: Path | None = None, *,
                 aembedding=None, retries: int = 2, backoff_s: float = 0.5) -> None:
        self.model = model
        self.dim: int | None = None  # 首次成功嵌入后记录（索引头校验用，矩阵 #12）
        self.cache_path = Path(cache_path) if cache_path else None
        self.retries = retries
        self.backoff_s = backoff_s
        self._aembedding = aembedding  # 测试注入；默认惰性取 litellm
        self._cache: dict[str, list[float]] | None = None

    def _load_cache(self) -> dict[str, list[float]]:
        if self._cache is None:
            self._cache = {}
            if self.cache_path and self.cache_path.exists():
                # 缓存损坏/形状不对当全量 miss：重嵌幂等（与索引 #3 同款策略）
                with contextlib.suppress(json.JSONDecodeError, OSError):
                    loaded = json.loads(
                        self.cache_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        self._cache = loaded
        return self._cache

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._cache), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except OSError:
            pass  # 只读缓存目录（矩阵 #6）：本轮放弃持久化，功能不中断

    def embed(self, texts: list[str]) -> list[dict[int, float]]:
        cache = self._load_cache()
        # 键带 model 盐：换 embedding 模型后旧缓存向量天然全量 miss（矩阵 #12
        # 不只重建索引，还必须重嵌——否则索引换壳、向量仍是旧模型的）
        keys = [hashlib.sha256(
                    f"{self.model}\x00{t}".encode()).hexdigest()
                for t in texts]
        miss = [i for i, k in enumerate(keys) if k not in cache]
        if miss:
            for i, vec in zip(miss, self._embed_sync(
                    [texts[i] for i in miss]), strict=True):
                cache[keys[i]] = vec
            self._save_cache()
        out = [dict(enumerate(cache[k])) for k in keys]
        if out:
            self.dim = len(out[0])
        return out

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self._embed_async(texts)).result()

    async def _embed_async(self, texts: list[str]) -> list[list[float]]:
        aembedding = self._aembedding
        if aembedding is None:
            import litellm

            aembedding = litellm.aembedding
        last: Exception | None = None
        kwargs: dict = {"model": self.model, "input": texts}
        # openai 兼容路由需要显式 base_url/key，否则会打到真 OpenAI（坑 #4 同族）
        if self.model.startswith("openai/") and os.environ.get("ZAI_API_BASE"):
            kwargs.update(base_url=os.environ["ZAI_API_BASE"],
                          api_key=os.environ.get("ZAI_API_KEY", ""))
        for attempt in range(self.retries + 1):  # 重试 2 次后抛（矩阵 #1）
            try:
                # 单次调用 30s 上限：openai 兼容路由在端点异常时会挂到 SDK 默认
                # 长超时，把拉通道工具拖死——快速失败让降级/错误文本尽快落地
                resp = await asyncio.wait_for(aembedding(**kwargs), timeout=30.0)
                return [self._normalize(d["embedding"]) for d in resp["data"]]
            except Exception as e:
                last = e
                await asyncio.sleep(self.backoff_s * (attempt + 1))
        raise RuntimeError(
            f"embedding failed after {self.retries + 1} attempts") from last

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        # L2 归一（与 TfidfEmbedder 同契约：dot 即 cosine）
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def chunk_text(text: str) -> list[dict]:
    """滑窗 chunk：500 字窗口 / 50 重叠；每窗携带其起点前最近的 Markdown 标题。"""
    out: list[dict] = []
    n = len(text)
    step = CHUNK_SIZE - CHUNK_OVERLAP
    start = 0
    while start < n:
        out.append({"title": _title_before(text, start),
                    "text": text[start:start + CHUNK_SIZE]})
        if start + CHUNK_SIZE >= n:
            break
        start += step
    return out


def _title_before(text: str, pos: int) -> str:
    """pos 之前最近的一个 # 标题行（窗口语义归属；首窗标题在正文内，返回空）。"""
    for line in reversed(text[:pos].splitlines()):
        if line.startswith("#"):
            return line.lstrip("# ").strip()
    return ""


def _embed_input(chunk: dict) -> str:
    # 嵌入文本 = 标题 + 正文（标题先行，命中带章节语义）
    return f"{chunk['title']}\n{chunk['text']}" if chunk["title"] else chunk["text"]


def _vec_from_json(d: dict) -> dict[int, float]:
    # JSON 落盘把 int key 变 str key；cosine 按 int key 查，载入时转回
    return {int(k): v for k, v in d.items()}


def _model_of(embedder: Embedder) -> str:
    return getattr(embedder, "model", "tfidf")


def _dim_of(embedder: Embedder) -> int | None:
    # dim 仅 LiteLlmEmbedder 首次成功嵌入后才有；Tfidf/测试替身没有 → None
    return getattr(embedder, "dim", None)


def _snippet(chunk: dict) -> str:
    text = " ".join(chunk["text"].split())
    head = f"{chunk['title']}\n" if chunk["title"] else ""
    return head + text[:160]


def _entry_active(path: Path) -> bool:
    """语料条目 frontmatter `active` 标志（九期蒸馏条目回滚协议，矩阵 #10）。

    只认 `active: false` 为隔离（缺 frontmatter/缺键默认 active）；手解析
    零依赖：首个 `---` 与下一个 `---` 之间的 `k: v` 行。读取失败视为隔离
    （读不出的条目不进索引，宁可漏召回不召回坏内容）。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    if not lines or lines[0].strip() != "---":
        return True
    for line in lines[1:]:
        if line.strip() == "---":
            break
        k, _, v = line.partition(":")
        if k.strip() == "active":
            return v.strip() != "false"
    return True


class BM25Scorer:
    """BM25 打分（k1=1.5 b=0.75，char bigram 分词适配中文，纯 stdlib）。

    ngram 默认 (2, 2)：bigram 词面区分度刚好；带 3-gram 会放大长文档的词法
    质量，eval-retrieval 旧 30 查询 hit@1 掉 1 条（本库实测，矩阵 #15）。

    # ponytail: 语料 <1k chunk 全量现算毫秒级；更大规模再谈增量索引
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75,
                 ngram: tuple[int, int] = (2, 2)) -> None:
        self.k1 = k1
        self.b = b
        self.ngram = ngram

    def _tokenize(self, text: str) -> list[str]:
        s = text.lower()
        out: list[str] = []
        for n in range(self.ngram[0], self.ngram[1] + 1):
            out.extend(s[i:i + n] for i in range(len(s) - n + 1))
        return out

    def score(self, query: str, docs: list[str]) -> list[float]:
        """query 对每条 doc 的 BM25 分。

        IDF 用 BM25+ 平滑 ln((N-df+0.5)/(df+0.5)+1) 恒正；tf 饱和项
        f*(k1+1)/(f+k1*(1-b+b*dl/avgdl))；空 docs 返回 []，空 query 全 0。
        """
        if not docs:
            return []
        if not (query or "").strip():
            return [0.0] * len(docs)
        q_toks = Counter(self._tokenize(query))
        d_toks = [Counter(self._tokenize(d)) for d in docs]
        n = len(docs)
        df: Counter[str] = Counter()
        for toks in d_toks:
            df.update(toks.keys())
        avgdl = sum(sum(t.values()) for t in d_toks) / n or 1.0
        scores: list[float] = []
        for toks in d_toks:
            dl = sum(toks.values())
            s = 0.0
            for term in q_toks:
                f = toks.get(term, 0)
                if not f:
                    continue
                idf = math.log((n - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
                s += idf * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / avgdl))
            scores.append(s)
        return scores


class KnowledgeBase:
    """知识语料库：knowledge/*.md → chunk → embed → JSON 索引 → cosine search。

    首次 search 惰性建/重建索引；索引态问题（缺失/损坏/mtime 漂移/模型变更）
    静默重建，语料为空恒空不报错（矩阵 #3/#4/#5/#12）；embedding API 失败重试
    后向上抛——推通道被 engine memory 守卫吞掉、拉通道由工具转错误文本
    （矩阵 #1/#9/#10）。
    """

    def __init__(self, runs_root: Path, corpus_dir: Path | None = None, *,
                 embedder: Embedder | None = None) -> None:
        self.runs_root = Path(runs_root)
        root = Path(__file__).resolve().parent.parent
        self.corpus_dir = Path(corpus_dir) if corpus_dir else root / "knowledge"
        self.index_path = self.runs_root / "knowledge" / "knowledge_index.json"
        self.embedder = embedder or build_embedder(
            self.runs_root / "knowledge" / "embed_cache.json")
        self._index: dict | None = None

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """向量+BM25 双腿 RRF 融合检索 top_k 命中 [{path, score, snippet}]。

        空 query/空语料恒空（不烧 API，矩阵 #4/#7）；top_k 超过总数返回全部
        （矩阵 #8）。RRF 只定序，score 仍取向量腿 cosine 原始分——分数域与
        miss_threshold=0.45 校准不变（裁定 2）；向量腿全 0（索引无 vector 且
        非 Tfidf）时 RRF 自然退化为 BM25 单腿（矩阵 #9 降级面）。
        """
        q = (query or "").strip()
        if not q or not self.corpus_dir.exists():
            return []
        self._ensure_index()
        chunks = self._index.get("chunks", [])
        if not chunks:
            return []
        if isinstance(self.embedder, TfidfEmbedder):
            # TfidfEmbedder 是 batch-local IDF（vocab 下标随批漂移）：query 必须
            # 与全体 chunk 同批嵌入，否则两批下标空间不同、cosine 无意义
            vecs = self.embedder.embed([q] + [_embed_input(c) for c in chunks])
            qvec, cvs = vecs[0], vecs[1:]
        else:  # 语义嵌入跨批一致：只嵌 query，与索引内向量点积
            qvec = self.embedder.embed([q])[0]
            cvs = [_vec_from_json(c["vector"]) if "vector" in c else {}
                   for c in chunks]  # 缺 vector（降级索引）→ 该腿全 0
        vec_scores = [_cosine(qvec, cv) for cv in cvs]
        bm25_scores = BM25Scorer().score(q, [_embed_input(c) for c in chunks])
        fused = _rrf([vec_scores, bm25_scores])
        # RRF 并列时按向量分决出：score 域（裁定 2）对用户可见的顺序不自相矛盾
        order = sorted(range(len(chunks)),
                       key=lambda j: (-fused[j], -vec_scores[j]))
        return [{"path": chunks[j]["path"], "score": vec_scores[j],
                 "snippet": _snippet(chunks[j])}
                for j in order[: max(top_k, 0)]]

    def reindex(self) -> int:
        """强制全量重建索引（make knowledge-index / CI 用），返回 chunk 数。"""
        self._index = self._build_index()
        return len(self._index["chunks"])

    def _ensure_index(self) -> None:
        # 进程级缓存：mtime/_fresh 只在首个 search（冷启动）检查——同进程内
        # quarantine 改盘后不会自动重索引，回滚跨进程生效（corpus_tools CLI
        # 与 agent_server 是不同进程，真实使用形态即跨进程；t6-rev Minor #3）
        if self._index is not None:
            return
        idx = self._load_index()
        if idx is not None and self._fresh(idx):
            self._index = idx
            return
        self._index = self._build_index()

    def _load_index(self) -> dict | None:
        if not self.index_path.exists():
            return None
        try:
            idx = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # 半写/损坏（矩阵 #3）→ 当缺失，惰性重建
        if not isinstance(idx, dict) or not isinstance(idx.get("chunks"), list):
            return None
        return idx

    def _fresh(self, idx: dict) -> bool:
        """索引新鲜度：源 mtime 集合一致 + 嵌入模型一致（维度随模型走，#12）。"""
        if idx.get("model") != _model_of(self.embedder):
            return False
        now = {self._key(p): p.stat().st_mtime for p in self._sources()}
        return idx.get("sources", {}) == now

    def _key(self, p: Path) -> str:
        # 索引键用相对路径（顶层文件与旧版文件名一致，向后兼容）；
        # 子目录条目（distilled/x.md）不与顶层同名文件冲突
        return p.relative_to(self.corpus_dir).as_posix()

    def _sources(self) -> list[Path]:
        """递归扫全部 *.md（九期：distilled/ 子目录新文件被 mtime 惰性重建
        自动接上——蒸馏落盘即索引，KB 零改动接线）。"""
        if not self.corpus_dir.exists():
            return []
        return sorted(self.corpus_dir.rglob("*.md"))

    def _build_index(self) -> dict:
        sources: dict[str, float] = {}
        chunks: list[dict] = []
        for p in self._sources():
            sources[self._key(p)] = p.stat().st_mtime
            if not _entry_active(p):
                continue   # 被隔离条目（active:false）不入索引（矩阵 #10 回滚生效）
            for ch in chunk_text(p.read_text(encoding="utf-8")):
                chunks.append({"path": self._key(p), "title": ch["title"],
                               "text": ch["text"]})
        if chunks:
            vecs = self.embedder.embed([_embed_input(c) for c in chunks])
            for c, v in zip(chunks, vecs, strict=True):
                c["vector"] = v
        idx = {"model": _model_of(self.embedder), "dim": _dim_of(self.embedder),
               "built_at": time.time(), "sources": sources, "chunks": chunks}
        self._write_index(idx)
        return idx

    def _write_index(self, idx: dict) -> None:
        # tmp+rename 原子替换；tmp 名带 pid+线程 id——两个实例并发重建时共用
        # 同一个 .tmp 会互相踩（一方 replace 后另一方 replace 报 FileNotFoundError）
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(
            f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.index_path)
