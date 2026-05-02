# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-10 22:08:47
@Description：向量存储数据
'''

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from config import load_config
class VectorStoreService(object):
    '''
    向量存储服务类，负责存储
    '''
    def __init__(self):
        # 这里可以初始化向量存储的相关配置，例如连接数据库等
        self.config = load_config()
        self.chroma = Chroma(
            collection_name=self.config['collection_name'],
            embedding_function=DashScopeEmbeddings(
                model=self.config['embedding-model'],dashscope_api_key = ''
                ),
            persist_directory=self.config['persist_directory']
        )


    def get_retriever(self):
        # 这里可以返回一个检索器对象，用于从向量存储中检索相关信息
        return self.chroma.as_retriever(
            search_kwargs={"k": int(self.config['retriever_k'])}
        )
