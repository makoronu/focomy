"""Admin routes - WordPress import preview and dry-run operations."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..rate_limit import limiter
from ..schemas.import_schema import ErrorResponse
from ..utils import require_feature
from .helpers import require_admin

router = APIRouter()


@router.post(
    "/import/{job_id}/dry-run",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def dry_run_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run a dry-run simulation of the import without making changes."""
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

        # Run dry-run
        result = await import_svc.dry_run(job_id)

        if not result:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Dry-run failed",
                    code="DRY_RUN_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        # Convert to JS-expected format
        summary = result.get("summary", {})
        counts = {
            "new": sum(s.get("new", 0) for s in summary.values()),
            "skip": sum(s.get("duplicates", 0) for s in summary.values()),
            "error": len(result.get("errors", [])),
            "update": 0,
        }
        # Build items with status for each type
        items = {}
        for entity_type, stats in summary.items():
            items[entity_type] = [
                {"status": "new"} for _ in range(stats.get("new", 0))
            ] + [
                {"status": "skip"} for _ in range(stats.get("duplicates", 0))
            ]

        return {
            "success": True,
            "job_id": job_id,
            "counts": counts,
            "items": items,
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "duplicates": result.get("duplicates", []),
            "has_errors": len(result.get("errors", [])) > 0,
            "request_id": request_id,
        }

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
    "/import/{job_id}/preview",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def preview_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Preview import by creating a small number of sample items."""
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

        result = await import_svc.preview_import(job_id, limit=3)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error=result.get("error", "Preview failed") if result else "Preview failed",
                    code="PREVIEW_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "job_id": job_id,
            "preview": result,
            "request_id": request_id,
        }

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
    "/import/{job_id}/preview/confirm",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def confirm_preview(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Confirm preview items and finalize them."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.confirm_preview(job_id)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Confirm failed") if result else "Confirm failed",
                    code="CONFIRM_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "confirmed": result.get("confirmed", 0),
            "request_id": request_id,
        }

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
    "/import/{job_id}/preview/discard",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def discard_preview(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Discard preview items and delete them."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.discard_preview(job_id)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Discard failed") if result else "Discard failed",
                    code="DISCARD_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "discarded": result.get("discarded", 0),
            "request_id": request_id,
        }

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
    "/import/{job_id}/resume",
    responses={
        400: {"model": ErrorResponse, "description": "Cannot resume job"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def resume_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Resume a failed or cancelled import job from checkpoint."""
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
                    error="Import job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Check if job can be resumed
        from ..models import ImportJobStatus

        if job.status not in (
            ImportJobStatus.FAILED,
            ImportJobStatus.CANCELLED,
        ):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=f"Cannot resume job with status: {job.status}. Only failed or cancelled jobs can be resumed.",
                    code="INVALID_STATUS",
                    request_id=request_id,
                ).model_dump(),
            )

        # Get checkpoint info
        checkpoint = job.checkpoint or {}
        last_phase = checkpoint.get("last_phase", "beginning")

        # Start resume in background
        asyncio.create_task(import_svc.resume_import(job_id))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Import resumed from phase: {last_phase}",
            "checkpoint": {
                "last_phase": last_phase,
                "authors_processed": len(checkpoint.get("authors", [])),
                "categories_processed": len(checkpoint.get("categories", [])),
                "tags_processed": len(checkpoint.get("tags", [])),
                "media_processed": len(checkpoint.get("media", [])),
                "posts_processed": len(checkpoint.get("posts", [])),
                "pages_processed": len(checkpoint.get("pages", [])),
                "menus_processed": len(checkpoint.get("menus", [])),
            },
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )
