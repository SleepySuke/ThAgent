import logging

from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from loop.hitl_handler import process_email_with_hitl, ReviewMode
from persistence.connection import get_pool

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self):
        self._checkpointer: AIOMySQLSaver | None = None
        self._graph = None

    async def _get_checkpointer(self) -> AIOMySQLSaver:
        if self._checkpointer is None:
            pool = await get_pool()
            self._checkpointer = AIOMySQLSaver(conn=pool)
        return self._checkpointer

    async def _get_graph(self):
        if self._graph is None:
            from model.llm import create_model
            from utils.config_handler import load_project_config
            from graph import build_multi_agent_graph

            config = load_project_config()
            model = create_model(config)
            checkpointer = await self._get_checkpointer()
            builder = build_multi_agent_graph(model)
            self._graph = builder.compile(checkpointer=checkpointer)
        return self._graph

    async def process_email(self, email_data: dict,
                            mode: ReviewMode = ReviewMode.CLI) -> dict | None:
        graph = await self._get_graph()
        config = {
            "configurable": {
                "thread_id": email_data.get("thread_id", f"email-{email_data.get('email_id', 'unknown')}"),
                "model": (await self._get_graph()).__class__,  # will be set properly
            }
        }

        initial_state = {
            "email_id": email_data.get("email_id"),
            "sender_email": email_data.get("sender_email"),
            "email_subject": email_data.get("email_subject"),
            "email_content": email_data.get("email_content"),
            "remaining_steps": 30,
        }

        return await process_email_with_hitl(
            graph, config, initial_state, mode=mode,
        )

    async def process_email_with_model(self, email_data: dict, model,
                                       mode: ReviewMode = ReviewMode.CLI) -> dict | None:
        graph = await self._get_graph()
        thread_id = f"email-{email_data.get('email_id', 'unknown')}"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "model": model,
                "imap_server": "",
                "smtp_server": "",
                "email_address": "",
                "auth_code": "",
            }
        }

        initial_state = {
            "email_id": email_data.get("email_id"),
            "sender_email": email_data.get("sender_email"),
            "email_subject": email_data.get("email_subject"),
            "email_content": email_data.get("email_content"),
            "remaining_steps": 30,
        }

        return await process_email_with_hitl(
            graph, config, initial_state, mode=mode,
        )
