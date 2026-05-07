# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:19:19
@Description：
path_tool单元测试
'''
import os

from utils.path_tool import get_abs_path, get_project_root


def test_get_project_root_returns_project_directory():
    """项目根目录应该定位到intelligent-sweep-robot。"""
    project_root = get_project_root()

    assert os.path.isabs(project_root)
    assert os.path.basename(project_root) == "intelligent-sweep-robot"
    assert os.path.exists(os.path.join(project_root, "utils", "path_tool.py"))


def test_get_abs_path_joins_project_root():
    """相对路径应该被拼接到项目根目录下。"""
    expected = os.path.join(get_project_root(), "data")

    assert get_abs_path("data") == expected


def test_get_abs_path_returns_none_for_none_input():
    """None输入用于表达无路径，应原样返回None。"""
    assert get_abs_path(None) is None
