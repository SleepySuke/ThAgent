# 智扫通 (Intelligent Sweep Robot)

基于 **LangChain** 构建的扫地机器人智能客服 Agent 实验项目。以 toC 客服场景为载体，验证 RAG 知识库问答、工具调用、Middleware 观测、动态 Prompt 切换和使用报告生成等 Agent 核心能力。

## 架构

```
用户 (Streamlit / CLI)
  ↓
react_agent.py          ← Agent 编排层 (langchain.agents.create_agent)
  ├── middleware/
  │   ├── prompt_switcher.py   ← 动态 Prompt 切换 (main / report)
  │   └── agent_middleware.py  ← 执行链路观测 (before/after model, tool monitor)
  ├── tools/                   ← 6 个 LangChain Tool
  │   ├── rag_summarize        ← 知识库检索总结
  │   ├── get_weather          ← 天气查询 (Mock)
  │   ├── get_user_location    ← 位置查询 (Mock)
  │   ├── get_user_id          ← 用户 ID (Mock)
  │   ├── get_current_month    ← 当前月份
  │   └── generate_external_data ← 使用数据生成 (Mock)
  ├── service/
  │   ├── rag_service.py       ← RAG 检索 + LLM 总结
  │   └── vector_store.py      ← Chroma 向量库 (构建 / 检索 / 同步)
  ├── model/factory.py         ← 模型工厂 (通义千问, 单例)
  └── utils/                   ← 配置 / 文件 / 日志 / Prompt / 路径
```

## 项目结构

```
intelligent-sweep-robot/
├── app.py                  # Streamlit Web 界面
├── react_agent.py          # Agent 编排 (create / execute / execute_stream)
├── run_agent.py            # CLI 交互式命令行
├── Makefile                # 命令入口
├── config/                 # YAML 配置
│   ├── project_config.yaml # 项目 & 模型配置
│   ├── agent_config.yaml   # Agent & Middleware 开关
│   ├── chroma_config.yaml  # Chroma 向量库配置
│   └── rag_config.yaml     # RAG 运行时配置
├── prompts/                # Prompt 模板
│   ├── main_prompt.txt     # Agent 主提示词
│   ├── rag_prompt.txt      # RAG 总结提示词
│   └── report_prompt.txt   # 报告生成提示词
├── data/                   # 知识库文件 (txt / pdf)
├── tools/                  # Agent 工具
├── service/                # RAG & 向量库服务
├── middleware/              # Middleware
├── model/                  # 模型工厂
├── utils/                  # 工具模块
├── tests/
│   ├── unit/               # 单元测试
│   └── e2e/                # 端到端测试 & 验证脚本
└── logs/                   # 运行日志
```

## 快速开始

### 环境要求

- Python 3.12+

### 安装

本项目共用父目录 `Agent/` 的 `.venv` 虚拟环境，使用 `requirements.txt` 安装依赖：

```bash
# 在 Agent/ 目录下
cd /path/to/Agent

# 创建虚拟环境（如尚未创建）
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r intelligent-sweep-robot/requirements.txt
```

### 配置

创建 `.env` 文件：

```env
DASHSCOPE_API_KEY=<your-dashscope-api-key>
```

默认使用通义千问 (`qwen-plus` / `tongyi-embedding-vision-plus`)，可在 `config/project_config.yaml` 中切换。

### 构建向量库

```bash
make build-vector-store
```

### 启动 Web 界面

```bash
make run-web
```

### 启动 CLI 交互

```bash
make run-agent
```

## Makefile 命令

| 命令 | 说明 |
|------|------|
| `make help` | 显示帮助 |
| `make test` | 运行全部测试 |
| `make unit` | 运行单元测试 |
| `make e2e` | 运行端到端测试 |
| `make build-vector-store` | 从 data/ 构建 Chroma 向量库 |
| `make test-tool-calling` | 运行 Tool Calling 验证脚本 |
| `make run-agent` | 启动 CLI 交互式命令行 |
| `make run-web` | 启动 Streamlit Web 界面 |

## 功能

### 🤖 智能问答

通过 RAG 从知识库检索产品资料，回答：
- **购买前**：功能对比、价格套餐、适用场景推荐
- **购买后**：操作指导、故障排查、耗材维护

### 📊 使用报告生成

- 已购买用户：调用工具获取使用数据，结合知识库生成个性化报告
- 未购买用户：提供购买引导和示例报告

### 🔧 工具调用

Agent 根据用户意图自动选择工具：

| 工具 | 用途 | 状态 |
|------|------|------|
| `rag_summarize` | 知识库检索总结 | 真实 |
| `get_weather` | 天气查询 | Mock |
| `get_user_location` | 位置查询 | Mock |
| `get_user_id` | 用户 ID | Mock |
| `get_current_month` | 当前月份 | 真实 |
| `generate_external_data` | 使用数据生成 | Mock |

### 🎯 动态 Prompt 切换

根据用户消息内容自动切换 system prompt——识别到报告意图时使用 `report_prompt`，其余场景使用 `main_prompt`。`rag_prompt` 由 `RagSummarizeService` 内部使用。

### 📋 历史对话

- 对话自动持久化到本地文件，刷新不丢失
- 侧边栏显示历史对话列表，以首个问题为标题
- 支持切换、删除历史对话

## 技术栈

| 技术 | 用途 |
|------|------|
| LangChain | Agent 编排、工具定义、Middleware |
| Chroma | 本地向量存储与语义检索 |
| 通义千问 (DashScope) | 聊天模型 + Embedding 模型 |
| Streamlit | Web 交互界面 |
| Pydantic | 配置模型校验 |
| pytest | 单元测试 + 端到端测试 |

## 设计笔记

- **模型工厂**：基于抽象基类的单例模式，按 provider 返回具体实现
- **Middleware 注入**：在 `create_agent` 创建时直接传入，非运行时通过 callbacks
- **Prompt 职责分离**：Agent 层只处理 main/report 切换，rag_prompt 归属 RAG 服务内部
- **懒加载单例**：`RagSummarizeService` 在 `rag_summarize` 工具首次调用时创建，避免重复初始化 Chroma

详细设计文档见飞书文档 [I.S.R](https://jcngf8hu5bzo.feishu.cn/wiki/Rr9lwdjy7izjHgkYebfcl827nfp)。
