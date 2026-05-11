# -*- coding: UTF-8 -*-
"""工具 description 丰富度测试。

验证每个工具的 description 都包含足够的上下文信息，
帮助 LLM 正确判断调用时机和输入要求。
"""
from tools.generate_external_data import generate_external_data
from tools.get_current_month import get_current_month
from tools.get_user_id import get_user_id
from tools.get_user_location import get_user_location
from tools.get_weather import get_weather
from tools.rag_summarize import rag_summarize


def _assert_description(tool, min_length=30):
    """通用断言：description 非空且长度达标。"""
    assert tool.description, f"{tool.name} 的 description 不能为空"
    assert len(tool.description) >= min_length, (
        f"{tool.name} 的 description 太短（{len(tool.description)} 字符），"
        f"需要至少 {min_length} 字符"
    )


class TestRagSummarizeDescription:
    """rag_summarize 的 description 应该明确覆盖知识库范围和调用时机。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(rag_summarize, min_length=50)

    def test_description_includes_call_timing(self):
        """description 应该包含调用时机，帮助 LLM 判断何时使用。"""
        desc = rag_summarize.description.lower()
        assert "当" in desc or "用户" in desc or "咨询" in desc or "问题" in desc, (
            "rag_summarize 的 description 应该包含调用时机（如'当用户咨询...'）"
        )

    def test_description_includes_knowledge_scope(self):
        """description 应该说明覆盖的知识范围。"""
        desc = rag_summarize.description.lower()
        assert "知识库" in desc or "产品" in desc or "资料" in desc, (
            "rag_summarize 的 description 应该说明知识库范围"
        )


class TestGetWeatherDescription:
    """get_weather 的 description 应该明确输入和适用场景。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(get_weather, min_length=30)

    def test_description_includes_city_input(self):
        """description 应该说明需要城市名作为输入。"""
        desc = get_weather.description.lower()
        assert "城市" in desc or "地点" in desc or "位置" in desc, (
            "get_weather 的 description 应该说明输入是城市/地点"
        )

    def test_description_includes_call_timing(self):
        desc = get_weather.description.lower()
        assert "天气" in desc or "湿度" in desc or "拖地" in desc or "下雨" in desc, (
            "get_weather 的 description 应该关联天气相关场景"
        )


class TestGetUserLocationDescription:
    """get_user_location 的 description 应该说明用途。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(get_user_location, min_length=30)

    def test_description_includes_purpose(self):
        desc = get_user_location.description.lower()
        assert "位置" in desc or "城市" in desc or "地理" in desc, (
            "get_user_location 的 description 应该说明获取位置的目的"
        )


class TestGetUserIdDescription:
    """get_user_id 的 description 应该关联报告生成场景。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(get_user_id, min_length=30)

    def test_description_includes_report_context(self):
        desc = get_user_id.description.lower()
        assert "报告" in desc or "用户" in desc or "id" in desc, (
            "get_user_id 的 description 应该关联报告或用户身份场景"
        )


class TestGetCurrentMonthDescription:
    """get_current_month 的 description 应该关联时间范围。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(get_current_month, min_length=30)

    def test_description_includes_month_context(self):
        desc = get_current_month.description.lower()
        assert "月" in desc or "时间" in desc or "报告" in desc, (
            "get_current_month 的 description 应该关联月份或报告场景"
        )


class TestGenerateExternalDataDescription:
    """generate_external_data 的 description 应该明确输入参数和数据范围。"""

    def test_description_not_empty_and_reasonable_length(self):
        _assert_description(generate_external_data, min_length=50)

    def test_description_includes_input_params(self):
        desc = generate_external_data.description.lower()
        assert "用户" in desc or "月份" in desc or "id" in desc, (
            "generate_external_data 的 description 应该说明需要 user_id 和 month"
        )

    def test_description_includes_call_timing(self):
        desc = generate_external_data.description.lower()
        assert "当" in desc or "已购买" in desc or "绑定" in desc or "报告" in desc, (
            "generate_external_data 的 description 应该包含调用时机（如'当用户已购买且已绑定设备时'）"
        )
