# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-10 22:08:10
@Description：知识库更新服务
'''

from datetime import datetime
import os
import hashlib
from typing import Optional
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import load_config


# 加载配置文件，获取知识库文件路径等信息
config = load_config()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class KnowledgeBaseService(object):
    '''
    知识库更新服务类，负责检查知识库文件的MD5值，判断是否需要更新，并保存新的MD5值
    '''
    def __init__(self):
        # 提前检查当前存放的db文件是否存在，不存在则创建
        os.makedirs(config['persist_directory'], exist_ok=True)
        # 初始化文本分割器
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=config['chunk_size'],
            chunk_overlap=config['chunk_overlap'],
            separators=config['separators']
        )
        # 初始化Chroma向量存储
        self.chroma = Chroma(
            collection_name=config['collection_name'],
            embedding_function=DashScopeEmbeddings(
                model=config['embedding-model'],dashscope_api_key = ''
                ),
            persist_directory=config['persist_directory']
        )



    def update_knowledge_base(self, data: Optional[str], file_name: Optional[str]):
        '''
        更新知识库文件，保存新的MD5值
        '''
        # 如果没有提供数据或文件名，直接返回
        if data is None or file_name is None:
            return {
                "status": "error",
                "message": "没有提供数据或文件名，无法更新知识库。",
                "added_chunks": 0,
            }

        data = data.strip()
        if not data:
            return {
                "status": "error",
                "message": f"文件 {file_name} 内容为空，无法写入资料库。",
                "added_chunks": 0,
            }
        
        # 需要分割的数据快列表
        chunks = []

        # 如果数据长度超过配置的最大长度，则进行文本分割
        if(len(data) > config['max_data_length']):
            chunks = self.spliter.split_text(data)
        else:
            chunks = [data]

        # 总体的知识块列表，包含需要添加到知识库的文本块
        knowledge_chunks = []
        new_md5_values = []

        # 对每个文本块计算MD5值，检查是否已经存在于知识库中，如果不存在则添加到知识块列表中，并保存新的MD5值
        for text in chunks:
            text = text.strip()
            if not text:
                continue
            md5_str = get_string_md5(text)
            if not check_md5(md5_str):
                knowledge_chunks.append(text)
                new_md5_values.append(md5_str)
            else:
                print("MD5值已存在，跳过该文本块。")
        
        # 将新的知识块添加到知识库中
        metadata = {
            "source": file_name,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        if not knowledge_chunks:
            return {
                "status": "skipped",
                "message": f"资料 {file_name} 已存在，无需重复导入。",
                "added_chunks": 0,
            }
        self.chroma.add_texts(knowledge_chunks, metadatas=[metadata for _ in knowledge_chunks])
        for md5_str in new_md5_values:
            save_md5(md5_str)
        print("新的数据已保存到知识库。")
        return {
            "status": "success",
            "message": f"资料 {file_name} 导入成功，共写入 {len(knowledge_chunks)} 个知识片段。",
            "added_chunks": len(knowledge_chunks),
        }

    def initialize_knowledge_base(self):
        '''
        根据配置文件初始化默认资料库
        '''
        init_results = []
        for file_name in config.get("files", {}).keys():
            file_path = _resolve_file_path(file_name)
            if not os.path.exists(file_path):
                init_results.append(
                    {
                        "status": "error",
                        "message": f"默认资料文件不存在：{file_name}",
                        "file_name": file_name,
                        "added_chunks": 0,
                    }
                )
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

            result = self.update_knowledge_base(file_content, file_name)
            result["file_name"] = file_name
            init_results.append(result)

        return init_results

        



def check_md5(md5_str: str) -> bool:
    '''
    检查知识库文件的MD5值，判断是否需要更新
    '''
    file_path = config["file_path"]
    if not os.path.exists(file_path):
        open(file_path, 'w').close()
        return False
    else:
        for line in open(file_path, 'r', encoding='utf-8').readlines():
            if line.strip() == md5_str:
                return True
    return False

def save_md5(md5_str: str):
    '''
    保存知识库文件的MD5值
    '''
    file_path = config["file_path"]
    with open(file_path,'a', encoding='utf-8') as f:
        f.write(md5_str + '\n')

def get_string_md5(input_str: str):
    '''
    将传入的字符转为md5值
    '''
    str_bytes = input_str.encode('utf-8')
    md5 = hashlib.md5()
    md5.update(str_bytes)
    return md5.hexdigest()


def _resolve_file_path(file_name: str) -> str:
    '''
    兼容相对路径与绝对路径的文件解析
    '''
    if os.path.isabs(file_name):
        return file_name
    return os.path.join(BASE_DIR, file_name)


# if __name__ == "__main__":
#     # 测试知识库更新服务
#     test_str = "这是一个测试字符串，用于生成MD5值。"
#     md5_str = get_string_md5(test_str)
#     print(f"生成的MD5值: {md5_str}")
#     if check_md5(md5_str):
#         print("MD5值已存在，知识库无需更新。")
#     else:
#         print("MD5值不存在，知识库需要更新。")
#         save_md5(md5_str)
#         print("新的MD5值已保存。")
