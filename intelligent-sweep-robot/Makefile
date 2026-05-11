# -*- coding: UTF-8 -*-
# @Author ：suke
# @Version ：1.0
# @Date ：2026-05-08 23:50:00
# @Description：
# 项目根目录命令入口
#
# 命令委托说明：
#   test / unit / e2e 三个 target 共享同一段 recipe，
#   通过 $(MAKE) -C tests $@ 将实际执行委托给 tests/Makefile。
#   其中 $@ 是 Makefile 自动变量，表示当前被调用的 target 名称。
#   例如：执行 `make unit` 时，$@ 的值为 "unit"，
#   实际执行的是 `make -C tests unit`（进入 tests 目录执行单元测试）。

THIS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_ROOT := $(patsubst %/,%,$(dir $(THIS_MAKEFILE)))
PROJECT_PYTHON := $(PROJECT_ROOT)/.venv/bin/python
PARENT_PYTHON := $(PROJECT_ROOT)/../.venv/bin/python

PYTHON ?= $(if $(wildcard $(PROJECT_PYTHON)),$(PROJECT_PYTHON),$(if $(wildcard $(PARENT_PYTHON)),$(PARENT_PYTHON),python3))

# 默认 target：输入 make 不带参数时，显示帮助信息
.DEFAULT_GOAL := help

.PHONY: help test unit e2e build-vector-store test-tool-calling run-agent

help:
	@echo ""
	@echo "🚀 智扫通 Agent 项目命令速查"
	@echo "═══════════════════════════════════════════════════════════"
	@echo ""
	@echo "  make help                显示本帮助信息"
	@echo "  make test                运行全部测试（委托到 tests/Makefile）"
	@echo "  make unit                运行单元测试（委托到 tests/Makefile）"
	@echo "  make e2e                 运行端到端测试（委托到 tests/Makefile）"
	@echo "  make build-vector-store  从 data/ 构建 Chroma 向量库"
	@echo "  make test-tool-calling   运行 LLM Tool Calling 验证脚本"
	@echo "  make run-agent           启动 Agent 交互式命令行"
	@echo ""
	@echo "═══════════════════════════════════════════════════════════"
	@echo ""

# 委托测试命令到 tests/Makefile
# test / unit / e2e 三个 target 复用同一段 recipe，$@ 自动匹配当前 target 名
test unit e2e:
	$(MAKE) -C tests $@

# 构建向量库：从 data/ 目录加载知识文件并写入 Chroma
build-vector-store:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) $(PROJECT_ROOT)/tests/e2e/build_vector_store.py

# 运行 Tool Calling 验证脚本
# 验证 LLM 是否能正确识别、选择并调用 Agent 工具
test-tool-calling:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) $(PROJECT_ROOT)/tests/e2e/test_tool_calling.py

# 启动 Agent 交互式命令行
run-agent:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) $(PROJECT_ROOT)/run_agent.py
