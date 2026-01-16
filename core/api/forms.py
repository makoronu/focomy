"""Form API endpoints - public form handling."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..engine.routes import render_theme
from ..rate_limit import limiter
from ..services.entity import EntityService
from ..services.mail import mail_service
from ..utils import require_feature_async

router = APIRouter(prefix="/forms", tags=["forms"])


class FormSubmitRequest(BaseModel):
    """Form submission request."""

    data: dict[str, Any]


@router.get("/{slug}", response_class=HTMLResponse)
async def view_form(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """View a public form."""
    await require_feature_async("form", db)
    entity_svc = EntityService(db)

    # Find form
    forms = await entity_svc.find(
        "form",
        limit=1,
        filters={"slug": slug, "status": "published"},
    )

    if not forms:
        raise HTTPException(status_code=404, detail="Form not found")

    form = forms[0]
    form_data = entity_svc.serialize(form)

    # Parse fields config
    fields_config = form_data.get("fields_config", [])
    if isinstance(fields_config, str):
        try:
            fields_config = json.loads(fields_config)
        except json.JSONDecodeError:
            fields_config = []

    # Parse steps config
    steps = form_data.get("steps", [])
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            steps = []

    # Render form template (with admin bar context)
    html = await render_theme(
        db,
        "form.html",
        {
            "form": form_data,
            "fields": fields_config,
            "steps": steps,
            "csrf_token": getattr(request.state, "csrf_token", ""),
        },
        request=request,
        entity=form,
        content_type="form",
    )

    return HTMLResponse(content=html)


@router.post("/{slug}")
@limiter.limit("10/minute")
async def submit_form(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit a form."""
    await require_feature_async("form", db)
    entity_svc = EntityService(db)

    # Find form
    forms = await entity_svc.find(
        "form",
        limit=1,
        filters={"slug": slug, "status": "published"},
    )

    if not forms:
        raise HTTPException(status_code=404, detail="Form not found")

    form = forms[0]
    form_data = entity_svc.serialize(form)

    # Get form data
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        submission_data = body.get("data", body)
    else:
        form_body = await request.form()
        submission_data = {k: v for k, v in form_body.items() if k != "csrf_token"}

    # Validate required fields
    fields_config = form_data.get("fields_config", [])
    if isinstance(fields_config, str):
        try:
            fields_config = json.loads(fields_config)
        except json.JSONDecodeError:
            fields_config = []

    errors = []
    for field in fields_config:
        if field.get("required") and not submission_data.get(field["name"]):
            errors.append(f"{field.get('label', field['name'])}は必須です")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Save submission
    await entity_svc.create(
        "form_submission",
        {
            "form_id": form.id,
            "form_title": form_data.get("title"),
            "data": submission_data,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "status": "new",
        },
    )

    # Send notification email
    notify_email = form_data.get("notify_email")
    if notify_email:
        reply_to = submission_data.get("email")
        mail_service.send_form_notification(
            to=notify_email,
            form_title=form_data.get("title", ""),
            submission_data=submission_data,
            reply_to=reply_to,
        )

    # Handle response
    redirect_url = form_data.get("redirect_url")
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=303)

    success_message = form_data.get("success_message", "送信が完了しました。")

    # Check if AJAX request
    if "application/json" in content_type:
        return {"success": True, "message": success_message}

    # Render success page (with admin bar context)
    html = await render_theme(
        db,
        "form_success.html",
        {
            "form": form_data,
            "message": success_message,
        },
        request=request,
    )

    return HTMLResponse(content=html)
