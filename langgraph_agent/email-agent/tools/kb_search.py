from langchain_core.tools import tool


@tool
def search_kb(query: str) -> str:
    """Search the product knowledge base for relevant documentation, FAQs, and
    troubleshooting guides.

    Use this tool to find answers to user questions from official documentation.

    Args:
        query: Search query describing what information you need.
    """
    from rag.chroma_client import search

    results = search(query, n_results=5)
    if not results:
        return "未找到相关文档。"

    lines = ["找到以下相关文档："]
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        doc_type = meta.get("type", "doc")
        lines.append(f"\n[{i}] [{doc_type}] {r['content']}")
    return "\n".join(lines)
