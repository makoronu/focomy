"""Admin routes - WordPress import verification, redirects, and alt preview."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity, EntityValue
from ..rate_limit import limiter
from ..schemas.import_schema import ErrorResponse
from ..utils import require_feature
from .helpers import require_admin

router = APIRouter()


@router.post(
    "/import/{job_id}/dry-run-v2",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def dry_run_import_v2(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run dry run simulation for import job (alternative implementation)."""
    require_feature("wordpress_import")
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService
    from ..services.wordpress_import.dry_run import DryRunService
    from ..services.wordpress_import.wxr_parser import WXRParser

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

        # Parse WXR file
        if not job.source_file:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="No source file found",
                    code="NO_SOURCE_FILE",
                    request_id=request_id,
                ).model_dump(),
            )

        file_path = Path(job.source_file)
        if not file_path.exists():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Source file not found",
                    code="FILE_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse and run dry run
        parser = WXRParser()
        wxr_data = parser.parse(str(file_path))

        dry_run_svc = DryRunService(db)
        result = await dry_run_svc.run(job_id, wxr_data)

        return {
            "success": True,
            **result.to_dict(),
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
    "/import/{job_id}/preview-v2",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def preview_import_v2(
    request: Request,
    job_id: str,
    count: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run preview import with a few items (alternative implementation)."""
    require_feature("wordpress_import")
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService
    from ..services.wordpress_import.preview import PreviewService, store_preview_entities
    from ..services.wordpress_import.wxr_parser import WXRParser

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

        # Parse WXR file
        if not job.source_file:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="No source file found",
                    code="NO_SOURCE_FILE",
                    request_id=request_id,
                ).model_dump(),
            )

        file_path = Path(job.source_file)
        if not file_path.exists():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Source file not found",
                    code="FILE_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse and run preview
        parser = WXRParser()
        wxr_data = parser.parse(str(file_path))

        preview_svc = PreviewService(db)
        result = await preview_svc.run_preview(job_id, wxr_data, count)

        # Store preview entities for later commit/rollback
        entity_ids = [i.entity_id for i in result.items if i.entity_id]
        store_preview_entities(result.preview_id, entity_ids)

        return {
            "success": True,
            **result.to_dict(),
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
    "/import/preview/{preview_id}/commit",
    responses={
        404: {"model": ErrorResponse, "description": "Preview not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def commit_preview(
    request: Request,
    preview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Commit preview - keep imported items."""
    from ..services.wordpress_import.preview import (
        get_preview_entities,
        clear_preview_entities,
    )

    request_id = str(uuid.uuid4())[:8]

    try:
        entity_ids = get_preview_entities(preview_id)

        if not entity_ids:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Preview not found or already processed",
                    code="PREVIEW_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Remove preview flag from entities
        for entity_id in entity_ids:
            result = await db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == entity_id,
                    EntityValue.field_name == "preview",
                )
            )
            ev = result.scalar_one_or_none()
            if ev:
                await db.delete(ev)

        await db.commit()
        clear_preview_entities(preview_id)

        return {
            "success": True,
            "preview_id": preview_id,
            "committed_count": len(entity_ids),
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
    "/import/preview/{preview_id}/rollback",
    responses={
        404: {"model": ErrorResponse, "description": "Preview not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def rollback_preview(
    request: Request,
    preview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Rollback preview - delete imported items."""
    from ..utils import utcnow
    from ..services.wordpress_import.preview import (
        get_preview_entities,
        clear_preview_entities,
    )

    request_id = str(uuid.uuid4())[:8]

    try:
        entity_ids = get_preview_entities(preview_id)

        if not entity_ids:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Preview not found or already processed",
                    code="PREVIEW_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Soft delete preview entities
        deleted_count = 0
        for entity_id in entity_ids:
            result = await db.execute(
                select(Entity).where(Entity.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                entity.deleted_at = utcnow()
                deleted_count += 1

        await db.commit()
        clear_preview_entities(preview_id)

        return {
            "success": True,
            "preview_id": preview_id,
            "rolled_back_count": deleted_count,
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
    "/import/{job_id}/verify",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def verify_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Verify import integrity and generate report."""
    require_feature("wordpress_import")
    from ..services.wordpress_import.verification import VerificationService

    request_id = str(uuid.uuid4())[:8]

    try:
        service = VerificationService(db)
        report = await service.verify(job_id)

        return {
            "success": True,
            "job_id": report.job_id,
            "generated_at": report.generated_at.isoformat(),
            "counts": report.counts,
            "summary": report.summary,
            "issues": [
                {
                    "level": i.level,
                    "category": i.category,
                    "entity_type": i.entity_type,
                    "entity_id": i.entity_id,
                    "message": i.message,
                    "details": i.details,
                }
                for i in report.issues
            ],
            "has_errors": report.has_errors,
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
    "/import/{job_id}/generate-redirects",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def generate_import_redirects(
    request: Request,
    job_id: str,
    source_url: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Generate URL redirects for imported content."""
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

        # Generate redirects
        result = await import_svc.generate_redirects(job_id, source_url)

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
