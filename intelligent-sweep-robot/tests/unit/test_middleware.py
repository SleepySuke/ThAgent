# -*- coding: UTF-8 -*-
"""middleware 单元测试。"""
from unittest.mock import patch

from middleware.agent_middleware import (
    create_middleware_from_config,
    load_middleware_config,
)


class TestCreateMiddlewareFromConfig:
    """测试从配置创建 middleware 列表。"""

    @patch("middleware.agent_middleware.load_agent_config")
    def test_returns_list_of_middleware(self, mock_load_agent_config):
        """create_middleware_from_config 应返回 middleware 列表。"""
        mock_load_agent_config.return_value = {
            "middleware": {
                "enable_log_before_model": True,
                "enable_log_after_model": True,
                "enable_tool_monitor": True,
            }
        }
        result = create_middleware_from_config()
        assert isinstance(result, list)
        assert len(result) == 3

    @patch("middleware.agent_middleware.load_agent_config")
    def test_respects_disabled_flags(self, mock_load_agent_config):
        """当开关关闭时不应包含对应 middleware。"""
        mock_load_agent_config.return_value = {
            "middleware": {
                "enable_log_before_model": False,
                "enable_log_after_model": True,
                "enable_tool_monitor": False,
            }
        }
        result = create_middleware_from_config()
        assert len(result) == 1

    @patch("middleware.agent_middleware.load_agent_config")
    def test_defaults_to_all_enabled_when_config_empty(self, mock_load_agent_config):
        """当配置为空时，默认全部开启（3 个 middleware）。"""
        mock_load_agent_config.return_value = {}
        result = create_middleware_from_config()
        assert len(result) == 3

    @patch("middleware.agent_middleware.load_agent_config")
    def test_defaults_to_all_enabled_when_config_none(self, mock_load_agent_config):
        """当配置为 None 时，默认全部开启。"""
        mock_load_agent_config.return_value = None
        result = create_middleware_from_config()
        assert len(result) == 3


class TestLoadMiddlewareConfig:
    """测试 middleware 配置加载。"""

    @patch("middleware.agent_middleware.load_agent_config")
    def test_returns_middleware_dict(self, mock_load_agent_config):
        """load_middleware_config 应返回 agent_config 中的 middleware 字典。"""
        mock_load_agent_config.return_value = {
            "middleware": {
                "enable_log_before_model": True,
                "enable_log_after_model": False,
            }
        }
        config = load_middleware_config()
        assert config["enable_log_before_model"] is True
        assert config["enable_log_after_model"] is False

    @patch("middleware.agent_middleware.load_agent_config")
    def test_returns_empty_when_missing(self, mock_load_agent_config):
        """当 agent_config 中没有 middleware 字段时返回空字典。"""
        mock_load_agent_config.return_value = {}
        config = load_middleware_config()
        assert config == {}
