# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-06 23:19:19
@Description：
logger_handler单元测试
'''
import logging
import os

import pytest

from utils import logger_handler


@pytest.fixture(autouse=True)
def cleanup_test_loggers():
    """清理测试创建的logger，避免用例之间共享handler状态。"""
    yield

    for logger_name in list(logger_handler._LOGGER_CACHE.keys()):
        if logger_name.startswith("test_logger_"):
            logger = logger_handler._LOGGER_CACHE.pop(logger_name)
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)


def test_get_logger_returns_same_instance_and_does_not_duplicate_handlers(tmp_path):
    """同名logger应该复用同一个实例，并且不会重复添加handler。"""
    logger_name = "test_logger_singleton"

    first_logger = logger_handler.get_logger(logger_name, log_dir=str(tmp_path))
    second_logger = logger_handler.get_logger(logger_name, log_dir=str(tmp_path))

    assert first_logger is second_logger
    assert len(first_logger.handlers) == 2
    assert first_logger.propagate is False


def test_get_logger_writes_utf8_file(tmp_path):
    """logger应该能以UTF-8编码写入中文日志内容。"""
    logger_name = "test_logger_utf8"
    logger = logger_handler.get_logger(
        logger_name,
        console_level=logging.CRITICAL,
        file_level=logging.DEBUG,
        log_dir=str(tmp_path),
    )

    logger.info("中文日志内容")
    for handler in logger.handlers:
        handler.flush()

    log_files = os.listdir(tmp_path)
    assert len(log_files) == 1

    log_path = os.path.join(tmp_path, log_files[0])
    with open(log_path, "r", encoding="utf-8") as log_file:
        content = log_file.read()

    assert "中文日志内容" in content
    assert logger_name in content
