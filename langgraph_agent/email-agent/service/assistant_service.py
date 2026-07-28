import logging

from langchain_community.chat_models.tongyi import ChatTongyi

from model.llm import create_model
from utils.config_handler import load_project_config
from persistence.email_repo import EmailRepo
from persistence.connection import get_pool

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM = """你是个人邮件助手。你可以帮助用户：
1. 查看邮件处理状态
2. 回答关于邮件的问题
3. 给出处理建议

请用简洁的中文回复。"""


class AssistantService:
    def __init__(self):
        self._model = None
        self._email_repo: EmailRepo | None = None

    def _get_model(self):
        if self._model is None:
            config = load_project_config()
            self._model = create_model(config)
        return self._model

    async def _get_email_repo(self) -> EmailRepo:
        if self._email_repo is None:
            pool = await get_pool()
            self._email_repo = EmailRepo(pool)
        return self._email_repo

    async def chat(self, message: str, context: dict | None = None) -> str:
        model = self._get_model()

        context_lines = [f"用户: {message}"]
        if context:
            context_lines.insert(0, f"当前上下文: {context}")

        prompt = "\n".join(context_lines)

        response = model.invoke([
            {"role": "system", "content": ASSISTANT_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        return response.content

    async def get_inbox_summary(self) -> str:
        repo = await self._get_email_repo()
        counts = await repo.count_by_status()
        pending = counts.get("pending", 0)
        review = counts.get("awaiting_review", 0)
        sent = counts.get("sent", 0)
        return f"收件箱概览：{pending}封待处理，{review}封待审批，{sent}封已发送。"
