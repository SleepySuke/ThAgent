# Agent Learning Project

这是一个用于学习 **AI Agent** 的工程，主要基于 **Google ADK (Agent Development Kit)** 和 **OpenAI Agents SDK** 框架。项目包含了多个 Agent 学习示例，涵盖了从基础的 LLM 调用到复杂的多 Agent 协作系统。

## 项目结构

```
Agent/
├── AIGC/                              # 核心学习代码目录
│   ├── google/                        # Google GenAI 基础示例
│   ├── llm_agent_demo/                # LLM Agent 基础示例
│   └── open_ai_agents/                # OpenAI Agents SDK 示例
│       └── financial_research_agent/  # 金融研究多 Agent 系统
│
├── clothing-customer-service/         # 服装客服 RAG 项目（资料上传 + 多轮问答）
├── financial-advisor/                 # 金融顾问完整项目 (重点)
├── agent_team/                        # Agent 团队协作示例
│   └── weather_agent/                 # 天气 Agent (含子代理)
│
├── story_agent/                       # 故事生成工作流
├── mcp_agent/                         # MCP Agent 示例
├── mcp_client/                        # MCP 客户端
├── mcp_server/                        # MCP 服务端
├── human_tool_confirmation/           # 人工工具确认示例
├── skills_agent/                      # Skills 技能示例
├── my_agent/                          # 自定义 Agent
└── parent_folder/
    └── multi_tool_agent/              # 多工具 Agent
```

## 项目文档

- [UV + Python 本地包启动指南](docs/uv-python-guide.md)
- [服装客服 RAG 项目实现说明](docs/clothing-customer-service-rag.md)

## 模块说明

### 1. AIGC - 核心学习代码

#### Google GenAI 基础 (`AIGC/google/`)
- `gen_ai_01.py`: Google GenAI 客户端初始化示例

#### LLM Agent 基础示例 (`AIGC/llm_agent_demo/`)
- `demo_01.py`: OpenAI API 基础调用示例（使用 DashScope）
- `open_ai_demo_01.py`: OpenAI 模型调用示例
- `langchain_demo_01.py`: LangChain 集成示例
- `finance_text_category.py`: 金融文本分类示例

#### OpenAI Agents SDK 示例 (`AIGC/open_ai_agents/`)
- `open_agent_01.py`: 基础 Agent 创建和运行（使用 LitellmModel）
- `auto_mode.py`: 自动化模式工具类
- `agent_conditional.py`: 条件 Agent 示例
- `agent_streaming.py`: Agent 流式输出示例
- `analysis_agents.py`: 分析型 Agent

#### 金融研究 Agent (`AIGC/open_ai_agents/financial_research_agent/`)
一个完整的金融研究多 Agent 系统：

| Agent | 功能 |
|-------|------|
| `planner_agent` | 规划搜索策略 |
| `search_agent` | 执行网络搜索 |
| `financials_agent` | 基本面分析 |
| `risk_agent` | 风险分析 |
| `writer_agent` | 撰写分析报告 |
| `verifier_agent` | 验证报告一致性 |

### 2. clothing-customer-service - 服装客服 RAG 项目

一个围绕服装客服场景搭建的 RAG Demo，当前已经串起离线资料导入与在线多轮问答两个核心流程：

详细设计、数据流向、关键实现和已处理问题见 [服装客服 RAG 项目实现说明](docs/clothing-customer-service-rag.md)。

| 模块 | 功能 |
|------|------|
| `app_file_upload.py` | Streamlit 资料上传与默认资料初始化页面 |
| `app_qa.py` | Streamlit 问答页面，支持历史会话切换 |
| `knowledge_base.py` | 文本切分、MD5 去重、知识库写入 |
| `vector_stores.py` | Chroma 向量检索封装 |
| `rag.py` | 历史对话改写、资料检索、回答生成 |
| `file_history_store.py` | 文件化历史消息持久化 |

**当前能力:**
- 支持默认资料初始化与自定义文件上传
- 支持基于 Chroma 的资料持久化检索
- 支持历史对话和 RAG 结合的多轮问答
- 支持页面刷新后恢复当前会话，并切换历史会话

### 3. financial-advisor - 金融顾问完整项目

基于 **Google ADK** 框架构建的完整项目：

```
financial_coordinator (主协调 Agent)
├── data_analyst_agent      # 数据分析师
├── trading_analyst_agent   # 交易策略师
├── execution_analyst_agent # 执行分析师
└── risk_analyst_agent      # 风险分析师
```

包含完整的部署脚本、评估测试和单元测试。

### 4. agent_team/weather_agent - Agent 团队协作

展示了如何构建主 Agent 管理多个子 Agent 的系统：

```
weather_agent (主协调 Agent)
├── greeting_agent   # 问候子代理
└── farewell_agent   # 告别子代理
```

**特性:**
- 状态感知工具 (`get_weather_stateful`)
- 回调机制 (before_model_callback, before_tool_callback)
- 护栏功能 (Guardrail) - 拦截特定关键词和参数
- Session 状态管理

