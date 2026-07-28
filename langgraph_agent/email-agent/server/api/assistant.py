from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatBody(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: Request, body: ChatBody):
    from service.assistant_service import AssistantService
    svc = AssistantService()
    reply = await svc.chat(body.message)
    return {"reply": reply, "message": body.message}


@router.get("/summary")
async def inbox_summary(request: Request):
    from service.assistant_service import AssistantService
    svc = AssistantService()
    summary = await svc.get_inbox_summary()
    return {"summary": summary}
