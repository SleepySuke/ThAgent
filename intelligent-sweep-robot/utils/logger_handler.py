# 指定源码文件使用UTF-8编码，保证中文日志说明和注释可读。
# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-05 23:52:23
@Description：
日志工具类 记录每次执行信息
'''
from datetime import datetime
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Optional

# 日志文件路径
# 定义默认日志目录，默认落在项目根目录的logs文件夹。
LOG_ROOT = str(Path(__file__).resolve().parent.parent / "logs")
# 定义默认logger名称，调用方不传name时使用该名称。
DEFAULT_LOGGER_NAME = "agent"

# 日志格式
# 创建统一日志格式对象，供控制台和文件handler复用。
DEFAULT_LOG_FORMAT = logging.Formatter(
    # 定义日志时间、名称、级别、位置和消息内容。
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
# 完成Formatter对象创建。
)

# 创建全局锁，保护logger缓存初始化过程。
_LOGGER_LOCK = Lock()
# 创建logger缓存字典，实现按logger名称复用同一个logger实例。
_LOGGER_CACHE = {}


# 封装日志文件路径生成逻辑。
def _build_log_file(name: str, log_file: Optional[str], log_dir: Optional[str]) -> str:
    """生成日志文件路径。"""
    # 如果调用方指定了完整日志文件路径，则优先使用该路径。
    if log_file:
        # 将传入日志文件路径规范化为绝对路径。
        target_log_file = os.path.abspath(log_file)
    # 如果调用方没有指定日志文件路径，则按日志目录和logger名称生成默认文件名。
    else:
        # 选择调用方传入的日志目录，否则使用默认日志目录。
        target_log_dir = os.path.abspath(log_dir or LOG_ROOT)
        # 拼接最终日志文件路径。
        target_log_file = os.path.join(
            # 使用目标日志目录作为文件所在目录。
            target_log_dir,
            # 使用logger名称和当前日期生成日志文件名。
            f"{name}_{datetime.now().strftime('%Y%m%d')}.log",
        )

    # 确保日志文件所在目录存在，目录已存在时不报错。
    os.makedirs(os.path.dirname(target_log_file), exist_ok=True)
    # 返回最终日志文件绝对路径。
    return target_log_file


# 定义统一获取logger对象的入口。
def get_logger(
        # logger名称，None或空字符串时会使用默认名称。
        name: Optional[str] = DEFAULT_LOGGER_NAME,
        # 控制台日志级别，默认输出INFO及以上。
        console_level: Optional[int] = logging.INFO,
        # 文件日志级别，默认记录DEBUG及以上。
        file_level: Optional[int] = logging.DEBUG,
        # 可选的完整日志文件路径，传入后优先级高于log_dir。
        log_file: Optional[str] = None,
        # 可选的日志目录，不传时使用项目logs目录。
        log_dir: Optional[str] = None,
# 返回标准库logging.Logger对象。
) -> logging.Logger:
    """获取日志记录器"""
    # 统一处理空名称，保证缓存key始终有效。
    logger_name = name or DEFAULT_LOGGER_NAME

    # 加锁保护缓存读取和初始化，避免并发重复添加handler。
    with _LOGGER_LOCK:
        # 如果同名logger已经初始化过，则直接复用缓存对象。
        if logger_name in _LOGGER_CACHE:
            # 返回缓存中的logger，避免重复添加handler。
            return _LOGGER_CACHE[logger_name]

        # 从logging模块获取指定名称的logger实例。
        logger = logging.getLogger(logger_name)
        # 设置logger总开关为DEBUG，让具体handler决定最终输出级别。
        logger.setLevel(logging.DEBUG)
        # 禁止日志向root logger传播，避免控制台重复输出。
        logger.propagate = False

        # 如果外部已经为该logger配置过handler，则尊重现有配置。
        if logger.handlers:
            # 将已有logger放入缓存，保持后续单例复用。
            _LOGGER_CACHE[logger_name] = logger
            # 返回已有handler的logger，避免重复添加handler。
            return logger

        # 创建控制台handler，用于开发和运行时实时查看日志。
        console_handler = logging.StreamHandler()
        # 设置控制台handler的日志输出级别。
        console_handler.setLevel(console_level)

        # 生成或解析最终日志文件路径。
        target_log_file = _build_log_file(logger_name, log_file, log_dir)
        # 创建UTF-8文件handler，支持中文日志内容。
        file_handler = logging.FileHandler(target_log_file, encoding="utf-8")
        # 设置文件handler的日志输出级别。
        file_handler.setLevel(file_level)

        # 为控制台handler绑定统一日志格式。
        console_handler.setFormatter(DEFAULT_LOG_FORMAT)
        # 为文件handler绑定统一日志格式。
        file_handler.setFormatter(DEFAULT_LOG_FORMAT)

        # 将控制台handler添加到logger。
        logger.addHandler(console_handler)
        # 将文件handler添加到logger。
        logger.addHandler(file_handler)

        # 将初始化完成的logger写入缓存，实现单例复用。
        _LOGGER_CACHE[logger_name] = logger
        # 返回初始化完成的logger对象。
        return logger
