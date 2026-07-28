def build_supervisor_prompt(state: dict) -> str:
    """构建 Supervisor 系统提示，注入当前处理状态"""
    classification = state.get("classification") or {}
    draft = state.get("draft_response")
    review_status = state.get("review_status")
    kb_results = state.get("kb_results")
    bug_results = state.get("bug_results")
    search_results = state.get("search_results") or []

    status_lines = ["当前处理状态："]
    status_lines.append(f"- 邮件主题：{state.get('email_subject', 'N/A')}")
    status_lines.append(f"- 发件人：{state.get('sender_email', 'N/A')}")

    if classification:
        status_lines.append(f"- 分类结果：意图={classification.get('intent')}, "
                           f"紧急度={classification.get('urgency')}, "
                           f"主题={classification.get('topic')}")
    else:
        status_lines.append("- 分类结果：尚未分类")

    if search_results or kb_results or bug_results:
        status_lines.append("- 信息检索：已完成")
    else:
        status_lines.append("- 信息检索：未进行")

    if draft:
        preview = draft[:150].replace("\n", " ")
        status_lines.append(f"- 回复草稿：已生成 ({preview}...)")
    else:
        status_lines.append("- 回复草稿：未生成")

    if review_status:
        status_lines.append(f"- 审核状态：{review_status}")
    else:
        status_lines.append("- 审核状态：未审核")

    status_summary = "\n".join(status_lines)

    return f"""你是邮件处理 Supervisor（调度总管）。你的职责是分析当前处理状态，决定下一步由哪个 Specialist Agent 处理。

## 可调度的 Specialist

- **transfer_to_classifier**: 对邮件进行意图和紧急度分类
- **transfer_to_researcher**: 搜索知识库和缺陷追踪系统，获取相关信息
- **transfer_to_draft_writer**: 撰写或修订回复草稿
- **transfer_to_human_review**: 将草稿提交人工审核
- **finish**: 邮件处理完成（已发送或无需回复）

## 决策逻辑

1. 新邮件刚到达（尚无分类）→ transfer_to_classifier
2. 已分类但未检索信息 → transfer_to_researcher
3. 已完成检索但未起草 → transfer_to_draft_writer
4. 草稿已生成但未审核 → transfer_to_human_review
5. 审核通过（review_status=approved）→ finish
6. 审核打回（review_status=needs_revision）→ transfer_to_draft_writer

## 重要规则

- 严格按照决策逻辑的优先级顺序判断
- 每次只调用一个工具
- 如果分类为空，必须先 transfer_to_classifier

{status_summary}"""


def build_researcher_prompt(state: dict) -> str:
    """构建 Researcher 系统提示，注入邮件和分类信息"""
    classification = state.get("classification") or {}

    context_lines = [
        f"邮件主题：{state.get('email_subject', 'N/A')}",
        f"邮件内容：{state.get('email_content', 'N/A')}",
    ]

    if classification:
        context_lines.append(
            f"分类结果：意图={classification.get('intent')}, "
            f"紧急度={classification.get('urgency')}, "
            f"主题={classification.get('topic')}, "
            f"摘要={classification.get('summary')}"
        )

    context = "\n".join(context_lines)

    return f"""你是信息检索专家。根据邮件分类结果，检索相关知识库和缺陷记录。

## 上下文

{context}

## 工具使用

- 先用 **search_kb** 搜索知识库文档（FAQ、产品文档、故障排查指南），查询使用分类的主题和摘要作为关键词
- 如果分类意图是"缺陷"，额外用 **query_bugs** 查询已知缺陷

## 要求

- 必须先调用至少一个搜索工具获取信息
- 检索完成后，总结关键发现"""


def build_draft_writer_prompt(state: dict) -> str:
    """构建 Draft Writer 系统提示，注入邮件和相关上下文"""
    classification = state.get("classification") or {}
    search_results = state.get("search_results") or []
    review_status = state.get("review_status")
    existing_draft = state.get("draft_response", "")

    context_lines = [
        f"发件人：{state.get('sender_email', 'N/A')}",
        f"主题：{state.get('email_subject', 'N/A')}",
        f"原始邮件内容：{state.get('email_content', 'N/A')}",
    ]

    if classification:
        context_lines.append(
            f"分类：意图={classification.get('intent')}, "
            f"紧急度={classification.get('urgency')}"
        )

    if search_results:
        context_lines.append(f"检索结果：{' | '.join(search_results[:3])}")

    if review_status == "needs_revision" and existing_draft:
        context_lines.append(f"上一版草稿（被打回需要重写）：{existing_draft}")

    context = "\n".join(context_lines)

    return f"""你是专业的客服邮件回复撰写专家。根据邮件内容、分类结果和检索信息，撰写回复草稿。

## 上下文

{context}

## 工具使用

- **write_draft(subject, body)**: 写好草稿后保存。subject 是回复邮件主题（不含 Re:），body 是完整正文。
- **revise_draft(feedback, current_draft)**: 根据反馈修改草稿。

## 要求

1. 语气专业、友善、具体
2. 直接回答用户问题，不要含糊
3. 如果检索到相关文档，引用关键信息
4. 如果涉及已知缺陷，告知当前处理状态和临时方案
5. 署名：客服团队
6. 必须调用 write_draft 工具保存草稿，不要只输出文本"""


CLASSIFIER_SYSTEM = """你是客服邮件分类专家。根据邮件内容输出分类结果。

意图 (intent)：
- 问题：用户遇到使用问题
- 缺陷：产品 bug 或故障
- 计费：账单、支付、退款相关
- 功能请求：新功能建议
- 复杂：多个类别混合或无法归类

紧急度 (urgency)：low / medium / high / critical
置信度 (confidence)：0.0 ~ 1.0，你对分类的把握程度
主题 (topic)：≤15字的简短概括
摘要 (summary)：一句话概括用户诉求"""
