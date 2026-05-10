# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 00:08:53
@Description：
Chroma向量库服务
'''
import hashlib
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ConfigDict, Field

from utils.config_handler import load_chroma_config
from utils.file_handler import DirectoryLoadResult, LoadedFile, load_directory
from utils.logger_handler import get_logger
from utils.path_tool import get_abs_path


class RetrievedDocument(BaseModel):
    """召回文档结果。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorStoreBuildResult(BaseModel):
    """向量库构建结果。"""

    model_config = ConfigDict(extra="forbid")

    loaded_file_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    deleted_chunk_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(ge=0)
    collection_name: str = Field(min_length=1)
    persist_directory: str = Field(min_length=1)


class ChromaVectorStoreService:
    """Chroma向量库服务。"""

    def __init__(
            self,
            embedding_model,
            persist_directory: str | None = None,
            collection_name: str | None = None,
            chunk_size: int | None = None,
            chunk_overlap: int | None = None,
            top_k: int | None = None,
            collection_metadata: dict[str, Any] | None = None,
            sync_deleted_files: bool | None = None,
            rebuild_collection: bool | None = None,
    ):
        chroma_config = load_chroma_config()
        self.logger = get_logger(__name__)
        self.embedding_model = embedding_model
        self.persist_directory = str(Path(persist_directory or get_abs_path(chroma_config.persist_directory)).resolve())
        self.collection_name = collection_name or chroma_config.collection_name
        self.chunk_size = chunk_size or chroma_config.text_splitter.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else chroma_config.text_splitter.chunk_overlap
        self.separators = chroma_config.text_splitter.separators
        self.top_k = top_k or chroma_config.retriever.top_k
        self.search_type = chroma_config.retriever.search_type
        self.score_threshold = chroma_config.retriever.score_threshold
        self.supported_file_types = chroma_config.document_loader.supported_file_types
        self.deduplicate = chroma_config.document_loader.deduplicate
        self.deduplicate_by = chroma_config.document_loader.deduplicate_by
        self.collection_metadata = collection_metadata or chroma_config.metadata
        self.sync_deleted_files = sync_deleted_files if sync_deleted_files is not None else chroma_config.sync_deleted_files
        self.rebuild_collection = rebuild_collection if rebuild_collection is not None else chroma_config.rebuild_collection
        self._vector_store = None

    def _get_vector_store(self) -> Chroma:
        """获取Chroma实例。"""
        if self._vector_store is None:
            self.logger.debug("初始化Chroma: collection=%s, persist=%s", self.collection_name, self.persist_directory)
            self._vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embedding_model,
                persist_directory=self.persist_directory,
                collection_metadata=self.collection_metadata,
            )
        return self._vector_store

    def _calculate_chunk_md5(self, chunk: str) -> str:
        """计算单个切片内容MD5。"""
        return hashlib.md5(chunk.encode("utf-8")).hexdigest()

    def _calculate_source_md5(self, source_path: str) -> str:
        """计算源文件路径MD5。"""
        return hashlib.md5(source_path.encode("utf-8")).hexdigest()

    def _build_chunk_id(self, source_md5: str, content_md5: str, chunk_index: int, chunk_md5: str) -> str:
        """构建稳定的向量库切片ID。"""
        return f"{source_md5}_{content_md5}_{chunk_index}_{chunk_md5}"

    def _delete_existing_documents_by_source(self, source_path: str) -> int:
        """按源文件路径删除Chroma中已有切片。"""
        vector_store = self._get_vector_store()
        existing_documents = vector_store._collection.get(
            where={"source_path": source_path},
            include=["metadatas"],
        )
        existing_ids = existing_documents.get("ids", [])
        if not existing_ids:
            self.logger.debug("未发现同源旧切片: source=%s", source_path)
            return 0

        vector_store.delete(ids=existing_ids)
        deleted_count = len(existing_ids)
        self.logger.info("已清理同源旧切片: source=%s, chunks=%s", source_path, deleted_count)
        return deleted_count

    def _delete_existing_documents_for_directory(self, directory_result: DirectoryLoadResult) -> int:
        """清理本次目录加载涉及文件的旧切片。"""
        source_paths = {loaded_file.source_path for loaded_file in directory_result.files}
        source_paths.update(duplicate.source_path for duplicate in directory_result.skipped_duplicates)
        deleted_count = 0
        for source_path in sorted(source_paths):
            deleted_count += self._delete_existing_documents_by_source(source_path)
        return deleted_count

    def _get_all_source_paths(self) -> set[str]:
        """获取向量库中所有已存储的 source_path（去重）。"""
        vector_store = self._get_vector_store()
        existing_documents = vector_store._collection.get(include=["metadatas"])
        source_paths = set()
        for metadata in existing_documents.get("metadatas", []):
            source_path = metadata.get("source_path")
            if source_path:
                source_paths.add(source_path)
        self.logger.debug("向量库现有 source_paths: %s", sorted(source_paths))
        return source_paths

    def _delete_documents_by_source_paths(self, source_paths: set[str]) -> int:
        """按多个 source_path 批量删除已有切片，返回删除数量。"""
        total_deleted = 0
        for source_path in sorted(source_paths):
            total_deleted += self._delete_existing_documents_by_source(source_path)
        return total_deleted

    def _clear_collection(self) -> None:
        """清空当前 collection 中的所有数据。"""
        vector_store = self._get_vector_store()
        try:
            vector_store.delete_collection()
            self.logger.info("已删除并清空 collection: %s", self.collection_name)
        except Exception:
            self.logger.warning("delete_collection 不可用，回退到逐条删除")
            all_docs = vector_store._collection.get(include=[])
            all_ids = all_docs.get("ids", [])
            if all_ids:
                vector_store.delete(ids=all_ids)
                self.logger.info("已逐条清空 collection: %s, ids=%s", self.collection_name, len(all_ids))
        self._vector_store = None

    def _split_loaded_file(self, loaded_file: LoadedFile) -> list[Document]:
        """将加载后的文件切分为LangChain Document。"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
        )
        source_md5 = self._calculate_source_md5(loaded_file.source_path)
        base_metadata = {
            "source_path": loaded_file.source_path,
            "source_md5": source_md5,
            "file_name": loaded_file.file_name,
            "file_type": loaded_file.file_type,
            "file_md5": loaded_file.file_md5,
            "content_md5": loaded_file.content_md5,
        }
        documents = []
        for index, chunk in enumerate(splitter.split_text(loaded_file.content)):
            chunk_md5 = self._calculate_chunk_md5(chunk)
            chunk_id = self._build_chunk_id(source_md5, loaded_file.content_md5, index, chunk_md5)
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        **base_metadata,
                        "chunk_index": index,
                        "chunk_md5": chunk_md5,
                        "chunk_id": chunk_id,
                    },
                )
            )
        self.logger.debug("文件切分完成: file=%s, chunks=%s", loaded_file.file_name, len(documents))
        return documents

    def build_from_directory(self, directory_path: str) -> VectorStoreBuildResult:
        """从目录加载知识文件并写入Chroma。"""
        self.logger.info("开始构建向量库: directory=%s", directory_path)
        directory_result = load_directory(
            directory_path,
            deduplicate=self.deduplicate,
            supported_file_types=self.supported_file_types,
            deduplicate_by=self.deduplicate_by,
        )
        self.logger.info(
            "知识文件加载完成: directory=%s, files=%s, duplicates=%s, deduplicate_by=%s",
            directory_result.directory_path,
            directory_result.file_count,
            directory_result.duplicate_count,
            self.deduplicate_by,
        )
        if self.rebuild_collection:
            self.logger.info("重建模式已启用，清空 collection")
            self._clear_collection()
            deleted_chunk_count = 0
        else:
            deleted_chunk_count = self._delete_existing_documents_for_directory(directory_result)

            if self.sync_deleted_files:
                all_stored_source_paths = self._get_all_source_paths()
                current_source_paths = {loaded_file.source_path for loaded_file in directory_result.files}
                current_source_paths.update(duplicate.source_path for duplicate in directory_result.skipped_duplicates)
                orphaned_source_paths = all_stored_source_paths - current_source_paths
                if orphaned_source_paths:
                    self.logger.info(
                        "发现已从目录移除的文件: count=%s, files=%s",
                        len(orphaned_source_paths),
                        sorted(orphaned_source_paths),
                    )
                    sync_deleted_count = self._delete_documents_by_source_paths(orphaned_source_paths)
                    deleted_chunk_count += sync_deleted_count
                    self.logger.info(
                        "同步删除孤儿文件完成: removed_files=%s, chunks=%s",
                        len(orphaned_source_paths),
                        sync_deleted_count,
                    )
        documents = []
        ids = []
        for loaded_file in directory_result.files:
            file_documents = self._split_loaded_file(loaded_file)
            documents.extend(file_documents)
            ids.extend(document.metadata["chunk_id"] for document in file_documents)

        vector_store = self._get_vector_store()
        if documents:
            self.logger.info("开始写入向量库: collection=%s, chunks=%s", self.collection_name, len(documents))
            vector_store.add_documents(documents=documents, ids=ids)
        else:
            self.logger.info("无可写入向量库的知识切片: collection=%s", self.collection_name)

        result = VectorStoreBuildResult(
            loaded_file_count=directory_result.file_count,
            duplicate_count=directory_result.duplicate_count,
            deleted_chunk_count=deleted_chunk_count,
            chunk_count=len(documents),
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
        )
        self.logger.info(
            "向量库构建完成: collection=%s, files=%s, duplicates=%s, deleted_chunks=%s, chunks=%s",
            result.collection_name,
            result.loaded_file_count,
            result.duplicate_count,
            result.deleted_chunk_count,
            result.chunk_count,
        )
        return result

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedDocument]:
        """从Chroma中召回相关文档。"""
        target_top_k = top_k or self.top_k
        self.logger.info("开始召回文档: query=%s, top_k=%s", query, target_top_k)
        documents = self._get_vector_store().similarity_search(query, k=target_top_k)
        retrieved_documents = [
            RetrievedDocument(content=document.page_content, metadata=document.metadata)
            for document in documents
        ]
        self.logger.info("文档召回完成: count=%s", len(retrieved_documents))
        return retrieved_documents
