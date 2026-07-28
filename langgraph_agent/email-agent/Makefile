VENV := /Users/suke/Python/Agent/.venv/bin/python
PIP  := /Users/suke/Python/Agent/.venv/bin/pip
UVICORN := /Users/suke/Python/Agent/.venv/bin/uvicorn

.PHONY: help install test web tui daemon db-up db-down db-init test-all test-step1 test-step2 test-step3 test-step4 test-step8 clean

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## 安装所有依赖
	$(PIP) install -r ../requirements.txt

# ── 运行模式 ──

test: ## CLI 测试模式（单封邮件 + 交互审批）
	$(VENV) main.py --test

WEB_PORT ?= 8000

web: ## FastAPI Web 界面 (http://localhost:$(WEB_PORT))
	@lsof -ti:$(WEB_PORT) | xargs kill 2>/dev/null || true
	$(VENV) main.py --web

tui: ## Textual 终端界面
	$(VENV) main.py --tui

daemon: ## 后台 Agent-Loop（无 UI）
	$(VENV) main.py --daemon

# ── 数据库 ──

db-up: ## 启动 Docker MySQL
	@docker ps --filter name=email-agent-mysql --format '{{.Names}}' | grep -q email-agent-mysql && \
		echo "MySQL container already running" || \
		docker run -d --name email-agent-mysql \
			-e MYSQL_ROOT_PASSWORD=suke041230 \
			-e MYSQL_DATABASE=email_agent \
			-p 3306:3306 mysql:8.0
	@echo "Waiting for MySQL to be ready..."
	@sleep 5
	@echo "MySQL ready on localhost:3306"

db-down: ## 停止 Docker MySQL
	docker stop email-agent-mysql 2>/dev/null; docker rm email-agent-mysql 2>/dev/null; echo "MySQL container removed"

db-init: ## 初始化数据库表
	$(VENV) -c "import asyncio; from persistence.connection import init_db; asyncio.run(init_db()); print('Tables created')"

db-reset: ## 重置数据库（删除并重建）
	$(VENV) -c "import asyncio; exec('async def r(): import aiomysql, os; from dotenv import load_dotenv; load_dotenv(); p=await aiomysql.create_pool(host=os.getenv(\"MYSQL_HOST\",\"127.0.0.1\"),port=int(os.getenv(\"MYSQL_PORT\",\"3306\")),user=os.getenv(\"MYSQL_USER\",\"root\"),password=os.getenv(\"MYSQL_PASSWORD\",\"\"),db=os.getenv(\"MYSQL_DATABASE\",\"email_agent\"),minsize=1,maxsize=2,autocommit=True); cur=await (await p.acquire()).cursor(); await cur.execute(\"DROP TABLE IF EXISTS review_queue, email_history\"); p.close(); await p.wait_closed()\nimport asyncio; asyncio.run(r()))"
	$(MAKE) db-init
	echo "Database reset complete"

# ── 测试 ──

test-all: ## 运行所有 E2E 测试
	@for step in test_step1_mysql test_step2_persistence test_step3_worker test_step4_service test_step8_e2e; do \
		echo "\n=== Running $$step ==="; \
		$(VENV) tests/$$step.py || exit 1; \
	done
	@echo "\nAll tests passed!"

test-step1: ## Step 1: MySQL 连接测试
	$(VENV) tests/test_step1_mysql.py

test-step2: ## Step 2: 持久化层测试
	$(VENV) tests/test_step2_persistence.py

test-step3: ## Step 3: Worker Pool 测试
	$(VENV) tests/test_step3_worker.py

test-step4: ## Step 4: Service 层测试
	$(VENV) tests/test_step4_service.py

test-step8: ## Step 8: E2E 集成测试
	$(VENV) tests/test_step8_e2e.py

# ── 工具 ──

clean: ## 清理 __pycache__ 和日志
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf logs/*
	@echo "Clean complete"

lint: ## 检查语法错误
	$(VENV) -m py_compile main.py
	$(VENV) -m py_compile graph.py
	@for f in $$(find persistence service server tui loop agents tools rag -name "*.py" 2>/dev/null); do \
		$(VENV) -m py_compile $$f || exit 1; \
	done
	@echo "Syntax check passed"
