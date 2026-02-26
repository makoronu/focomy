"""Admin routes - WordPress import diff, rollback, and link operations."""

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
    "/import/{job_id}/detect-diff",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def detect_diff(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Detect differences between WordPress and database."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.detect_diff(job_id)

        if not result:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Import job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Diff detection failed"),
                    code="DIFF_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
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
    "/import/{job_id}/import-diff",
    responses={
        400: {"model": ErrorResponse, "description": "No diff result found"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def import_diff(
    request: Request,
    job_id: str,
    import_new: bool = True,
    import_updated: bool = True,
    delete_removed: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Import only the differences (new and updated items)."""
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

        # Start diff import in background
        asyncio.create_task(
            import_svc.import_diff(
                job_id,
                import_new=import_new,
                import_updated=import_updated,
                delete_removed=delete_removed,
            )
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": "Diff import started",
            "options": {
                "import_new": import_new,
                "import_updated": import_updated,
                "delete_removed": delete_removed,
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


@router.get(
    "/import/{job_id}/rollback-status",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_rollback_status(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Get rollback status for an import job."""
    from ..services.wordpress_import.rollback import RollbackService

    request_id = str(uuid.uuid4())[:8]

    try:
        rollback_svc = RollbackService(db)
        result = await rollback_svc.get_rollback_status(job_id)

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error=result.get("error", "Job not found"),
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
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
    "/import/{job_id}/rollback",
    responses={
        400: {"model": ErrorResponse, "description": "Rollback not allowed"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("1/minute")
async def rollback_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Rollback an import job - deletes all imported entities."""
    require_feature("wordpress_import")
    from ..services.wordpress_import.rollback import RollbackService

    request_id = str(uuid.uuid4())[:8]

    try:
        rollback_svc = RollbackService(db)

        # Check if rollback is allowed
        can_rollback = await rollback_svc.can_rollback(job_id)
        if not can_rollback.get("can_rollback"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=can_rollback.get("reason", "Rollback not allowed"),
                    code="ROLLBACK_NOT_ALLOWED",
                    request_id=request_id,
                ).model_dump(),
            )

        # Perform rollback
        result = await rollback_svc.rollback(job_id)

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Rollback failed"),
                    code="ROLLBACK_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
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
    "/import/{job_id}/fix-links",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def fix_import_links(
    request: Request,
    job_id: str,
    source_domain: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Fix internal links in imported content."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)

        # Check job exists
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

        # Fix links
        result = await import_svc.fix_links(job_id, source_domain)

        return {
            **result,
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
