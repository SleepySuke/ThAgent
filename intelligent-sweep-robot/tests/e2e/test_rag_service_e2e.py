# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 00:07:38
@Description：
RAG服务端到端测试
'''
import json
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage

from service.rag_service import RagSummarizeService
from service.vector_store import ChromaVectorStoreService


class KeywordEmbeddings(Embeddings):
    """用于e2e测试的确定性关键词向量。"""

    keywords = [
        "S1",
        "Max",
        "自动",
        "集尘",
        "洗拖布",
        "热风",
        "烘干",
        "基础款",
        "小户型",
    ]

    def embed_documents(self, texts):
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text):
        return self._embed_text(text)

    def _embed_text(self, text):
        return [float(text.count(keyword)) for keyword in self.keywords]


class DeterministicChatModel:
    """用于e2e测试的确定性chat model。"""

    def invoke(self, messages):
        return AIMessage(content="智扫通 S1 Max 支持自动集尘、自动洗拖布和热风烘干。")


def _escape_pdf_text(text):
    """转义PDF文本对象中的特殊字符。"""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_simple_pdf(pdf_path, text):
    """写入一个可被PyPDFLoader解析的最小PDF文件。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({_escape_pdf_text(text)}) Tj ET"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\n"
        "endstream\nendobj\n".encode("latin-1"),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for pdf_object in objects:
        offsets.append(len(pdf))
        pdf += pdf_object

    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    pdf_path.write_bytes(pdf)


def _prepare_knowledge_files(knowledge_dir):
    """准备e2e测试知识文件。"""
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "s1_max_knowledge.txt").write_text(
        "智扫通 S1 Max 支持自动集尘、自动洗拖布、热风烘干，适合大户型和宠物家庭。",
        encoding="utf-8",
    )
    (knowledge_dir / "s1_basic_knowledge.txt").write_text(
        "智扫通基础型号适合小户型和预算敏感用户，重点提供日常扫拖能力。",
        encoding="utf-8",
    )
    _write_simple_pdf(
        knowledge_dir / "maintenance_knowledge.pdf",
        "S1 Max supports automatic dust collection, mop washing, and hot-air drying.",
    )


def test_rag_service_matches_expected_result(tmp_path):
    """RAG服务真实结果应该与预期结果一致。"""
    project_root = Path(__file__).resolve().parents[2]
    expected_path = project_root / "tests" / "e2e" / "expected" / "rag_query_expected.json"
    actual_path = project_root / "tests" / "e2e" / "actual" / "rag_query_actual.json"
    knowledge_dir = tmp_path / "knowledge"
    persist_directory = tmp_path / "chroma"
    query = "S1 Max 支持自动集尘、自动洗拖布和热风烘干吗？"
    _prepare_knowledge_files(knowledge_dir)

    vector_store_service = ChromaVectorStoreService(
        embedding_model=KeywordEmbeddings(),
        persist_directory=str(persist_directory),
        collection_name="e2e_sweep_robot_knowledge",
        chunk_size=300,
        chunk_overlap=0,
        top_k=2,
    )
    vector_store_service.build_from_directory(str(knowledge_dir))
    rag_service = RagSummarizeService(
        vector_store_service=vector_store_service,
        chat_model=DeterministicChatModel(),
    )

    actual_result = rag_service.query(query).model_dump(mode="json")
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(
        json.dumps(actual_result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    expected_result = json.loads(expected_path.read_text(encoding="utf-8"))

    assert actual_result == expected_result
