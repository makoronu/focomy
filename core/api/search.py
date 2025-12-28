"""Search API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.search import SearchService, get_search_suggestions

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=2, description="Search query"),
    types: str = Query(None, description="Comma-separated content types"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search content across the site.

    Args:
        q: Search query (minimum 2 characters)
        types: Optional comma-separated list of content types to search
        page: Page number (1-based)
        per_page: Results per page

    Returns:
        Search results with pagination info
    """
    search_svc = SearchService(db)

    type_list = None
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]

    offset = (page - 1) * per_page
    results, total = await search_svc.search(
        query=q,
        types=type_list,
        limit=per_page,
        offset=offset,
    )

    return {
        "query": q,
        "results": [
            {
                "id": r.entity_id,
                "type": r.entity_type,
                "title": r.title,
                "excerpt": r.excerpt,
                "score": r.score,
                "url": r.url,
            }
            for r in results
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    }


@router.get("/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=2, description="Search query prefix"),
    limit: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """Get search suggestions for autocomplete.

    Args:
        q: Query prefix (minimum 2 characters)
        limit: Maximum suggestions

    Returns:
        List of suggestion strings
    """
    suggestions = await get_search_suggestions(db, q, limit)
    return {"suggestions": suggestions}
