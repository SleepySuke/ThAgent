from langchain_core.tools import tool


@tool
def query_bugs(keywords: str) -> str:
    """Query the bug tracking system for known issues matching the given keywords.

    Use this tool when the user reports a potential bug or defect to check if
    it's a known issue and find the current status and workaround.

    Args:
        keywords: Keywords or short description of the bug to search for.
    """
    from rag.chroma_client import search

    results = search(keywords, n_results=10)
    bugs = [r for r in results if r.get("metadata", {}).get("type") == "bug"]

    if not bugs:
        return "未找到匹配的已知缺陷记录。建议用户提交详细复现步骤，转交技术团队排查。"

    lines = ["找到以下相关缺陷记录："]
    for i, r in enumerate(bugs, 1):
        meta = r.get("metadata", {})
        lines.append(f"\n[{i}] {r['content']}")
    return "\n".join(lines)
