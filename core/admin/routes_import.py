"""Admin routes - WordPress import core flow."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..rate_limit import limiter
from ..schemas.import_schema import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ErrorResponse,
)
from ..services.entity import EntityService
from ..utils import require_feature
from .helpers import get_context, require_admin, templates

router = APIRouter()


@router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """WordPress import page."""
    require_feature("wordpress_import")
    context = await get_context(request, db, current_user, "import")
    return templates.TemplateResponse("admin/import.html", context)


@router.post(
    "/import/test-connection",
    response_model=ConnectionTestResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("10/minute")
async def test_wp_connection(
    request: Request,
    data: ConnectionTestRequest,
    current_user: Entity = Depends(require_admin),
):
    """Test WordPress REST API connection."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import RESTClientConfig, WordPressRESTClient

    request_id = str(uuid.uuid4())[:8]

    try:
        config = RESTClientConfig(
            site_url=str(data.url),
            username=data.username,
            password=data.password,
        )

        async with WordPressRESTClient(config) as client:
            result = await client.test_connection()

            return ConnectionTestResponse(
                success=result.success,
                message=result.message,
                site_name=result.site_name,
                authenticated=result.authenticated,
                errors=result.errors,
            )

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="CONNECTION_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/analyze",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def analyze_import(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Analyze WordPress data for import."""
    require_feature("wordpress_import")
    import tempfile
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        form = await request.form()
        source_type = form.get("source_type", "wxr")

        # Validate source_type
        if source_type not in ("wxr", "rest"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Invalid source_type. Must be 'wxr' or 'rest'",
                    code="INVALID_SOURCE_TYPE",
                    request_id=request_id,
                ).model_dump(),
            )

        import_svc = WordPressImportService(db)

        # Determine upload directory and base URL
        upload_dir = Path("uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        base_url = str(request.base_url).rstrip("/")

        # Validate webp_quality
        try:
            webp_quality = int(form.get("webp_quality", "85"))
            if not 1 <= webp_quality <= 100:
                webp_quality = 85
        except ValueError:
            webp_quality = 85

        config = {
            "import_media": form.get("import_media") == "true",
            "download_media": form.get("download_media") == "true",
            "convert_to_webp": form.get("convert_to_webp") == "true",
            "webp_quality": webp_quality,
            "include_drafts": form.get("include_drafts") == "true",
            "import_comments": form.get("import_comments") == "true",
            "import_menus": form.get("import_menus") == "true",
            "upload_dir": str(upload_dir),
            "base_url": base_url,
        }

        source_url = None
        source_file = None

        if source_type == "wxr":
            # Handle file upload
            file = form.get("file")
            if not file:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        error="No file uploaded",
                        code="NO_FILE",
                        request_id=request_id,
                    ).model_dump(),
                )

            # Save to temp file
            temp_dir = Path(tempfile.gettempdir())
            temp_file = temp_dir / f"wp_import_{file.filename}"
            content = await file.read()
            temp_file.write_bytes(content)
            source_file = str(temp_file)

        else:
            # REST API
            source_url = form.get("url")
            config["username"] = form.get("username", "")
            config["password"] = form.get("password", "")

            if not source_url:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        error="URL is required for REST API import",
                        code="URL_REQUIRED",
                        request_id=request_id,
                    ).model_dump(),
                )

        # Create job
        entity_svc = EntityService(db)
        user_data = entity_svc.serialize(current_user)

        job = await import_svc.create_job(
            source_type=source_type,
            source_url=source_url,
            source_file=source_file,
            config=config,
            user_id=user_data.get("id"),
        )

        # Run analysis
        analysis = await import_svc.analyze(job.id)

        if not analysis:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Analysis failed",
                    code="ANALYSIS_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "job_id": job.id,
            "analysis": analysis,
            "request_id": request_id,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/start",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def start_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Start WordPress import job."""
    require_feature("wordpress_import")
    import asyncio

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Start import in background
        asyncio.create_task(_run_import_background(job_id))

        return {"success": True, "job_id": job_id, "request_id": request_id}

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


async def _run_import_background(job_id: str):
    """Run import in background."""
    from ..database import async_session
    from ..services.wordpress_import import WordPressImportService

    async with async_session() as db:
        import_svc = WordPressImportService(db)
        await import_svc.run_import(job_id)


@router.get(
    "/import/{job_id}/status",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_import_status(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Get import job status for polling."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        return job.to_dict()

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/cancel",
    responses={
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("10/minute")
async def cancel_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Cancel import job."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        success = await import_svc.cancel_job(job_id)

        return {"success": success, "request_id": request_id}

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )
