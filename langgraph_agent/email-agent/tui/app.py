from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane


class EmailAgentTUI(App):
    TITLE = "Email Agent"
    SUB_TITLE = "个人邮件助手 v2.0"
    CSS = """
    TabbedContent { height: 1fr; }
    TabPane { padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("仪表盘", id="dash"):
                from tui.screens.dashboard import DashboardScreen
                yield DashboardScreen()
            with TabPane("收件箱", id="inbox"):
                from tui.screens.inbox import InboxScreen
                yield InboxScreen()
            with TabPane("审批", id="review"):
                from tui.screens.review import ReviewScreen
                yield ReviewScreen()
            with TabPane("助手", id="assistant"):
                from tui.screens.assistant import AssistantScreen
                yield AssistantScreen()
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Email Agent — 个人邮件助手"
