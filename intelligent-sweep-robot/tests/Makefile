# -*- coding: UTF-8 -*-
# @Author ：suke
# @Version ：1.0
# @Date ：2026-05-06 23:19:19
# @Description：
# tests目录下的测试命令入口

THIS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))
TEST_ROOT := $(dir $(THIS_MAKEFILE))
PROJECT_ROOT := $(abspath $(TEST_ROOT)/..)
PROJECT_PYTHON := $(PROJECT_ROOT)/.venv/bin/python
PARENT_PYTHON := $(PROJECT_ROOT)/../.venv/bin/python

PYTHON ?= $(if $(wildcard $(PROJECT_PYTHON)),$(PROJECT_PYTHON),$(if $(wildcard $(PARENT_PYTHON)),$(PARENT_PYTHON),python3))
PYTEST_ARGS ?= -q
PYTEST_TARGET ?= $(PROJECT_ROOT)/tests

.PHONY: test unit e2e

test:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) -m pytest $(PYTEST_TARGET) $(PYTEST_ARGS)

unit:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) -m pytest $(PROJECT_ROOT)/tests/unit $(PYTEST_ARGS)

e2e:
	PYTHONPATH=$(PROJECT_ROOT) $(PYTHON) -m pytest $(PROJECT_ROOT)/tests/e2e $(PYTEST_ARGS)
