# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:55:00
@Description：
向量库构建脚本。
从 data/ 目录加载知识文件，切分并向量化后写入 Chroma。
'''
import sys
from pathlib import Path
from model.factory import get_model_factory
from service.vector_store import ChromaVectorStoreService

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))




def main():
    print("🔄 开始构建向量库 ...")
    factory = get_model_factory()
    embedding_model = factory.create_embedding_model()
    service = ChromaVectorStoreService(embedding_model=embedding_model)
    result = service.build_from_directory(str(PROJECT_ROOT / "data"))
    print(
        f"✅ 向量库构建完成: "
        f"files={result.loaded_file_count}, "
        f"chunks={result.chunk_count}, "
        f"collection={result.collection_name}"
    )


if __name__ == "__main__":
    main()
