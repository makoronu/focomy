"""Pagination Service - Standardized pagination helpers.

Provides both offset-based and cursor-based pagination.
"""

import base64
import json
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


@dataclass
class PageInfo:
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResult(BaseModel, Generic[T]):
    """Standard paginated response."""

    items: list
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def create(
        cls,
        items: list,
        page: int,
        per_page: int,
        total: int,
    ) -> "PaginatedResult":
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return cls(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "pagination": {
                "page": self.page,
                "per_page": self.per_page,
                "total": self.total,
                "total_pages": self.total_pages,
                "has_next": self.has_next,
                "has_prev": self.has_prev,
            },
        }


@dataclass
class CursorInfo:
    """Cursor-based pagination metadata."""

    cursor: str | None
    limit: int
    has_more: bool
    next_cursor: str | None


class CursorPaginatedResult(BaseModel, Generic[T]):
    """Cursor-based paginated response."""

    items: list
    limit: int
    has_more: bool
    next_cursor: str | None

    @classmethod
    def create(
        cls,
        items: list,
        limit: int,
        cursor_field: str = "id",
    ) -> "CursorPaginatedResult":
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        next_cursor = None
        if items and has_more:
            last_item = items[-1]
            if isinstance(last_item, dict):
                cursor_value = last_item.get(cursor_field)
            else:
                cursor_value = getattr(last_item, cursor_field, None)
            if cursor_value:
                next_cursor = encode_cursor(cursor_value)

        return cls(
            items=items,
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "pagination": {
                "limit": self.limit,
                "has_more": self.has_more,
                "next_cursor": self.next_cursor,
            },
        }


def encode_cursor(value: Any) -> str:
    """Encode a cursor value."""
    data = json.dumps({"v": str(value)})
    return base64.urlsafe_b64encode(data.encode()).decode()


def decode_cursor(cursor: str) -> str | None:
    """Decode a cursor value."""
    try:
        data = base64.urlsafe_b64decode(cursor.encode())
        parsed = json.loads(data.decode())
        return parsed.get("v")
    except Exception:
        return None


class PaginationParams(BaseModel):
    """Standard pagination parameters."""

    page: int = 1
    per_page: int = 20
    cursor: str | None = None
    sort: str = "-created_at"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def decoded_cursor(self) -> str | None:
        if self.cursor:
            return decode_cursor(self.cursor)
        return None


def calculate_pages(total: int, per_page: int) -> int:
    """Calculate total pages."""
    if per_page <= 0:
        return 0
    return (total + per_page - 1) // per_page


def get_page_range(current: int, total_pages: int, window: int = 2) -> list[int]:
    """Get page numbers to display in pagination UI."""
    start = max(1, current - window)
    end = min(total_pages, current + window)

    pages = list(range(start, end + 1))

    # Add first page if not included
    if start > 1:
        pages = [1, ...] + pages if start > 2 else [1] + pages

    # Add last page if not included
    if end < total_pages:
        pages = pages + [..., total_pages] if end < total_pages - 1 else pages + [total_pages]

    return pages
