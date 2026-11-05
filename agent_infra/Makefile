# agent_infra 启动与开发命令
# 依赖：uv、git；LLM 冒烟需 .env 里有 ZAI_API_KEY（cp .env.example .env）

# 各 Agent A2A server 端口 / harness web 端口（一进程一 agent）
PORT_PLANNING := 8103
PORT_CR := 8101
PORT_WEB := 8100
PORT_REQUIREMENT := 8104
PORT_STRATEGY := 8105
PORT_REPORT := 8109
PORT_TEST_RECALL := 8110
PORT_CHANGE_REPORT := 8111
PORT_CASE := 8106
PORT_SCRIPT := 8107
PORT_DIAGNOSE := 8108

# 可选加载 .env（不存在则跳过，只有烧 LLM 的目标需要它）
ENV_HOOK := $(shell test -f .env && echo "set -a; . ./.env; set +a;")

# eval-ab 无人值守：起服时注入 HITL auto-answer（评测没人答题，无超时等待会挂死）
EVAL_ENV := AGENT_INFRA_HITL_AUTO=1

.DEFAULT_GOAL := help

.PHONY: help deps repo server server-cr server-planning server-test-recall server-case server-script server-change-report server-diagnose web dev down test lint smoke smoke-hitl knowledge-index eval-retrieval smoke-rag smoke-agents smoke-sdlc smoke-review eval eval-ab eval-offline eval-update eval-report judge-calibrate smoke-mcp clean

help: ## 显示本帮助
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

deps: ## 安装依赖（uv sync，含 dev 组）
	uv sync

repo: ## 构建/重建种子缺陷仓库 fixtures/demo_repo
	uv run python -m fixtures.build_demo_repo

server: server-cr ## 前台启动 CR Agent A2A server（:8101，烧 LLM）

server-cr: ## 前台启动 CR Agent（:8101）
	@$(ENV_HOOK) uv run python agent_server.py --agent cr_agent

server-planning: ## 前台启动 Planning Agent（:8103）
	@$(ENV_HOOK) uv run python agent_server.py --agent planning_agent

server-test-recall: ## 前台启动 Test Recall Agent（:8110）
	@$(ENV_HOOK) uv run python agent_server.py --agent test_recall_agent

server-case: ## 前台启动 Case Agent（:8106）
	@$(ENV_HOOK) uv run python agent_server.py --agent case_agent

server-script: ## 前台启动 Script Agent（:8107）
	@$(ENV_HOOK) uv run python agent_server.py --agent script_agent

server-change-report: ## 前台启动 Change Report Agent（:8111）
	@$(ENV_HOOK) uv run python agent_server.py --agent change_report_agent

server-diagnose: ## 前台启动 Diagnose Agent（:8108）
	@$(ENV_HOOK) uv run python agent_server.py --agent diagnose_agent

web: ## 前台启动 harness web（:8100）
	uv run python app.py

# opt-in 真实 MCP smoke：真实 GitHub MCP server 是外部二进制/Docker（npx/docker
# 命令），不进测试、不进 CI——仅在显式提供 env 时手动执行。凭证只经 env 注入，
# 不写入任何文件/trace。用法：
#   AGENT_INFRA_MCP_CMD='npx -y @modelcontextprotocol/server-github' \
#   MCP_GITHUB_TOKEN=ghp_xxx make smoke-mcp
smoke-mcp: ## 真实 MCP smoke（opt-in，需 AGENT_INFRA_MCP_CMD + MCP_GITHUB_TOKEN）
	@if [ -z "$(AGENT_INFRA_MCP_CMD)" ]; then \
		echo "需要 AGENT_INFRA_MCP_CMD（真实 MCP server 启动命令，如 'npx -y @modelcontextprotocol/server-github' 或 docker 命令）"; \
		echo "用法: AGENT_INFRA_MCP_CMD='...' MCP_GITHUB_TOKEN=xxx make smoke-mcp"; \
		exit 1; fi
	@if [ -z "$(MCP_GITHUB_TOKEN)" ]; then \
		echo "需要 MCP_GITHUB_TOKEN（GitHub PAT，只经 env 注入）"; exit 1; fi
	@$(ENV_HOOK) AGENT_INFRA_MCP_CMD="$(AGENT_INFRA_MCP_CMD)" MCP_GITHUB_TOKEN="$(MCP_GITHUB_TOKEN)" \
		uv run python scripts/smoke_mcp.py

