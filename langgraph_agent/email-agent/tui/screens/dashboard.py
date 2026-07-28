import asyncio
from textual.widgets import Static
from textual.containers import Vertical


class DashboardScreen(Vertical):
    def compose(self):
        yield Static("加载中...", id="stats")

    async def on_mount(self):
        self.set_interval(10, self.refresh_stats)
        asyncio.create_task(self.refresh_stats())

    async def refresh_stats(self):
        try:
            from persistence.connection import init_db, get_pool
            from persistence.email_repo import EmailRepo
            await init_db()
            pool = await get_pool()
            repo = EmailRepo(pool)
            counts = await repo.count_by_status()
            total = sum(counts.values())
            lines = [
                f"  待处理: {counts.get('pending', 0)}    处理中: {counts.get('processing', 0)}",
                f"  待审批: {counts.get('awaiting_review', 0)}    已发送: {counts.get('sent', 0)}",
                f"  总计: {total}",
            ]
            self.query_one("#stats").update("\n".join(lines))
        except Exception as e:
            self.query_one("#stats").update(f"错误: {e}")
