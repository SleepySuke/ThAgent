from fastapi import APIRouter, Request, Query

router = APIRouter(prefix="/api/emails", tags=["emails"])


async def _get_email_service(request: Request):
    if not hasattr(request.app.state, "_email_svc"):
        from service.email_service import EmailService
        request.app.state._email_svc = EmailService()
    return request.app.state._email_svc


@router.get("")
async def list_emails(
    request: Request,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    svc = await _get_email_service(request)
    emails = await svc.list_emails(status=status, limit=limit, offset=offset)
    return {"emails": emails, "count": len(emails)}


@router.get("/stats")
async def get_stats(request: Request):
    svc = await _get_email_service(request)
    return await svc.get_stats()


@router.get("/{thread_id}")
async def get_email(request: Request, thread_id: str):
    svc = await _get_email_service(request)
    email = await svc.get_email(thread_id)
    if email is None:
        return {"error": "not found"}
    return {"email": email}
