# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-04
@Description：Chroma 向量存储示例 —— 持久化存储与完整RAG流程
'''

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_loaders import CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 初始化 Embedding 模型
embedding = DashScopeEmbeddings(
    model="text-embedding-v3",
    dashscope_api_key=""
)

# 初始化 Chroma 向量存储（持久化到本地目录）
vector_store = Chroma(
    collection_name="ai_knowledge",
    embedding_function=embedding,
    persist_directory="/Users/suke/Python/Agent/AIGC/llm_agent_demo/chroma_db"
)

# # 加载 CSV 文档
# loader = CSVLoader(
#     file_path="/Users/suke/Python/Agent/AIGC/llm_agent_demo/csv_data/ai_knowledge.csv",
#     encoding="utf-8",
#     csv_args={"delimiter": ","}
# )
# docs = loader.load()
# print(f"加载文档数量: {len(docs)}")
# for doc in docs[:2]:
#     print(f"  - {doc.page_content[:80]}...")
#     print(f"    metadata: {doc.metadata}")

# 文本分割
# splitter = RecursiveCharacterTextSplitter(
#     chunk_size=200,
#     chunk_overlap=20,
#     separators=["\n", "。", "，", " "]
# )
# splits = splitter.split_documents(docs)
# print(f"\n分割后文本块数量: {len(splits)}")

# 存入向量存储（自动持久化到 /Users/suke/Python/Agent/AIGC/llm_agent_demo/chroma_db 目录）
# vector_store.add_documents(splits)
# print("文档已存入向量存储（已持久化）\n")

# 相似度检索
print("=" * 50)
print("相似度检索演示")
print("=" * 50)

queries = [
    "什么是RAG？它的工作流程是什么？",
    "有哪些主流的Agent框架？",
    "怎么保证Agent的安全性？"
]

for query in queries:
    print(f"\n问题: {query}")
    results = vector_store.similarity_search(query, k=2)
    for i, doc in enumerate(results):
        print(f"  结果{i + 1}: {doc.page_content[:100]}...")

# 删除演示
print("\n" + "=" * 50)
print("删除操作演示")
print("=" * 50)

test_ids = vector_store.add_texts(
    texts=["这是一条用于测试删除功能的临时数据"],
    metadatas=[{"source": "test_delete"}]
)
print(f"添加测试文档，id: {test_ids}")

# 删除前
before = vector_store.similarity_search("临时数据", k=1)
print(f"删除前: {before[0].page_content[:60]}")
print(f"删除前检索结果数: {len(before)}")

vector_store.delete(test_ids)
print(f"已删除 id: {test_ids}")

# 删除后
after = vector_store.similarity_search("临时数据", k=1)
print(f"删除后: {after[0].page_content[:60]}")

# 持久化验证提示
print("\n" + "=" * 50)
print("持久化说明")
print("=" * 50)
print("数据已保存到 ./chroma_db 目录，下次启动时 Chroma 会自动加载已有数据。")
print("如需重新构建，删除 ./chroma_db 目录即可。")
