# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:38:38
@Description：
file_handler单元测试
'''
import hashlib

import pytest

from utils.file_handler import DirectoryLoadResult, LoadedFile, calculate_file_md5, load_directory, load_file


def _escape_pdf_text(text):
    """转义PDF文本对象中的特殊字符。"""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_simple_pdf(pdf_path, text):
    """写入一个可被PyPDFLoader解析的最小PDF文件。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({_escape_pdf_text(text)}) Tj ET"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\n"
        "endstream\nendobj\n".encode("latin-1"),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for pdf_object in objects:
        offsets.append(len(pdf))
        pdf += pdf_object

    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    pdf_path.write_bytes(pdf)


def test_load_file_reads_txt_as_loaded_file(tmp_path):
    """TXT文件应该被读取为LoadedFile模型。"""
    txt_path = tmp_path / "knowledge.txt"
    txt_path.write_text("智扫通S1适合小户型用户。", encoding="utf-8")

    loaded_file = load_file(str(txt_path))

    assert isinstance(loaded_file, LoadedFile)
    assert loaded_file.file_type == "txt"
    assert loaded_file.content == "智扫通S1适合小户型用户。"
    assert loaded_file.char_count == len("智扫通S1适合小户型用户。")
    assert loaded_file.file_md5 == calculate_file_md5(str(txt_path))
    assert loaded_file.content_md5 == hashlib.md5(loaded_file.content.encode("utf-8")).hexdigest()


def test_load_file_reads_pdf_with_langchain_pdf_loader(tmp_path):
    """PDF文件应该通过LangChain PyPDFLoader读取。"""
    pdf_path = tmp_path / "knowledge.pdf"
    _write_simple_pdf(pdf_path, "S1 Max supports automatic mop washing")

    loaded_file = load_file(str(pdf_path))

    assert isinstance(loaded_file, LoadedFile)
    assert loaded_file.file_type == "pdf"
    assert loaded_file.page_count == 1
    assert loaded_file.file_md5 == calculate_file_md5(str(pdf_path))
    assert "S1 Max supports automatic mop washing" in loaded_file.content


def test_load_directory_reads_supported_files_only(tmp_path):
    """目录读取应该只加载支持的TXT和PDF文件。"""
    txt_path = tmp_path / "a.txt"
    pdf_path = tmp_path / "b.pdf"
    ignored_path = tmp_path / "ignored.md"
    txt_path.write_text("滤网需要定期清理。", encoding="utf-8")
    _write_simple_pdf(pdf_path, "Main brush should be cleaned weekly")
    ignored_path.write_text("ignored", encoding="utf-8")

    result = load_directory(str(tmp_path))

    assert isinstance(result, DirectoryLoadResult)
    assert result.file_count == 2
    assert result.total_char_count > 0
    assert result.duplicate_count == 0
    assert [file.file_name for file in result.files] == ["a.txt", "b.pdf"]


def test_load_file_rejects_unsupported_file_type(tmp_path):
    """不支持的文件类型应该给出明确异常。"""
    file_path = tmp_path / "knowledge.md"
    file_path.write_text("# ignored", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        load_file(str(file_path))


def test_calculate_file_md5_returns_stable_hash(tmp_path):
    """文件MD5应该基于文件字节内容稳定计算。"""
    file_path = tmp_path / "knowledge.txt"
    file_path.write_text("same knowledge", encoding="utf-8")

    md5_value = calculate_file_md5(str(file_path))

    assert md5_value == hashlib.md5("same knowledge".encode("utf-8")).hexdigest()
    assert len(md5_value) == 32


def test_load_directory_deduplicates_same_content_by_default(tmp_path):
    """目录读取默认应该按content_md5跳过重复知识内容。"""
    first_path = tmp_path / "a.txt"
    duplicate_path = tmp_path / "b.txt"
    unique_path = tmp_path / "c.txt"
    first_path.write_text("重复的知识内容", encoding="utf-8")
    duplicate_path.write_text("重复的知识内容", encoding="utf-8")
    unique_path.write_text("新的知识内容", encoding="utf-8")

    result = load_directory(str(tmp_path))

    assert result.file_count == 2
    assert result.duplicate_count == 1
    assert [file.file_name for file in result.files] == ["a.txt", "c.txt"]
    assert result.skipped_duplicates[0].file_name == "b.txt"
    assert result.skipped_duplicates[0].duplicate_of == "a.txt"


def test_load_directory_can_disable_deduplicate(tmp_path):
    """调用方可以关闭目录去重以保留所有支持文件。"""
    first_path = tmp_path / "a.txt"
    duplicate_path = tmp_path / "b.txt"
    first_path.write_text("重复的知识内容", encoding="utf-8")
    duplicate_path.write_text("重复的知识内容", encoding="utf-8")

    result = load_directory(str(tmp_path), deduplicate=False)

    assert result.file_count == 2
    assert result.duplicate_count == 0
    assert [file.file_name for file in result.files] == ["a.txt", "b.txt"]
