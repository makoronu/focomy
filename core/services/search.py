"""SearchService - Full-text search with Japanese support.

Uses PostgreSQL pg_trgm for trigram-based fuzzy search,
which works well with Japanese text without requiring
morphological analysis.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService
from .field import field_service


@dataclass
class SearchResult:
    """Search result item."""

    entity_id: str
    entity_type: str
    title: str
    excerpt: str
    score: float
    url: str
    data: dict


class SearchService:
    """
    Full-text search service.

    Uses PostgreSQL pg_trgm extension for fuzzy trigram matching.
    This works well with Japanese text without needing mecab or similar.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def ensure_extension(self) -> bool:
        """Ensure pg_trgm extension is installed.

        Returns True if extension is available.
        """
        try:
            await self.db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False

    async def search(
        self,
        query: str,
        types: list[str] = None,
        limit: int = 20,
        offset: int = 0,
        filters: dict = None,
    ) -> tuple[list[SearchResult], int]:
        """Search entities by query string.

        Args:
            query: Search query string
            types: Content types to search (None = all searchable types)
            limit: Maximum results
            offset: Skip results
            filters: Additional filters

        Returns:
            Tuple of (results list, total count)
        """
        if not query or len(query.strip()) < 2:
            return [], 0

        query = query.strip()

        # Get searchable content types
        if types is None:
            types = self._get_searchable_types()

        if not types:
            return [], 0

        # Get searchable fields for each type
        searchable_fields = self._get_searchable_fields(types)

        # Build search query using pg_trgm similarity
        results = await self._execute_search(
            query=query,
            types=types,
            searchable_fields=searchable_fields,
            limit=limit,
            offset=offset,
            filters=filters,
        )

        # Get total count
        total = await self._count_search_results(
            query=query,
            types=types,
            searchable_fields=searchable_fields,
            filters=filters,
        )

        return results, total

    def _get_searchable_types(self) -> list[str]:
        """Get content types marked as searchable."""
        content_types = field_service.get_all_content_types()
        return [name for name, ct in content_types.items() if ct.searchable]

    def _get_searchable_fields(self, types: list[str]) -> dict[str, list[str]]:
        """Get searchable fields for each content type."""
        result = {}
        for type_name in types:
            ct = field_service.get_content_type(type_name)
            if ct:
                # Default searchable fields
                fields = ["title", "name", "slug"]
                # Add fields marked as searchable
                for field in ct.fields:
                    if field.searchable and field.name not in fields:
                        fields.append(field.name)
                    # Also search text/string fields by default
                    if field.type in ("string", "text") and field.name not in fields:
                        if not field.admin_hidden and not field.auth_field:
                            fields.append(field.name)
                result[type_name] = fields
        return result

    async def _execute_search(
        self,
        query: str,
        types: list[str],
        searchable_fields: dict[str, list[str]],
        limit: int,
        offset: int,
        filters: dict = None,
    ) -> list[SearchResult]:
        """Execute search query and return results."""
        # Build a union of all searchable field values
        # Using pg_trgm similarity for ranking

        # Get all unique field names
        all_fields = set()
        for fields in searchable_fields.values():
            all_fields.update(fields)

        # Search in entity_values using trigram similarity
        sql = text(
            """
            WITH search_matches AS (
                SELECT DISTINCT
                    e.id as entity_id,
                    e.type as entity_type,
                    MAX(similarity(ev.value_text, :query)) as score
                FROM entities e
                JOIN entity_values ev ON e.id = ev.entity_id
                WHERE e.deleted_at IS NULL
                    AND e.type = ANY(:types)
                    AND ev.field_name = ANY(:fields)
                    AND ev.value_text IS NOT NULL
                    AND ev.value_text % :query
                GROUP BY e.id, e.type
            )
            SELECT
                sm.entity_id,
                sm.entity_type,
                sm.score
            FROM search_matches sm
            ORDER BY sm.score DESC
            LIMIT :limit OFFSET :offset
        """
        )

        try:
            result = await self.db.execute(
                sql,
                {
                    "query": query,
                    "types": types,
                    "fields": list(all_fields),
                    "limit": limit,
                    "offset": offset,
                },
            )
            rows = result.fetchall()
        except Exception:
            # pg_trgm might not be available, fall back to LIKE
            # Rollback aborted transaction before fallback
            await self.db.rollback()
            return await self._fallback_search(query, types, searchable_fields, limit, offset)

        # Build search results
        results = []
        for row in rows:
            entity_id, entity_type, score = row
            entity = await self.entity_svc.get(entity_id)
            if entity:
                data = self.entity_svc.serialize(entity)
                results.append(
                    SearchResult(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        title=data.get("title") or data.get("name") or "",
                        excerpt=self._generate_excerpt(data, query),
                        score=float(score),
                        url=self._get_entity_url(entity_type, data),
                        data=data,
                    )
                )

        return results

    async def _fallback_search(
        self,
        query: str,
        types: list[str],
        searchable_fields: dict[str, list[str]],
        limit: int,
        offset: int,
    ) -> list[SearchResult]:
        """Fallback to LIKE-based search when pg_trgm is not available."""
        all_fields = set()
        for fields in searchable_fields.values():
            all_fields.update(fields)

        # Use ILIKE for case-insensitive matching
        like_pattern = f"%{query}%"

        sql = text(
            """
            SELECT DISTINCT
                e.id as entity_id,
                e.type as entity_type,
                e.updated_at
            FROM entities e
            JOIN entity_values ev ON e.id = ev.entity_id
            WHERE e.deleted_at IS NULL
                AND e.type = ANY(:types)
                AND ev.field_name = ANY(:fields)
                AND ev.value_text ILIKE :pattern
            ORDER BY e.updated_at DESC
            LIMIT :limit OFFSET :offset
        """
        )

        result = await self.db.execute(
            sql,
            {
                "types": types,
                "fields": list(all_fields),
                "pattern": like_pattern,
                "limit": limit,
                "offset": offset,
            },
        )
        rows = result.fetchall()

        results = []
        for row in rows:
            entity_id, entity_type, _ = row  # _ is updated_at, used only for ordering
            entity = await self.entity_svc.get(entity_id)
            if entity:
                data = self.entity_svc.serialize(entity)
                results.append(
                    SearchResult(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        title=data.get("title") or data.get("name") or "",
                        excerpt=self._generate_excerpt(data, query),
                        score=1.0,
                        url=self._get_entity_url(entity_type, data),
                        data=data,
                    )
                )

        return results

    async def _count_search_results(
        self,
        query: str,
        types: list[str],
        searchable_fields: dict[str, list[str]],
        filters: dict = None,
    ) -> int:
        """Count total search results."""
        all_fields = set()
        for fields in searchable_fields.values():
            all_fields.update(fields)

        try:
            sql = text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_values ev ON e.id = ev.entity_id
                WHERE e.deleted_at IS NULL
                    AND e.type = ANY(:types)
                    AND ev.field_name = ANY(:fields)
                    AND ev.value_text IS NOT NULL
                    AND ev.value_text % :query
            """
            )

            result = await self.db.execute(
                sql,
                {
                    "query": query,
                    "types": types,
                    "fields": list(all_fields),
                },
            )
            return result.scalar() or 0
        except Exception:
            # Rollback aborted transaction before fallback
            await self.db.rollback()
            # Fallback to LIKE count
            sql = text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_values ev ON e.id = ev.entity_id
                WHERE e.deleted_at IS NULL
                    AND e.type = ANY(:types)
                    AND ev.field_name = ANY(:fields)
                    AND ev.value_text ILIKE :pattern
            """
            )

            result = await self.db.execute(
                sql,
                {
                    "types": types,
                    "fields": list(all_fields),
                    "pattern": f"%{query}%",
                },
            )
            return result.scalar() or 0

    def _generate_excerpt(self, data: dict, query: str, max_length: int = 200) -> str:
        """Generate excerpt with query highlighted."""
        # Try excerpt field first
        text_content = data.get("excerpt") or data.get("body") or ""

        # If body is blocks, extract text
        if isinstance(text_content, list):
            text_content = self._extract_text_from_blocks(text_content)

        if not text_content:
            return ""

        # Truncate if too long
        if len(text_content) > max_length:
            # Try to find query in text and center around it
            query_lower = query.lower()
            text_lower = text_content.lower()
            pos = text_lower.find(query_lower)

            if pos >= 0:
                # Center around the match
                start = max(0, pos - max_length // 2)
                end = min(len(text_content), pos + len(query) + max_length // 2)
                text_content = text_content[start:end]
                if start > 0:
                    text_content = "..." + text_content
                if end < len(text_content):
                    text_content = text_content + "..."
            else:
                text_content = text_content[:max_length] + "..."

        return text_content

    def _extract_text_from_blocks(self, blocks: list) -> str:
        """Extract plain text from Editor.js blocks."""
        texts = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            block_data = block.get("data", {})

            if block_type == "paragraph":
                texts.append(block_data.get("text", ""))
            elif block_type == "header":
                texts.append(block_data.get("text", ""))
            elif block_type == "list":
                items = block_data.get("items", [])
                texts.extend(items)
            elif block_type == "quote":
                texts.append(block_data.get("text", ""))

        return " ".join(texts)

    def _get_entity_url(self, entity_type: str, data: dict) -> str:
        """Generate URL for an entity."""
        ct = field_service.get_content_type(entity_type)
        if not ct:
            return f"/{entity_type}/{data.get('id')}"

        slug = data.get("slug") or data.get("id")
        prefix = ct.path_prefix.rstrip("/") if ct.path_prefix else f"/{entity_type}"

        return f"{prefix}/{slug}"

    async def create_search_indexes(self) -> list[str]:
        """Create GIN indexes for trigram search.

        Call this during migration to optimize search performance.
        """
        created = []

        # Create GIN index on value_text for trigram ops
        try:
            await self.db.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_entity_values_text_trgm
                ON entity_values
                USING gin (value_text gin_trgm_ops)
                WHERE value_text IS NOT NULL
            """
                )
            )
            await self.db.commit()
            created.append("idx_entity_values_text_trgm")
        except Exception:
            await self.db.rollback()
            # pg_trgm might not be available
            pass

        return created


async def get_search_suggestions(
    db: AsyncSession,
    query: str,
    limit: int = 5,
) -> list[str]:
    """Get search suggestions based on existing content.

    Returns titles/names that match the query prefix.
    """
    if not query or len(query) < 2:
        return []

    sql = text(
        """
        SELECT DISTINCT ev.value_text
        FROM entity_values ev
        JOIN entities e ON e.id = ev.entity_id
        WHERE e.deleted_at IS NULL
            AND ev.field_name IN ('title', 'name')
            AND ev.value_text ILIKE :pattern
        ORDER BY ev.value_text
        LIMIT :limit
    """
    )

    result = await db.execute(sql, {"pattern": f"{query}%", "limit": limit})

    return [row[0] for row in result.fetchall()]
