# UV + Python 本地包启动指南

本文档介绍如何使用 `uv` 管理 Python 项目，以及如何通过 `python -m` 方式运行本项目的各个模块。

---

## 1. UV 包管理器

### 1.1 什么是 uv

[uv](https://github.com/astral-sh/uv) 是一个极速的 Python 包管理器和项目管理工具，用 Rust 编写，可以替代 `pip`、`pip-tools`、`virtualenv`、`pyenv` 等工具。

### 1.2 安装 uv

```bash
# macOS (Homebrew)
brew install uv

# 或使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.3 项目初始化

```bash
cd /Users/suke/Python/Agent

# 方式一：从 requirements.txt 导入依赖
uv init --no-readme
uv add --requirements requirements.txt

# 也可以直接使用如下命令
uv venv 
uv pip install -r requirements.txt
# 使用 uv venv 之后即是传统做法 source .venv/bin/activate 若是要使用pip的话 通过如下命令
uv pip install pip
# 之后即可传统使用
pip install -r requirements.txt

# 方式二：手动添加依赖
uv add openai langchain-core langchain-community dashscope jq google-adk
```

初始化后项目结构会新增：

```
Agent/
├── .venv/              # 虚拟环境（自动生成）
├── pyproject.toml      # 项目配置（自动生成）
├── uv.lock             # 依赖锁文件（自动生成）
├── requirements.txt    # 原始依赖列表
└── ...
```

### 1.4 常用 uv 命令

| 命令 | 说明 |
|------|------|
| `uv add <package>` | 添加依赖 |
| `uv add --dev <package>` | 添加开发依赖 |
| `uv remove <package>` | 移除依赖 |
| `uv sync` | 根据 uv.lock 同步安装依赖 |
| `uv run python <script>` | 在虚拟环境中运行 Python 脚本 |
| `uv run python -m <module>` | 在虚拟环境中以模块方式运行 |
| `uv pip list` | 查看已安装的包 |
| `uv python install 3.12` | 安装指定 Python 版本 |

---

## 2. Python 本地包启动 (`python -m`)

### 2.1 原理说明

`python -m <module>` 的含义是**将 Python 文件作为模块运行**，而不是直接执行文件路径。

**文件路径方式 vs 模块方式：**

```bash
# 文件路径方式（不推荐）
python AIGC/llm_agent_demo/demo_01.py

# 模块方式（推荐）
python -m AIGC.llm_agent_demo.demo_01
```

**模块方式的优势：**
- import 路径始终以项目根目录为基准，不会出现相对导入报错
- 包的 `__init__.py` 会被正确执行
- 与部署环境一致

### 2.2 前提条件

使用 `python -m` 需要满足：

1. 每个目录下有 `__init__.py`（本项目已具备）
2. 以项目根目录为工作路径
3. 目标文件有 `if __name__ == "__main__":` 入口

### 2.3 路径转换规则

```
文件路径                              →    模块路径
AIGC/llm_agent_demo/demo_01.py      →    AIGC.llm_agent_demo.demo_01
AIGC/llm_agent_demo/chain_demo_01.py →    AIGC.llm_agent_demo.chain_demo_01
story_agent/story_flow_agent.py      →    story_agent.story_flow_agent
mcp_server/my_mcp_server.py          →    mcp_server.my_mcp_server
agent_team/weather_agent/agent.py    →    agent_team.weather_agent.agent
```

规则很简单：**把 `/` 换成 `.`，去掉 `.py` 后缀**。

---

## 3. 本项目各模块启动命令

### 3.1 AIGC - 核心学习模块

```bash
# Google GenAI 基础
uv run python -m AIGC.google.gen_ai_01

# LLM Agent 基础示例
uv run python -m AIGC.llm_agent_demo.demo_01
uv run python -m AIGC.llm_agent_demo.open_ai_demo_01
uv run python -m AIGC.llm_agent_demo.langchain_demo_01
uv run python -m AIGC.llm_agent_demo.finance_text_category
uv run python -m AIGC.llm_agent_demo.chain_demo_01
uv run python -m AIGC.llm_agent_demo.prompt_demo_01
uv run python -m AIGC.llm_agent_demo.prompt_demo_02
uv run python -m AIGC.llm_agent_demo.human_messages
uv run python -m AIGC.llm_agent_demo.chain_history_memory
uv run python -m AIGC.llm_agent_demo.long_history_memory
uv run python -m AIGC.llm_agent_demo.csv_loader
uv run python -m AIGC.llm_agent_demo.json_load

# OpenAI Agents SDK
uv run python -m AIGC.open_ai_agents.open_agent_01
uv run python -m AIGC.open_ai_agents.auto_mode
uv run python -m AIGC.open_ai_agents.agent_conditional
uv run python -m AIGC.open_ai_agents.agent_streaming
uv run python -m AIGC.open_ai_agents.analysis_agents

# 金融研究 Agent
uv run python -m AIGC.open_ai_agents.financial_research_agent.main
```

### 3.2 其他模块

```bash
# 故事生成工作流
uv run python -m story_agent.story_flow_agent

# MCP 服务端
uv run python -m mcp_server.my_mcp_server

# MCP 客户端
uv run python -m mcp_client.agent

# MCP Agent
uv run python -m mcp_agent.agent

# 天气 Agent
uv run python -m agent_team.weather_agent.agent

# 技能 Agent
uv run python -m skills_agent.agent

# 人工确认示例
uv run python -m human_tool_confirmation.agent

# 多工具 Agent
uv run python -m parent_folder.multi_tool_agent.agent
```

### 3.3 financial-advisor 独立项目

`financial-advisor` 有自己的 `pyproject.toml`，需要单独操作：

```bash
cd financial-advisor
uv sync
uv run python -m financial_advisor
```

---

## 4. 可选：配置 Shell 别名

如果嫌每次输入 `uv run python -m` 太长，可以添加别名：

```bash
# 添加到 ~/.zshrc
alias py="uv run python -m"
```

之后就可以简化命令：

```bash
py AIGC.llm_agent_demo.demo_01
py story_agent.story_flow_agent
py mcp_server.my_mcp_server
```

---

## 5. 常见问题

### Q: 报错 `ModuleNotFoundError`

**原因：** 工作目录不是项目根目录。

**解决：** 确保在 `/Users/suke/Python/Agent/` 下执行命令：
```bash
cd /Users/suke/Python/Agent
uv run python -m AIGC.llm_agent_demo.demo_01
```

### Q: 报错 `No module named 'xxx'`

**原因：** 依赖未安装。

**解决：**
```bash
uv add xxx
# 或
uv sync
```

### Q: Python 版本不对

**解决：**
```bash
# 查看当前虚拟环境 Python 版本
uv run python --version

# 安装并指定 Python 版本
uv python install 3.12
uv python pin 3.12
uv sync
```

### Q: 不想每次都输 uv run

**解决：** 手动激活虚拟环境：
```bash
source .venv/bin/activate
python -m AIGC.llm_agent_demo.demo_01

# 退出虚拟环境
deactivate
```