dev: ## 后台启动 10 个 agent server + web（日志在 runs/*.log）
	@mkdir -p runs
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent planning_agent > runs/planning.log 2>&1 & echo "planning pid $$! -> :$(PORT_PLANNING) (runs/planning.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent cr_agent > runs/cr.log 2>&1 & echo "cr pid $$! -> :$(PORT_CR) (runs/cr.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent requirement_agent > runs/requirement.log 2>&1 & echo "requirement pid $$! -> :$(PORT_REQUIREMENT) (runs/requirement.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent strategy_agent > runs/strategy.log 2>&1 & echo "strategy pid $$! -> :$(PORT_STRATEGY) (runs/strategy.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent test_recall_agent > runs/test_recall.log 2>&1 & echo "test_recall pid $$! -> :$(PORT_TEST_RECALL) (runs/test_recall.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent change_report_agent > runs/change_report.log 2>&1 & echo "change_report pid $$! -> :$(PORT_CHANGE_REPORT) (runs/change_report.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent case_agent > runs/case.log 2>&1 & echo "case pid $$! -> :$(PORT_CASE) (runs/case.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent script_agent > runs/script.log 2>&1 & echo "script pid $$! -> :$(PORT_SCRIPT) (runs/script.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent diagnose_agent > runs/diagnose.log 2>&1 & echo "diagnose pid $$! -> :$(PORT_DIAGNOSE) (runs/diagnose.log)"
	@$(ENV_HOOK) nohup uv run python agent_server.py --agent report_agent > runs/report.log 2>&1 & echo "report pid $$! -> :$(PORT_REPORT) (runs/report.log)"
	@nohup uv run python app.py > runs/web.log 2>&1 & echo "web pid $$! -> :$(PORT_WEB) (runs/web.log)"
	@echo "打开 http://127.0.0.1:$(PORT_WEB)/ （make down 停止）"

down: ## 停止 dev 启动的进程
	@for p in $(PORT_WEB) $(PORT_CR) $(PORT_PLANNING) $(PORT_REQUIREMENT) $(PORT_STRATEGY) $(PORT_TEST_RECALL) $(PORT_CHANGE_REPORT) $(PORT_CASE) $(PORT_SCRIPT) $(PORT_DIAGNOSE) $(PORT_REPORT); do pid=$$(lsof -ti tcp:$$p); if [ -n "$$pid" ]; then kill $$pid && echo "killed :$$p (pid $$pid)"; else echo ":$$p not running"; fi; done

test: ## 全量单测（不烧 LLM）
	uv run pytest -q

lint: ## ruff 检查（含自动修复）
	uv run ruff check . --fix

smoke: ## 冒烟自检：服务是否活着（需先 make dev）
	@curl -sf http://127.0.0.1:$(PORT_WEB)/commits >/dev/null && echo "web OK" || echo "web DOWN"
	@for p in $(PORT_PLANNING):planning_agent $(PORT_REQUIREMENT):requirement_agent $(PORT_STRATEGY):strategy_agent $(PORT_CR):cr_agent $(PORT_TEST_RECALL):test_recall_agent $(PORT_CHANGE_REPORT):change_report_agent $(PORT_CASE):case_agent $(PORT_SCRIPT):script_agent $(PORT_DIAGNOSE):diagnose_agent $(PORT_REPORT):report_agent; do port=$${p%%:*}; name=$${p##*:}; curl -sf http://127.0.0.1:$$port/.well-known/agent-card.json >/dev/null && echo "$$name card OK" || echo "$$name server DOWN"; done

smoke-hitl: ## HITL 真实冒烟：defect-5 关召回问人→答 0.20→命中（需先 make dev）
	@$(ENV_HOOK) uv run python scripts/smoke_hitl.py

knowledge-index: ## 重建知识库索引（knowledge/*.md → runs/knowledge/）
	@$(ENV_HOOK) uv run python scripts/knowledge_index.py

eval-retrieval: ## 检索 Benchmark（hit@1/@3 + MRR 门禁，掉点 exit 1）
	@$(ENV_HOOK) uv run python eval/retrieval.py

smoke-rag: ## RAG 真实冒烟：defect-5 知识层开/关对照（需先 make dev）
	@$(ENV_HOOK) uv run python scripts/smoke_rag.py

smoke-agents: ## 做实链路真实冒烟：context_note → planning 选新链 → execution_report.md
	@$(MAKE) -s down
	@mkdir -p runs
	@for a in planning_agent:$(PORT_PLANNING) requirement_agent:$(PORT_REQUIREMENT) strategy_agent:$(PORT_STRATEGY) cr_agent:$(PORT_CR) test_recall_agent:$(PORT_TEST_RECALL) case_agent:$(PORT_CASE) script_agent:$(PORT_SCRIPT) change_report_agent:$(PORT_CHANGE_REPORT) diagnose_agent:$(PORT_DIAGNOSE) report_agent:$(PORT_REPORT); do n=$${a%%:*}; p=$${a##*:}; $(ENV_HOOK) nohup uv run python agent_server.py --agent $$n > runs/$$n.log 2>&1 & echo "$$n pid $$! -> :$$p (runs/$$n.log)"; done
	@for i in $$(seq 1 60); do ok=1; for p in $(PORT_PLANNING) $(PORT_REQUIREMENT) $(PORT_STRATEGY) $(PORT_CR) $(PORT_TEST_RECALL) $(PORT_CASE) $(PORT_SCRIPT) $(PORT_REPORT) $(PORT_CHANGE_REPORT) $(PORT_DIAGNOSE); do curl -sf http://127.0.0.1:$$p/.well-known/agent-card.json >/dev/null || ok=0; done; [ $$ok -eq 1 ] && break; sleep 0.5; done; [ $$ok -eq 1 ] || { echo "server 未就绪（见 runs/<agent>.log）"; $(MAKE) -s down; exit 1; }
	@$(ENV_HOOK) uv run python scripts/smoke_agents.py; rc=$$?; $(MAKE) -s down; exit $$rc

smoke-sdlc: ## 八期全链真实冒烟：召回→变更分析报告→用例→脚本→执行→双报告（烧 LLM）
	@$(MAKE) -s down
	@mkdir -p runs
	@for a in planning_agent:$(PORT_PLANNING) requirement_agent:$(PORT_REQUIREMENT) strategy_agent:$(PORT_STRATEGY) cr_agent:$(PORT_CR) test_recall_agent:$(PORT_TEST_RECALL) change_report_agent:$(PORT_CHANGE_REPORT) case_agent:$(PORT_CASE) script_agent:$(PORT_SCRIPT) diagnose_agent:$(PORT_DIAGNOSE) report_agent:$(PORT_REPORT); do n=$${a%%:*}; p=$${a##*:}; $(ENV_HOOK) nohup uv run python agent_server.py --agent $$n > runs/$$n.log 2>&1 & echo "$$n pid $$! -> :$$p (runs/$$n.log)"; done
	@for i in $$(seq 1 60); do ok=1; for p in $(PORT_PLANNING) $(PORT_REQUIREMENT) $(PORT_STRATEGY) $(PORT_CR) $(PORT_TEST_RECALL) $(PORT_CHANGE_REPORT) $(PORT_CASE) $(PORT_SCRIPT) $(PORT_DIAGNOSE) $(PORT_REPORT); do curl -sf http://127.0.0.1:$$p/.well-known/agent-card.json >/dev/null || ok=0; done; [ $$ok -eq 1 ] && break; sleep 0.5; done; [ $$ok -eq 1 ] || { echo "server 未就绪（见 runs/<agent>.log）"; $(MAKE) -s down; exit 1; }
	@$(ENV_HOOK) uv run python scripts/smoke_sdlc.py; rc=$$?; $(MAKE) -s down; exit $$rc

smoke-review: ## 九期审阅回路真实冒烟：park→reject→replan(round2)→accept→蒸馏（烧 LLM）
	@$(MAKE) -s down
	@mkdir -p runs
	@for a in planning_agent:$(PORT_PLANNING) requirement_agent:$(PORT_REQUIREMENT) strategy_agent:$(PORT_STRATEGY) cr_agent:$(PORT_CR) test_recall_agent:$(PORT_TEST_RECALL) change_report_agent:$(PORT_CHANGE_REPORT) case_agent:$(PORT_CASE) script_agent:$(PORT_SCRIPT) diagnose_agent:$(PORT_DIAGNOSE) report_agent:$(PORT_REPORT); do n=$${a%%:*}; p=$${a##*:}; $(ENV_HOOK) nohup uv run python agent_server.py --agent $$n > runs/$$n.log 2>&1 & echo "$$n pid $$! -> :$$p (runs/$$n.log)"; done
	@for i in $$(seq 1 60); do ok=1; for p in $(PORT_PLANNING) $(PORT_REQUIREMENT) $(PORT_STRATEGY) $(PORT_CR) $(PORT_TEST_RECALL) $(PORT_CHANGE_REPORT) $(PORT_CASE) $(PORT_SCRIPT) $(PORT_DIAGNOSE) $(PORT_REPORT); do curl -sf http://127.0.0.1:$$p/.well-known/agent-card.json >/dev/null || ok=0; done; [ $$ok -eq 1 ] && break; sleep 0.5; done; [ $$ok -eq 1 ] || { echo "server 未就绪（见 runs/<agent>.log）"; $(MAKE) -s down; exit 1; }
	@$(ENV_HOOK) uv run python scripts/smoke_review.py; rc=$$?; $(MAKE) -s down; exit $$rc

eval-ab: ## A/B 评测：自起服务器（HITL auto-answer），memory 开/关各跑一遍，比 hit_rate/FP
	@$(MAKE) -s down
	@mkdir -p runs
	@for a in planning_agent:$(PORT_PLANNING) cr_agent:$(PORT_CR) requirement_agent:$(PORT_REQUIREMENT) strategy_agent:$(PORT_STRATEGY) test_recall_agent:$(PORT_TEST_RECALL) case_agent:$(PORT_CASE) script_agent:$(PORT_SCRIPT) change_report_agent:$(PORT_CHANGE_REPORT) diagnose_agent:$(PORT_DIAGNOSE) report_agent:$(PORT_REPORT); do n=$${a%%:*}; p=$${a##*:}; $(ENV_HOOK) $(EVAL_ENV) nohup uv run python agent_server.py --agent $$n > runs/$$n.log 2>&1 & echo "$$n pid $$! -> :$$p (HITL auto)"; done
	@nohup uv run python app.py > runs/web.log 2>&1 & echo "web pid $$! -> :$(PORT_WEB)"
	@for i in $$(seq 1 60); do curl -sf http://127.0.0.1:$(PORT_CR)/.well-known/agent-card.json >/dev/null && curl -sf http://127.0.0.1:$(PORT_SCRIPT)/.well-known/agent-card.json >/dev/null && curl -sf http://127.0.0.1:$(PORT_PLANNING)/.well-known/agent-card.json >/dev/null && break; sleep 0.5; done
	@$(ENV_HOOK) uv run python eval/ab.py; rc=$$?; $(MAKE) -s down; exit $$rc

BENCH_ARGS :=

eval: ## Benchmark 门禁：自起 10 agent（HITL auto；REVIEW auto 注 benchmark 进程）跑 defect-1..5 → 打分对基线，掉点 exit 1
	@$(MAKE) -s down
	@mkdir -p runs
	@for a in planning_agent:$(PORT_PLANNING) cr_agent:$(PORT_CR) requirement_agent:$(PORT_REQUIREMENT) strategy_agent:$(PORT_STRATEGY) test_recall_agent:$(PORT_TEST_RECALL) case_agent:$(PORT_CASE) script_agent:$(PORT_SCRIPT) change_report_agent:$(PORT_CHANGE_REPORT) diagnose_agent:$(PORT_DIAGNOSE) report_agent:$(PORT_REPORT); do n=$${a%%:*}; p=$${a##*:}; $(ENV_HOOK) $(EVAL_ENV) nohup uv run python agent_server.py --agent $$n > runs/$$n.log 2>&1 & echo "$$n pid $$! -> :$$p (HITL auto)"; done
	@for i in $$(seq 1 60); do ok=1; for p in $(PORT_PLANNING) $(PORT_CR) $(PORT_REQUIREMENT) $(PORT_STRATEGY) $(PORT_TEST_RECALL) $(PORT_CASE) $(PORT_SCRIPT) $(PORT_REPORT) $(PORT_CHANGE_REPORT) $(PORT_DIAGNOSE); do curl -sf http://127.0.0.1:$$p/.well-known/agent-card.json >/dev/null || ok=0; done; [ $$ok -eq 1 ] && break; sleep 0.5; done; [ $$ok -eq 1 ] || { echo "server 未就绪（见 runs/<agent>.log）"; $(MAKE) -s down; exit 1; }
	@$(ENV_HOOK) AGENT_INFRA_REVIEW_AUTO=1 uv run python eval/benchmark.py $(BENCH_ARGS); rc=$$?; $(MAKE) -s down; exit $$rc

eval-offline: ## 离线重放打分（零 LLM）：make eval-offline FROM=runs/smoke-agents
	@if [ -z "$(FROM)" ]; then echo "用法: make eval-offline FROM=<run 目录或父目录>"; exit 2; fi
	@$(ENV_HOOK) uv run python eval/benchmark.py --from $(FROM)

eval-update: ## 首跑建基线/人审后固化基线（在线跑一遍并 --update-baseline）
	@$(MAKE) -s eval BENCH_ARGS=--update-baseline

eval-report: ## 模型对比+归因报告（离线零 LLM）：runs/bench/report.md
	@$(ENV_HOOK) uv run python eval/report.py

judge-calibrate: ## 判定链 judge 校准（烧 ~14 次小 LLM 调用）：准确率 <0.9 不可上岗
	@$(ENV_HOOK) uv run python eval/judge.py

clean: ## 清理运行产物 runs/（含 trace、日志、adk_sessions.db）
	rm -rf runs
