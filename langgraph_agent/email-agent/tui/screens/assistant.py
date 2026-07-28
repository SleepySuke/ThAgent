from textual.widgets import Static, Input
from textual.containers import Vertical


class AssistantScreen(Vertical):
    def compose(self):
        yield Static("对话助手 — 输入指令后回车发送", id="chat-info")
        yield Static("", id="chat-history")
        yield Input(placeholder="输入指令...", id="chat-input")

    async def on_input_submitted(self, event: Input.Submitted):
        msg = event.value.strip()
        if not msg:
            return
        event.input.value = ""
        try:
            from service.assistant_service import AssistantService
            svc = AssistantService()
            reply = await svc.chat(msg)
            history = self.query_one("#chat-history")
            current = history.renderable if history.renderable else ""
            history.update(f"{current}\n\n你: {msg}\n助手: {reply}")
        except Exception as e:
            self.query_one("#chat-info").update(f"错误: {e}")
