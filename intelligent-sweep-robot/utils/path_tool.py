# 指定源码文件使用UTF-8编码，兼容中文注释和文档字符串。
# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-05 23:41:05
@Description：
为工程提供统一的读取绝对路径
'''
import os
from typing import Optional

from utils.logger_handler import get_logger

# 定义获取项目根目录的函数，返回值固定为字符串路径。
def get_project_root() -> str:
    """获取项目根目录"""
    # 获取路径工具模块的logger对象。
    logger = get_logger(__name__)
    # 记录开始获取项目根目录。
    logger.debug("开始获取项目根目录")
    # 获取当前工具文件的绝对路径，避免受运行目录影响。
    current_file_path = os.path.abspath(__file__)
    # 获取当前文件所在目录，也就是utils目录。
    current_dir = os.path.dirname(current_file_path)
    # 计算项目根目录。
    project_root = os.path.dirname(current_dir)
    # 记录项目根目录计算结果。
    logger.debug("项目根目录: %s", project_root)
    # 返回utils目录的上一级目录，作为项目根目录。
    return project_root

# 定义相对路径转绝对路径的函数，允许输入None。
def get_abs_path(relative_path: Optional[str]) -> Optional[str]:
    """获取绝对路径"""
    # 获取路径工具模块的logger对象。
    logger = get_logger(__name__)
    # 记录开始解析相对路径。
    logger.debug("开始解析相对路径: %s", relative_path)
    # 如果调用方没有提供路径，保留None语义并直接返回。
    if relative_path is None:
        # 记录空路径输入。
        logger.debug("相对路径为空，返回None")
        # 返回None，避免把空路径误拼成项目根目录。
        return None

    # 计算最终绝对路径。
    abs_path = os.path.abspath(os.path.join(get_project_root(), relative_path))
    # 记录路径解析结果。
    logger.debug("相对路径解析完成: %s -> %s", relative_path, abs_path)
    # 将相对路径拼接到项目根目录下并规范化为绝对路径。
    return abs_path
