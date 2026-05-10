# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 21:51:09
@Description：
vector_store单元测试
'''
import hashlib

from langchain_core.embeddings import Embeddings

from service.vector_store import ChromaVectorStoreService
from utils.file_handler import LoadedFile


class SimpleEmbeddings(Embeddings):
    """用于单元测试的确定性Embedding模型。"""

    def embed_documents(self, texts):
        """生成文档向量。"""
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text):
        """生成查询向量。"""
        return self._embed_text(text)

    def _embed_text(self, text):
        """将文本转换成稳定的简单向量。"""
        return [
            float(len(text)),
            float(text.count("智扫通")),
            float(text.count("更新")),
        ]


def _build_service(tmp_path, collection_name="unit_vector_store", chunk_size=300):
    """构建测试用向量库服务。"""
    return ChromaVectorStoreService(
        embedding_model=SimpleEmbeddings(),
        persist_directory=str(tmp_path / "chroma"),
        collection_name=collection_name,
        chunk_size=chunk_size,
        chunk_overlap=0,
        top_k=2,
    )


def _collection_count(service):
    """返回当前Chroma collection中的记录数量。"""
    return service._get_vector_store()._collection.count()


def test_split_loaded_file_adds_chunk_md5_metadata_and_stable_id(tmp_path):
    """切片后应该写入chunk_md5和稳定chunk_id，便于去重和排查。"""
    content = "智扫通S1支持自动集尘。智扫通S1支持热风烘干。"
    content_md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    loaded_file = LoadedFile(
        source_path=str(tmp_path / "knowledge.txt"),
        file_name="knowledge.txt",
        file_type="txt",
        file_md5=hashlib.md5(b"file-bytes").hexdigest(),
        content_md5=content_md5,
        content=content,
    )
    service = _build_service(tmp_path)

    documents = service._split_loaded_file(loaded_file)

    assert documents
    first_document = documents[0]
    source_md5 = hashlib.md5(loaded_file.source_path.encode("utf-8")).hexdigest()
    chunk_md5 = hashlib.md5(first_document.page_content.encode("utf-8")).hexdigest()
    assert first_document.metadata["source_md5"] == source_md5
    assert first_document.metadata["chunk_md5"] == chunk_md5
    assert first_document.metadata["chunk_id"] == f"{source_md5}_{content_md5}_0_{chunk_md5}"


def test_build_from_directory_deduplicates_same_content_before_writing(tmp_path):
    """构建向量库时应该复用文件工具的content_md5去重能力。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("重复的智扫通知识内容。", encoding="utf-8")
    (knowledge_dir / "b.txt").write_text("重复的智扫通知识内容。", encoding="utf-8")
    (knowledge_dir / "c.txt").write_text("唯一的智扫通知识内容。", encoding="utf-8")
    service = _build_service(tmp_path)

    result = service.build_from_directory(str(knowledge_dir))

    assert result.loaded_file_count == 2
    assert result.duplicate_count == 1
    assert result.chunk_count == 2
    assert _collection_count(service) == 2


def test_build_from_directory_can_keep_duplicate_content_when_deduplicate_disabled(tmp_path):
    """关闭去重时，同内容不同文件也应该生成不同chunk_id并分别入库。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("重复的智扫通知识内容。", encoding="utf-8")
    (knowledge_dir / "b.txt").write_text("重复的智扫通知识内容。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.deduplicate = False

    result = service.build_from_directory(str(knowledge_dir))
    stored_documents = service._get_vector_store()._collection.get(include=["metadatas"])
    file_names = sorted(metadata["file_name"] for metadata in stored_documents["metadatas"])

    assert result.loaded_file_count == 2
    assert result.duplicate_count == 0
    assert result.chunk_count == 2
    assert _collection_count(service) == 2
    assert file_names == ["a.txt", "b.txt"]


def test_build_from_directory_replaces_existing_chunks_for_changed_file(tmp_path):
    """同一个源文件内容变化时，旧切片应该先删除再写入新切片。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    knowledge_file = knowledge_dir / "product.txt"
    knowledge_file.write_text("智扫通旧知识内容。", encoding="utf-8")
    service = _build_service(tmp_path)

    first_result = service.build_from_directory(str(knowledge_dir))
    knowledge_file.write_text("智扫通更新后的知识内容。", encoding="utf-8")
    second_result = service.build_from_directory(str(knowledge_dir))
    stored_documents = service._get_vector_store()._collection.get(include=["documents"])

    assert first_result.chunk_count == 1
    assert second_result.deleted_chunk_count == 1
    assert second_result.chunk_count == 1
    assert _collection_count(service) == 1
    assert stored_documents["documents"] == ["智扫通更新后的知识内容。"]


def test_without_sync_deleted_files_keeps_orphaned_chunks(tmp_path):
    """默认不启用 sync_deleted_files 时，已从目录删除的文件对应切片会保留（问题复现）。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "keep.txt").write_text("保留的智扫通知识。", encoding="utf-8")
    (knowledge_dir / "remove.txt").write_text("即将删除的智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = False

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 2

    (knowledge_dir / "remove.txt").unlink()
    service.build_from_directory(str(knowledge_dir))

    # remove.txt 的孤儿切片仍然保留
    assert _collection_count(service) == 2


def test_sync_deleted_files_removes_orphaned_chunks(tmp_path):
    """启用 sync_deleted_files 时，已从目录删除的文件对应切片应该被清理。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "keep.txt").write_text("保留的智扫通知识。", encoding="utf-8")
    (knowledge_dir / "remove.txt").write_text("即将删除的智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = True

    # 第一次构建：两个文件都入库
    first_result = service.build_from_directory(str(knowledge_dir))
    assert first_result.chunk_count == 2
    assert _collection_count(service) == 2

    # 删除 remove.txt
    (knowledge_dir / "remove.txt").unlink()

    # 第二次构建：remove.txt 的切片应被自动清理
    second_result = service.build_from_directory(str(knowledge_dir))
    assert second_result.chunk_count == 1
    assert _collection_count(service) == 1
    # 包含 keep.txt 的旧切片清理 + remove.txt 的孤儿切片清理
    assert second_result.deleted_chunk_count == 2


def test_rebuild_collection_clears_all_and_rebuilds(tmp_path):
    """启用 rebuild_collection 时，应清空所有旧数据并重新构建。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "old.txt").write_text("旧智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.rebuild_collection = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 1

    # 替换文件内容并新增文件
    (knowledge_dir / "old.txt").write_text("更新后的智扫通知识。", encoding="utf-8")
    (knowledge_dir / "new.txt").write_text("全新智扫通知识。", encoding="utf-8")

    result = service.build_from_directory(str(knowledge_dir))
    assert result.chunk_count == 2
    assert _collection_count(service) == 2


# ========== 边界测试（收紧） ==========

def test_sync_deleted_files_with_empty_directory_clears_all(tmp_path):
    """空目录 + sync_deleted_files=True 时，应清空整个 collection。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("智扫通知识A。", encoding="utf-8")
    (knowledge_dir / "b.txt").write_text("智扫通知识B。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 2

    # 清空目录
    (knowledge_dir / "a.txt").unlink()
    (knowledge_dir / "b.txt").unlink()

    result = service.build_from_directory(str(knowledge_dir))
    assert result.chunk_count == 0
    assert result.deleted_chunk_count == 2
    assert _collection_count(service) == 0


def test_sync_deleted_files_false_with_empty_directory_keeps_all(tmp_path):
    """空目录 + sync_deleted_files=False（默认）时，不应删除任何已有数据。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("智扫通知识A。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = False

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 1

    (knowledge_dir / "a.txt").unlink()

    result = service.build_from_directory(str(knowledge_dir))
    # 目录为空，没有新文件写入，但旧切片应保留
    assert result.chunk_count == 0
    assert _collection_count(service) == 1


def test_sync_deleted_files_removes_multiple_orphaned_files(tmp_path):
    """同时删除多个文件时，所有孤儿切片都应被清理。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "keep.txt").write_text("保留。", encoding="utf-8")
    (knowledge_dir / "remove1.txt").write_text("删除1。", encoding="utf-8")
    (knowledge_dir / "remove2.txt").write_text("删除2。", encoding="utf-8")
    (knowledge_dir / "remove3.txt").write_text("删除3。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 4

    (knowledge_dir / "remove1.txt").unlink()
    (knowledge_dir / "remove2.txt").unlink()
    (knowledge_dir / "remove3.txt").unlink()

    result = service.build_from_directory(str(knowledge_dir))
    assert result.chunk_count == 1
    assert _collection_count(service) == 1
    # 1(keep旧) + 3(孤儿) = 4
    assert result.deleted_chunk_count == 4


def test_rebuild_collection_with_empty_directory_clears_all(tmp_path):
    """重建模式 + 空目录时，应清空整个 collection。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.rebuild_collection = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 1

    (knowledge_dir / "a.txt").unlink()

    result = service.build_from_directory(str(knowledge_dir))
    assert result.chunk_count == 0
    assert _collection_count(service) == 0


def test_rebuild_collection_takes_precedence_over_sync_deleted(tmp_path):
    """rebuild_collection=True 时，sync_deleted_files 不应执行（互斥）。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.rebuild_collection = True
    service.sync_deleted_files = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 1

    (knowledge_dir / "a.txt").unlink()

    result = service.build_from_directory(str(knowledge_dir))
    # rebuild_collection 优先，走 _clear_collection 分支
    assert result.chunk_count == 0
    assert result.deleted_chunk_count == 0
    assert _collection_count(service) == 0


def test_sync_deleted_files_does_not_remove_current_files(tmp_path):
    """sync_deleted_files 不应误删当前目录中仍然存在的文件切片。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "a.txt").write_text("智扫通知识。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = True

    service.build_from_directory(str(knowledge_dir))
    assert _collection_count(service) == 1

    # 修改内容但不删除文件
    (knowledge_dir / "a.txt").write_text("智扫通更新知识。", encoding="utf-8")

    result = service.build_from_directory(str(knowledge_dir))
    # 旧切片被清理，新切片写入，collection 中仍应有 1 条
    assert result.chunk_count == 1
    assert _collection_count(service) == 1
    assert result.deleted_chunk_count == 1


def test_sync_deleted_files_with_duplicates_after_removing_one(tmp_path):
    """有重复文件时删除其中一个，sync_deleted_files 应只清理被删除的那个。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "dup_a.txt").write_text("重复内容。", encoding="utf-8")
    (knowledge_dir / "dup_b.txt").write_text("重复内容。", encoding="utf-8")
    service = _build_service(tmp_path)
    service.sync_deleted_files = True

    # 第一次构建：dup_b 被判定为重复，只写入 dup_a
    result = service.build_from_directory(str(knowledge_dir))
    assert result.loaded_file_count == 1
    assert result.duplicate_count == 1
    assert result.chunk_count == 1
    assert _collection_count(service) == 1

    # 删除 dup_a（入库的那个）
    (knowledge_dir / "dup_a.txt").unlink()

    # 第二次构建：dup_b 不再重复，应该被入库
    second_result = service.build_from_directory(str(knowledge_dir))
    assert second_result.loaded_file_count == 1
    assert second_result.duplicate_count == 0
    assert second_result.chunk_count == 1
    assert _collection_count(service) == 1

    # 验证最终 collection 中的文件是 dup_b
    stored = service._get_vector_store()._collection.get(include=["metadatas"])
    assert stored["metadatas"][0]["file_name"] == "dup_b.txt"
