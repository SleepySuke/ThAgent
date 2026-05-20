# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17
@Description：
提供统一的绝对路径解析
'''

import os


def get_project_root() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(current_dir)


def get_abs_path(relative_path: str | None) -> str | None:
    if relative_path is None:
        return None
    return os.path.abspath(os.path.join(get_project_root(), relative_path))
