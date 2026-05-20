# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17
@Description：
日志工具类
'''

from datetime import datetime
import logging
import os
from pathlib import Path
from threading import Lock

LOG_ROOT = str(Path(__file__).resolve().parent.parent / "logs")
DEFAULT_LOGGER_NAME = "email_agent"

DEFAULT_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

_LOGGER_LOCK = Lock()
_LOGGER_CACHE = {}


def get_logger(name: str = DEFAULT_LOGGER_NAME) -> logging.Logger:
    logger_name = name or DEFAULT_LOGGER_NAME
    with _LOGGER_LOCK:
        if logger_name in _LOGGER_CACHE:
            return _LOGGER_CACHE[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        if logger.handlers:
            _LOGGER_CACHE[logger_name] = logger
            return logger

        os.makedirs(LOG_ROOT, exist_ok=True)
        log_file = os.path.join(LOG_ROOT, f"{logger_name}_{datetime.now().strftime('%Y%m%d')}.log")

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(DEFAULT_LOG_FORMAT)
        logger.addHandler(console_handler)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(DEFAULT_LOG_FORMAT)
        logger.addHandler(file_handler)

        _LOGGER_CACHE[logger_name] = logger
        return logger
