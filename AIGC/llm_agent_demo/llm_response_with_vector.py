# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-08 00:23:13
@Description：向量存储之后组装vector检索结果作为LLM输入的示例
'''



from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


# 初始化 Embedding 模型和向量存储
embedding = DashScopeEmbeddings(
    model="text-embedding-v3",
    dashscope_api_key=""
)

# 初始化向量存储
vector_store = InMemoryVectorStore(embedding=embedding)


# 加载文档内容
loader = CSVLoader(
    file_path="./csv_data/ai_knowledge.csv",
    encoding="utf-8",
    csv_args={"delimiter": ","}
)

# 将文档内容分割成更小的文本块
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 100,  # 每个文本块的最大长度
    chunk_overlap = 5,  # 文本块之间的重叠长度
    separators=["\n\n", "\n", " ", ""], # 分割文本的分隔符列表
)

# 加载并分割文档
docs = loader.load()
print(f"加载文档数量: {len(docs)}")
for doc in docs[:2]:
    print(f"  - {doc.page_content[:80]}...")
    print(f"    metadata: {doc.metadata}")
splits = text_splitter.split_documents(docs)
print(f"\n分割后文本块数量: {len(splits)}")

# 将分割后的文本块存入向量存储
vector_store.add_documents(splits)
print("文档已存入向量存储\n")

# 初始化聊天模型
chat_model = ChatTongyi(
    model="qwen-plus",
    dashscope_api_key=""
)

# 定义聊天提示模板
prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个AI助手，帮助用户解答关于人工智能的问题。"),
        ("human", "根据以下文档内容回答用户的问题：{retrieved_docs}\n\n用户问题：{user_query}")
    ]
)


def print_prompt(full_prompt):
    print("="*20,full_prompt.to_string(),"="*20)
    return full_prompt


# 定义一个函数来处理用户查询
def answer_query(user_query):
    # 从向量存储中检索与用户查询相关的文档
    retrieved_docs = vector_store.similarity_search(user_query, k=3)
    retrieved_texts = "\n\n".join([doc.page_content for doc in retrieved_docs])
    print(f'检索到的相关文档:\n{retrieved_texts}\n')
    
    
    parse = StrOutputParser()

    # 调用聊天模型生成回答
    chain = prompt_template | print_prompt | chat_model | parse

    response = chain.invoke(
        {
            "retrieved_docs": retrieved_texts,
            "user_query": user_query
        }
    )
    
    return response

# 测试用户查询
if __name__ == "__main__":
    test_queries = [
        "什么是RAG？它的工作流程是什么？",
        "有哪些主流的Agent框架？",
        "怎么保证Agent的安全性？"
    ]
    
    for query in test_queries:
        print(f"\n用户问题: {query}")
        answer = answer_query(query)
        print(f"AI助手回答: {answer}\n")
