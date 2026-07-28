from textual.widgets import Static, DataTable
from textual.containers import Vertical


class InboxScreen(Vertical):
    def compose(self):
        yield Static("加载中...", id="inbox-info")
        yield DataTable(id="email-table")

    async def on_mount(self):
        table = self.query_one("#email-table", DataTable)
        table.add_columns("发件人", "主题", "状态", "时间")
        self.set_interval(15, self.refresh)
        await self.refresh()

    async def refresh(self):
        try:
            from persistence.connection import init_db, get_pool
            from persistence.email_repo import EmailRepo
            await init_db()
            pool = await get_pool()
            repo = EmailRepo(pool)
            emails = await repo.list_all(limit=50)
            table = self.query_one("#email-table", DataTable)
            table.clear()
            for e in emails:
                table.add_row(
                    e.get("sender_email", "-")[:25],
                    (e.get("email_subject") or "-")[:40],
                    e.get("status", "-"),
                    str(e.get("created_at", "-"))[:19],
                )
            self.query_one("#inbox-info").update(f"共 {len(emails)} 封邮件")
        except Exception as e:
            self.query_one("#inbox-info").update(f"错误: {e}")
