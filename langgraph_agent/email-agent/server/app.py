import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

load_dotenv()
logger = logging.getLogger(__name__)

templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

_jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    auto_reload=True,
    cache_size=0,
)


def _render(name: str, context: dict) -> HTMLResponse:
    tmpl = _jinja_env.get_template(name)
    return HTMLResponse(tmpl.render(context))


def _email_svc(request: Request):
    if not hasattr(request.app.state, "_email_svc"):
        from service.email_service import EmailService
        request.app.state._email_svc = EmailService()
    return request.app.state._email_svc


def _review_svc(request: Request):
    if not hasattr(request.app.state, "_review_svc"):
        from service.review_service import ReviewService
        request.app.state._review_svc = ReviewService()
    return request.app.state._review_svc


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    from persistence.connection import init_db, get_pool
    from rag.chroma_client import ensure_kb_initialized

    await init_db()
    ensure_kb_initialized()
    logger.info("Database and KB initialized")

    # 创建模型和图
    from model.llm import create_model
    from utils.config_handler import load_project_config
    from graph import build_multi_agent_graph
    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

    project_config = load_project_config()
    model = create_model(project_config)
    pool = await get_pool()
    checkpointer = AIOMySQLSaver(conn=pool)
    compiled = build_multi_agent_graph(model).compile(checkpointer=checkpointer)

    app.state.model = model
    app.state.graph = compiled
    logger.info("Multi-agent graph compiled with MySQL checkpointer")

    # 启动邮件处理链路
    email_queue: asyncio.Queue = asyncio.Queue()
    app.state.email_queue = email_queue

    imap_cfg = {
        "imap_server": os.getenv("IMAP_SERVER", "imap.163.com"),
        "smtp_server": os.getenv("SMTP_SERVER", "smtp.163.com"),
        "email_address": os.getenv("EMAIL_ADDRESS", ""),
        "auth_code": os.getenv("EMAIL_AUTH_CODE", ""),
    }

    # 后台任务: IMAP 轮询 + 消费者
    from loop.engine import run_imap_poller, run_consumer

    poller_task = asyncio.create_task(
        run_imap_poller(email_queue, interval=60),
        name="imap-poller",
    )
    consumer_task = asyncio.create_task(
        run_consumer(compiled, model, imap_cfg, email_queue),
        name="email-consumer",
    )
    app.state._bg_tasks = [poller_task, consumer_task]

    logger.info("IMAP poller and email consumer started")
    yield

    # ── shutdown ──
    for task in app.state._bg_tasks:
        task.cancel()
    await asyncio.gather(*app.state._bg_tasks, return_exceptions=True)

    from persistence.connection import close_pool
    await close_pool()
    logger.info("FastAPI server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Email Agent", version="2.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from server.api.emails import router as email_router
    from server.api.review import router as review_router
    from server.api.assistant import router as assistant_router
    from server.api.ws import router as ws_router

    app.include_router(email_router)
    app.include_router(review_router)
    app.include_router(assistant_router)
    app.include_router(ws_router)

    @app.get("/")
    async def dashboard_page(request: Request):
        svc = _email_svc(request)
        stats = await svc.get_stats()
        return _render("dashboard.html", {"request": request, "stats": stats, "title": "Dashboard"})

    @app.get("/inbox")
    async def inbox_page(request: Request, status: str | None = None):
        svc = _email_svc(request)
        emails = await svc.list_emails(status=status)
        return _render("inbox.html", {"request": request, "emails": emails, "title": "Inbox", "current_status": status})

    @app.get("/review")
    async def review_page(request: Request):
        svc = _review_svc(request)
        pending = await svc.list_pending()
        return _render("review.html", {"request": request, "pending": pending, "title": "Review Queue"})

    @app.get("/assistant")
    async def assistant_page(request: Request):
        return _render("assistant.html", {"request": request, "title": "Assistant"})

    return app
