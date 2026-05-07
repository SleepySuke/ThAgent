# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:40:08
@Description：
文件处理工具类，支持读取txt和pdf知识文件
'''
import hashlib
from pathlib import Path
from typing import Any, Literal

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from pydantic import BaseModel, ConfigDict, DirectoryPath, Field, FilePath, computed_field

from utils.logger_handler import get_logger

MD5_PATTERN = r"^[a-f0-9]{32}$"


class FileLoadRequest(BaseModel):
    """文件读取请求。"""

    model_config = ConfigDict(extra="forbid")

    path: FilePath


class DirectoryLoadRequest(BaseModel):
    """目录读取请求。"""

    model_config = ConfigDict(extra="forbid")

    path: DirectoryPath
    deduplicate: bool = True


class DuplicateFile(BaseModel):
    """被跳过的重复文件信息。"""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    file_md5: str = Field(pattern=MD5_PATTERN)
    content_md5: str = Field(pattern=MD5_PATTERN)
    duplicate_of: str = Field(min_length=1)


class LoadedFile(BaseModel):
    """已加载文件内容。"""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    file_type: Literal["txt", "pdf"]
    file_md5: str = Field(pattern=MD5_PATTERN)
    content_md5: str = Field(pattern=MD5_PATTERN)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    page_count: int = Field(default=0, ge=0)

    @computed_field
    @property
    def char_count(self) -> int:
        """返回文件内容字符数。"""
        return len(self.content)


class DirectoryLoadResult(BaseModel):
    """目录加载结果。"""

    model_config = ConfigDict(extra="forbid")

    directory_path: str = Field(min_length=1)
    files: list[LoadedFile] = Field(default_factory=list)
    skipped_duplicates: list[DuplicateFile] = Field(default_factory=list)

    @computed_field
    @property
    def file_count(self) -> int:
        """返回成功加载的文件数量。"""
        return len(self.files)

    @computed_field
    @property
    def total_char_count(self) -> int:
        """返回所有文件内容总字符数。"""
        return sum(file.char_count for file in self.files)

    @computed_field
    @property
    def duplicate_count(self) -> int:
        """返回被跳过的重复文件数量。"""
        return len(self.skipped_duplicates)


def _get_logger():
    """获取文件工具logger。"""
    return get_logger(__name__)


def calculate_file_md5(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """按文件字节内容计算MD5。"""
    logger = _get_logger()
    request = FileLoadRequest(path=file_path)
    target_file = Path(request.path).resolve()
    logger.debug("开始计算文件MD5: %s", target_file)

    md5_hash = hashlib.md5()
    with target_file.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            md5_hash.update(chunk)

    md5_value = md5_hash.hexdigest()
    logger.debug("文件MD5计算完成: file=%s, md5=%s", target_file, md5_value)
    return md5_value


def _calculate_content_md5(content: str) -> str:
    """按加载后的知识内容计算MD5。"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _build_loaded_file(
        file_path: Path,
        file_type: Literal["txt", "pdf"],
        page_contents: list[str],
        metadata: dict[str, Any],
) -> LoadedFile:
    """将LangChain加载结果转换为LoadedFile模型。"""
    logger = _get_logger()
    logger.debug("开始构建LoadedFile模型: %s", file_path)
    content = "\n\n".join(page_content.strip() for page_content in page_contents if page_content.strip())
    file_md5 = calculate_file_md5(str(file_path))
    content_md5 = _calculate_content_md5(content)
    loaded_file = LoadedFile(
        source_path=str(file_path),
        file_name=file_path.name,
        file_type=file_type,
        file_md5=file_md5,
        content_md5=content_md5,
        content=content,
        metadata=metadata,
        page_count=len(page_contents) if file_type == "pdf" else 0,
    )
    logger.info(
        "LoadedFile模型构建完成: file=%s, type=%s, chars=%s",
        loaded_file.file_name,
        loaded_file.file_type,
        loaded_file.char_count,
    )
    return loaded_file


def _load_txt_file(file_path: Path) -> LoadedFile:
    """读取TXT文件。"""
    logger = _get_logger()
    logger.debug("开始读取TXT文件: %s", file_path)
    documents = TextLoader(str(file_path), encoding="utf-8").load()
    page_contents = [document.page_content for document in documents]
    metadata = {
        "source": str(file_path),
        "documents": [document.metadata for document in documents],
    }
    loaded_file = _build_loaded_file(file_path, "txt", page_contents, metadata)
    logger.info("TXT文件读取完成: %s", file_path)
    return loaded_file


def _load_pdf_file(file_path: Path) -> LoadedFile:
    """使用LangChain PyPDFLoader读取PDF文件。"""
    logger = _get_logger()
    logger.debug("开始读取PDF文件: %s", file_path)
    documents = PyPDFLoader(str(file_path)).load()
    page_contents = [document.page_content for document in documents]
    metadata = {
        "source": str(file_path),
        "documents": [document.metadata for document in documents],
    }
    loaded_file = _build_loaded_file(file_path, "pdf", page_contents, metadata)
    logger.info("PDF文件读取完成: %s, pages=%s", file_path, loaded_file.page_count)
    return loaded_file


def load_file(file_path: str) -> LoadedFile:
    """根据文件类型读取单个知识文件。"""
    logger = _get_logger()
    logger.debug("开始加载文件: %s", file_path)
    request = FileLoadRequest(path=file_path)
    target_file = Path(request.path).resolve()
    suffix = target_file.suffix.lower()

    if suffix == ".txt":
        return _load_txt_file(target_file)
    if suffix == ".pdf":
        return _load_pdf_file(target_file)

    logger.error("不支持的文件类型: %s", suffix)
    raise ValueError(f"Unsupported file type: {suffix}")


def load_directory(directory_path: str, deduplicate: bool = True) -> DirectoryLoadResult:
    """批量读取目录中的知识文件。"""
    logger = _get_logger()
    logger.debug("开始批量读取目录: directory=%s, deduplicate=%s", directory_path, deduplicate)
    request = DirectoryLoadRequest(path=directory_path, deduplicate=deduplicate)
    target_directory = Path(request.path).resolve()
    supported_suffixes = {".txt", ".pdf"}
    loaded_files = []
    skipped_duplicates = []
    seen_content_md5 = {}

    for file_path in sorted(target_directory.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in supported_suffixes:
            continue

        loaded_file = load_file(str(file_path))
        original_file = seen_content_md5.get(loaded_file.content_md5)
        if request.deduplicate and original_file:
            skipped_duplicate = DuplicateFile(
                source_path=loaded_file.source_path,
                file_name=loaded_file.file_name,
                file_md5=loaded_file.file_md5,
                content_md5=loaded_file.content_md5,
                duplicate_of=original_file.file_name,
            )
            skipped_duplicates.append(skipped_duplicate)
            logger.info(
                "跳过重复知识文件: file=%s, duplicate_of=%s, content_md5=%s",
                loaded_file.file_name,
                original_file.file_name,
                loaded_file.content_md5,
            )
            continue

        seen_content_md5[loaded_file.content_md5] = loaded_file
        loaded_files.append(loaded_file)

    result = DirectoryLoadResult(
        directory_path=str(target_directory),
        files=loaded_files,
        skipped_duplicates=skipped_duplicates,
    )
    logger.info(
        "目录读取完成: directory=%s, files=%s, duplicates=%s, chars=%s",
        result.directory_path,
        result.file_count,
        result.duplicate_count,
        result.total_char_count,
    )
    return result
