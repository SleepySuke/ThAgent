# -*- coding: UTF-8 -*-
"""react_agent 单元测试。"""
from unittest.mock import MagicMock, patch


class TestCreateAgent:
    """测试 Agent 创建逻辑。"""

    @patch("react_agent.get_model_factory")
    @patch("react_agent.get_agent_tools")
    @patch("react_agent.load_prompt_bundle")
    @patch("react_agent.create_middleware_from_config")
    @patch("react_agent.build_prompt_middleware")
    @patch("react_agent.create_agent")
    def test_create_sweep_robot_agent_composes_all_components(
        self,
        mock_create_agent,
        mock_build_prompt_mw,
        mock_create_mw_from_config,
        mock_load_prompt_bundle,
        mock_get_agent_tools,
        mock_get_model_factory,
    ):
        """create_sweep_robot_agent 应组合模型、工具和 middleware。"""
        mock_model = MagicMock()
        mock_tools = [MagicMock(), MagicMock()]
        mock_bundle = MagicMock()
        mock_prompt_mw = MagicMock()
        mock_logging_mw = [MagicMock(), MagicMock()]
        mock_agent = MagicMock()

        mock_get_model_factory.return_value.create_chat_model.return_value = mock_model
        mock_get_agent_tools.return_value = mock_tools
        mock_load_prompt_bundle.return_value = mock_bundle
        mock_build_prompt_mw.return_value = mock_prompt_mw
        mock_create_mw_from_config.return_value = mock_logging_mw
        mock_create_agent.return_value = mock_agent

        from react_agent import create_sweep_robot_agent

        agent = create_sweep_robot_agent()

        mock_get_model_factory.assert_called_once()
        mock_get_agent_tools.assert_called_once()
        mock_load_prompt_bundle.assert_called_once()
        mock_build_prompt_mw.assert_called_once_with(mock_bundle)
        mock_create_mw_from_config.assert_called_once()
        mock_create_agent.assert_called_once_with(
            model=mock_model,
            tools=mock_tools,
            middleware=[mock_prompt_mw, *mock_logging_mw],
        )
        assert agent is mock_agent


class TestExecute:
    """测试同步执行入口。"""

    def test_execute_extracts_ai_message_content(self):
        """execute 应该从 Agent 结果中提取最后一条 AI 消息的内容。"""
        from react_agent import execute

        mock_agent = MagicMock()
        ai_message = MagicMock()
        ai_message.type = "ai"
        ai_message.content = "这是 AI 的回答"
        mock_agent.invoke.return_value = {"messages": [ai_message]}

        result = execute(mock_agent, "用户问题")

        mock_agent.invoke.assert_called_once()
        assert result == "这是 AI 的回答"

    def test_execute_returns_empty_when_no_ai_message(self):
        """当结果中没有 AI 消息时，execute 应返回空字符串。"""
        from react_agent import execute

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        result = execute(mock_agent, "用户问题")

        assert result == ""

    def test_execute_skips_ai_message_with_empty_content(self):
        """当 AI 消息 content 为空（仅含 tool_calls）时，应跳过并取下一个有实际内容的 AI 消息。"""
        from react_agent import execute

        mock_agent = MagicMock()
        tool_call_msg = MagicMock()
        tool_call_msg.type = "ai"
        tool_call_msg.content = ""
        answer_msg = MagicMock()
        answer_msg.type = "ai"
        answer_msg.content = "最终回答内容"
        mock_agent.invoke.return_value = {
            "messages": [tool_call_msg, MagicMock(), answer_msg]
        }

        result = execute(mock_agent, "用户问题")

        assert result == "最终回答内容"


class TestExecuteStream:
    """测试流式执行入口。"""

    def test_execute_stream_yields_agent_chunks(self):
        """execute_stream 应该逐块产出 Agent 的流式结果。"""
        from react_agent import execute_stream

        mock_agent = MagicMock()
        chunk_1 = {"agent": {"messages": [MagicMock(content=" chunk1")]}}
        chunk_2 = {"agent": {"messages": [MagicMock(content=" chunk2")]}}
        mock_agent.stream.return_value = [chunk_1, chunk_2]

        chunks = list(execute_stream(mock_agent, "用户问题"))

        mock_agent.stream.assert_called_once()
        assert len(chunks) == 2
        assert chunks[0] is chunk_1
        assert chunks[1] is chunk_2
