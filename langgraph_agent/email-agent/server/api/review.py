from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class RejectBody(BaseModel):
    reason: str = ""


class EditBody(BaseModel):
    edited_draft: str = ""


async def _get_review_service(request: Request):
    if not hasattr(request.app.state, "_review_svc"):
        from service.review_service import ReviewService
        request.app.state._review_svc = ReviewService()
    return request.app.state._review_svc


@router.get("")
async def list_pending(request: Request):
    svc = await _get_review_service(request)
    pending = await svc.list_pending()
    return {"pending": pending, "count": len(pending)}


@router.post("/{thread_id}/approve")
async def approve(request: Request, thread_id: str):
    svc = await _get_review_service(request)
    await svc.approve(thread_id)
    return {"status": "ok", "action": "approved", "thread_id": thread_id}


@router.post("/{thread_id}/reject")
async def reject(request: Request, thread_id: str, body: RejectBody):
    svc = await _get_review_service(request)
    await svc.reject(thread_id, body.reason)
    return {"status": "ok", "action": "rejected", "thread_id": thread_id}


@router.post("/{thread_id}/edit")
async def edit(request: Request, thread_id: str, body: EditBody):
    svc = await _get_review_service(request)
    await svc.edit_and_approve(thread_id, body.edited_draft)
    return {"status": "ok", "action": "edited", "thread_id": thread_id}