### 5. story_agent - 故事生成工作流

展示了自定义 `BaseAgent` 的实现：

```
StoryFlowAgent
├── story_generator  # 生成故事
├── LoopAgent
│   ├── critic       # 评论家
│   └── reviser      # 修订者
└── SequentialAgent
    ├── grammar_check # 语法检查
    └── tone_check    # 语气检查
```

### 6. MCP 协议示例

| 模块 | 功能 |
|------|------|
| `mcp_agent` | 使用 MCP 工具集连接文件系统服务 |
| `mcp_client` | MCP 客户端，调用自定义 MCP 服务 |
| `mcp_server` | MCP 服务端，暴露 ADK 工具 |

### 7. human_tool_confirmation - 人工确认机制

展示如何在工具调用前请求人工确认：
- `require_confirmation` - 设置确认阈值
- `tool_context.request_confirmation()` - 请求确认
- `ResumabilityConfig` - 支持会话恢复

### 8. skills_agent - 技能系统

展示 ADK 的 **SkillToolset** 功能，包含天气技能示例。

## 技术栈

### 框架和库

| 框架 | 用途 |
|------|------|
| Google ADK | 主要 Agent 开发框架 |
| OpenAI Agents SDK | OpenAI Agent 框架 |
| LiteLlm | 统一 LLM 接口 |
| LangChain | RAG 链路与消息历史编排 |
| Chroma | 向量存储与资料检索 |
| Streamlit | RAG 项目的 Web 页面 |
| MCP | Model Context Protocol |

### 模型支持

| 模型 | 用途 |
|------|------|
| `dashscope/qwen-plus` | 通义千问（阿里云） |
| `zai/glm-4.7` | 智谱 GLM |
| Google Gemini | Google GenAI |

### 主要依赖

```bash
google-adk>=1.0.0
google-genai>=1.9.0
google-cloud-aiplatform[adk]>=1.93.0
pydantic>=2.10.6
python-dotenv>=1.0.1
mcp
```

## 环境配置

> **快速上手指南：** 本项目使用 [uv](https://github.com/astral-sh/uv) 管理 Python 环境和依赖，通过 `python -m` 方式启动各模块。详细教程请参考 [docs/uv-python-guide.md](docs/uv-python-guide.md)。

```bash
# 快速初始化
uv init --no-readme
uv add --requirements requirements.txt

# 运行示例
uv run python -m AIGC.llm_agent_demo.demo_01
```

如果要体验服装客服 RAG 项目，可直接启动两个 Streamlit 页面：

```bash
streamlit run clothing-customer-service/app_file_upload.py
streamlit run clothing-customer-service/app_qa.py
```

创建 `.env` 文件并配置以下环境变量：

```env
# Google Cloud
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=<location>

# 阿里云 DashScope
DASHSCOPE_API_KEY=<your-api-key>
```

## 学习要点

1. **基础 Agent 创建**: 使用 `LlmAgent` 创建基本 Agent
2. **工具集成**: 定义 Python 函数作为 Agent 工具
3. **多 Agent 协作**: 使用 `sub_agents` 构建层级 Agent 系统
4. **状态管理**: 使用 Session State 和 `output_key` 传递数据
5. **工作流编排**:
   - `SequentialAgent` - 顺序执行
   - `LoopAgent` - 循环迭代
   - 自定义 `BaseAgent` - 复杂编排
6. **护栏机制**: 使用回调函数实现安全检查
7. **MCP 协议**: 标准化工具接口
8. **技能系统**: 可扩展的技能模块
9. **RAG 体系**: 资料切分、向量检索、检索增强问答、多轮历史会话结合

## 当前状态

- [x] 添加更多 Agent 模式示例
- [x] 添加 RAG Agent 示例
- [x] 添加基础 MCP 工具示例

### 9. intelligent-sweep-robot — 智扫通 Agent

基于 **LangChain** 构建的扫地机器人智能客服 Agent，完整的 Agent 闭环项目。详见 [intelligent-sweep-robot/README.md](intelligent-sweep-robot/README.md)。

| 特性 | 说明 |
|------|------|
| Agent 编排 | `langchain.agents.create_agent` + 动态 Prompt 切换 |
| Middleware | 执行链路观测 (before/after model, tool monitor) |
| RAG | Chroma 向量库 + 知识库检索总结 |
| 工具 | 6 个 LangChain Tool (RAG 总结 / 天气 / 位置 / 用户 ID / 月份 / 使用数据) |
| 前端 | Streamlit 对话界面 (流式输出 + 文件上传 + 历史持久化) |
| 测试 | 单元测试 + 端到端测试 |

## 后续计划

- [ ] 完善单元测试覆盖率
- [ ] 添加 LangGraph 集成示例
- [ ] 添加更多 MCP 工具示例
- [ ] 部署和监控示例

## 参考资源
- 同时可以移步到main分支上的Java代码教程，里面也介绍有关SpringAI、Graph集成使用

- [Google ADK 文档](https://github.com/google/adk-python)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-sdk)
- [Model Context Protocol](https://modelcontextprotocol.io/)

