from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal


class ReviewScreen(Vertical):
    def compose(self):
        yield Static("加载中...", id="review-info")
        yield Static("", id="review-detail")
        with Horizontal(id="review-btns"):
            yield Button("通过", id="btn-approve", variant="success")
            yield Button("打回", id="btn-reject", variant="error")

    async def on_mount(self):
        self.set_interval(10, self.refresh)
        await self.refresh()

    async def refresh(self):
        try:
            from persistence.connection import init_db, get_pool
            from persistence.review_repo import ReviewRepo
            await init_db()
            pool = await get_pool()
            repo = ReviewRepo(pool)
            pending = await repo.list_pending()
            if pending:
                r = pending[0]
                self.query_one("#review-info").update(
                    f"待审批: {len(pending)} 封\n发件人: {r.get('sender_email')} | 主题: {r.get('email_subject')}"
                )
                draft = (r.get("draft_response") or "")[:500]
                self.query_one("#review-detail").update(draft)
                self._current_thread = r["thread_id"]
            else:
                self.query_one("#review-info").update("暂无待审批邮件")
                self.query_one("#review-detail").update("")
                self._current_thread = None
        except Exception as e:
            self.query_one("#review-info").update(f"错误: {e}")

    async def on_button_pressed(self, event: Button.Pressed):
        if not getattr(self, "_current_thread", None):
            return
        tid = self._current_thread
        try:
            from persistence.connection import get_pool
            from persistence.review_repo import ReviewRepo
            pool = await get_pool()
            repo = ReviewRepo(pool)
            if event.button.id == "btn-approve":
                await repo.resolve(tid, "approved", "已通过")
            elif event.button.id == "btn-reject":
                await repo.resolve(tid, "rejected", "已打回")
            await self.refresh()
        except Exception as e:
            self.query_one("#review-info").update(f"操作失败: {e}")
