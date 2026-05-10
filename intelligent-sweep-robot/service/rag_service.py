# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 00:08:53
@Description：
RAG检索总结服务
'''
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from model.factory import ModelFactory, get_model_factory
from service.vector_store import ChromaVectorStoreService, RetrievedDocument
from utils.config_handler import RagRuntimeConfig, load_rag_config
from utils.logger_handler import get_logger
from utils.prompt_handler import load_prompt_bundle


class RagQueryResult(BaseModel):
    """RAG查询结果。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    retrieved_count: int = Field(ge=0)
    source_file_names: list[str] = Field(default_factory=list)


class RagSummarizeService:
    """RAG检索总结服务。"""

    def __init__(
            self,
            vector_store_service: ChromaVectorStoreService | None = None,
            chat_model=None,
            model_factory: ModelFactory | None = None,
            rag_config: RagRuntimeConfig | None = None,
    ):
        self.logger = get_logger(__name__)
        self.rag_config = rag_config or load_rag_config()
        self.model_factory = model_factory
        if chat_model is None or vector_store_service is None:
            self.model_factory = self.model_factory or get_model_factory()

        if chat_model is not None:
            self.chat_model = chat_model
        elif self.rag_config.model.use_project_default:
            self.chat_model = self.model_factory.create_chat_model()
        else:
            self.chat_model = self.model_factory.create_chat_model(
                chat_model=self.rag_config.model.chat_model,
                temperature=self.rag_config.model.temperature,
            )
        if vector_store_service is None:
            embedding_model = self.model_factory.create_embedding_model()
            vector_store_service = ChromaVectorStoreService(embedding_model=embedding_model)
        self.vector_store_service = vector_store_service

    def _select_context_documents(self, retrieved_documents: list[RetrievedDocument]) -> list[RetrievedDocument]:
        """按RAG配置裁剪上下文文档。"""
        selected_documents = []
        used_chars = 0
        for document in retrieved_documents[:self.rag_config.context.max_context_docs]:
            next_chars = len(document.content)
            if used_chars + next_chars > self.rag_config.context.max_context_chars:
                break
            selected_documents.append(document)
            used_chars += next_chars
        return selected_documents

    def _build_messages(self, query: str, retrieved_documents: list[RetrievedDocument]):
        """构建RAG总结消息。"""
        prompt_bundle = load_prompt_bundle()
        context = "\n\n".join(
            self.rag_config.context.source_format.format(
                file_name=document.metadata.get("file_name"),
                content=document.content,
            )
            for document in retrieved_documents
        )
        user_content = f"用户问题：{query}\n\n检索资料：\n{context}"
        return [
            SystemMessage(content=prompt_bundle.rag_prompt.content),
            HumanMessage(content=user_content),
        ]

    def query(self, query: str) -> RagQueryResult:
        """执行RAG查询。"""
        self.logger.info("开始执行RAG查询: %s", query)
        retrieved_documents = self.vector_store_service.retrieve(query)
        selected_documents = self._select_context_documents(retrieved_documents)
        if not selected_documents:
            return RagQueryResult(
                query=query,
                answer=self.rag_config.generation.fallback_answer,
                retrieved_count=0,
                source_file_names=[],
            )

        messages = self._build_messages(query, selected_documents)
        response = self.chat_model.invoke(messages)
        answer = response.content if hasattr(response, "content") else str(response)
        source_file_names = sorted(
            {
                document.metadata.get("file_name")
                for document in selected_documents
                if document.metadata.get("file_name")
            }
        ) if self.rag_config.output.include_source_file_names else []
        result = RagQueryResult(
            query=query,
            answer=answer,
            retrieved_count=len(selected_documents) if self.rag_config.output.include_retrieved_count else 0,
            source_file_names=source_file_names,
        )
        self.logger.info("RAG查询完成: query=%s, sources=%s", query, source_file_names)
        return result
