"""Query Optimizer - Helpers for efficient large dataset queries.

Provides utilities for:
- Lazy loading
- Query optimization hints
- Chunked processing
- Efficient counting
"""

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


@dataclass
class QueryStats:
    """Statistics about a query result."""

    total: int
    page: int
    per_page: int
    has_more: bool
    estimated: bool = False  # True if count is estimated


class QueryOptimizer:
    """
    Query optimization utilities for large datasets.

    Usage:
        optimizer = QueryOptimizer(db)

        # Efficient count (uses estimation for large tables)
        count = await optimizer.fast_count(Entity, Entity.type == "post")

        # Chunked processing
        async for batch in optimizer.chunked_query(query, chunk_size=100):
            process(batch)
    """

    # Threshold for using estimated counts
    ESTIMATE_THRESHOLD = 100000

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fast_count(
        self,
        model: Any,
        *conditions,
        use_estimate: bool = True,
    ) -> tuple[int, bool]:
        """
        Get count efficiently, using estimation for large tables.

        Args:
            model: SQLAlchemy model
            *conditions: Filter conditions
            use_estimate: Whether to use pg_class estimation

        Returns:
            Tuple of (count, is_estimated)
        """
        # First try exact count with limit check
        if use_estimate:
            # Check if we should use estimation
            check_query = select(func.count()).select_from(model)
            for cond in conditions:
                check_query = check_query.where(cond)
            check_query = check_query.limit(self.ESTIMATE_THRESHOLD + 1)

            result = await self.db.execute(check_query)
            check_count = result.scalar() or 0

            if check_count > self.ESTIMATE_THRESHOLD:
                # Use PostgreSQL's estimate
                estimate = await self._get_pg_estimate(model.__tablename__)
                if estimate:
                    return estimate, True

        # Exact count
        query = select(func.count()).select_from(model)
        for cond in conditions:
            query = query.where(cond)

        result = await self.db.execute(query)
        return result.scalar() or 0, False

    async def _get_pg_estimate(self, table_name: str) -> int | None:
        """Get PostgreSQL's row count estimate from pg_class."""
        try:
            from sqlalchemy import text

            result = await self.db.execute(
                text("SELECT reltuples::bigint FROM pg_class WHERE relname = :table"),
                {"table": table_name},
            )
            row = result.first()
            return row[0] if row else None
        except Exception:
            return None

    async def chunked_query(
        self,
        query,
        chunk_size: int = 100,
        id_column: Any = None,
    ) -> AsyncGenerator[list, None]:
        """
        Execute query in chunks for memory efficiency.

        Args:
            query: SQLAlchemy query
            chunk_size: Number of records per chunk
            id_column: Column to use for cursor (default: id)

        Yields:
            Lists of records
        """
        last_id = None

        while True:
            chunk_query = query.limit(chunk_size)

            if last_id is not None and id_column is not None:
                chunk_query = chunk_query.where(id_column > last_id)

            result = await self.db.execute(chunk_query)
            records = result.scalars().all()

            if not records:
                break

            yield list(records)

            if len(records) < chunk_size:
                break

            if id_column is not None:
                last_id = getattr(records[-1], id_column.key, None)
            else:
                # Fall back to offset-based (less efficient)
                break

    async def stream_process(
        self,
        query,
        processor: Callable[[Any], None],
        chunk_size: int = 100,
    ) -> int:
        """
        Stream and process records without loading all into memory.

        Args:
            query: SQLAlchemy query
            processor: Function to call for each record
            chunk_size: Processing chunk size

        Returns:
            Total records processed
        """
        total = 0
        offset = 0

        while True:
            chunk_query = query.limit(chunk_size).offset(offset)
            result = await self.db.execute(chunk_query)
            records = result.scalars().all()

            if not records:
                break

            for record in records:
                processor(record)
                total += 1

            if len(records) < chunk_size:
                break

            offset += chunk_size

        return total


class LazyLoader:
    """
    Lazy loading helper for related entities.

    Prevents N+1 queries by batching lookups.

    Usage:
        loader = LazyLoader(db)

        # Register IDs to load
        for entity in entities:
            loader.add("user", entity.created_by)

        # Batch load
        await loader.load_all()

        # Get loaded entity
        user = loader.get("user", entity.created_by)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._pending: dict[str, set[str]] = {}
        self._loaded: dict[str, dict[str, Any]] = {}

    def add(self, entity_type: str, entity_id: str | None) -> None:
        """Add an entity ID to load."""
        if entity_id is None:
            return
        if entity_type not in self._pending:
            self._pending[entity_type] = set()
        self._pending[entity_type].add(entity_id)

    def get(self, entity_type: str, entity_id: str) -> Any | None:
        """Get a loaded entity."""
        return self._loaded.get(entity_type, {}).get(entity_id)

    async def load_all(self) -> None:
        """Batch load all pending entities."""
        from ..models import Entity

        for entity_type, ids in self._pending.items():
            if not ids:
                continue

            query = select(Entity).where(
                Entity.id.in_(list(ids)),
                Entity.deleted_at.is_(None),
            )
            result = await self.db.execute(query)
            entities = result.scalars().all()

            if entity_type not in self._loaded:
                self._loaded[entity_type] = {}

            for entity in entities:
                self._loaded[entity_type][entity.id] = entity

        self._pending.clear()


# Utility functions


async def get_optimized_stats(
    db: AsyncSession,
    model: Any,
    page: int,
    per_page: int,
    *conditions,
) -> QueryStats:
    """Get paginated query stats efficiently."""
    optimizer = QueryOptimizer(db)
    total, estimated = await optimizer.fast_count(model, *conditions)

    return QueryStats(
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
        estimated=estimated,
    )
