# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-04 19:53:54
@Description：向量数据存储示例 —— 从CSV加载到向量检索的完整RAG流程
'''

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_loaders import CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 初始化 Embedding 模型和向量存储
embedding = DashScopeEmbeddings(
    model="text-embedding-v3",
    dashscope_api_key=""
)
vector_store = InMemoryVectorStore(embedding=embedding)

# 加载 CSV 文档
loader = CSVLoader(
    file_path="./csv_data/ai_knowledge.csv",
    encoding="utf-8",
    csv_args={"delimiter": ","}
)
docs = loader.load()
print(f"加载文档数量: {len(docs)}")
for doc in docs[:2]:
    print(f"  - {doc.page_content[:80]}...")
    print(f"    metadata: {doc.metadata}")

#  文本分割
splitter = RecursiveCharacterTextSplitter(
    chunk_size=200,
    chunk_overlap=20,
    separators=["\n", "。", "，", " "]
)
splits = splitter.split_documents(docs)
print(f"\n分割后文本块数量: {len(splits)}")

#  存入向量存储
vector_store.add_documents(splits)
print("文档已存入向量存储\n")

#  相似度检索
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

#  删除演示
print("\n" + "=" * 50)
print("删除操作演示")
print("=" * 50)

# 先添加一条测试文档，拿到返回的 id
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

results = vector_store.similarity_search_with_score("临时数据", k=2)
for doc, score in results:
    print(f"分数: {score}, 内容: {doc.page_content[:60]}")
