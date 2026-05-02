# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-04 18:16:34
@Description：文档加载器的使用
'''

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

loader = TextLoader(

    '/Users/suke/Python/Agent/AIGC/llm_agent_demo/sample_docs/ai_agent_intro.txt',
)

docs = loader.load()

print(docs) # 输出加载的文档内容

splitter = RecursiveCharacterTextSplitter(

    chunk_size = 500, # 每个文本块的最大长度
    chunk_overlap = 50, # 文本块之间的重叠长度
    separators=["\n\n", "\n", " ", ""], # 分割文本的分隔符列表
    length_function = len, # 计算文本长度的函数
)

# 将文档分割成更小的文本块
chunks = splitter.split_documents(docs)
print(len(chunks)) # 输出分割后的文本块数量
# 输出分割后的文本块
for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}:\n{chunk.page_content}\n")


