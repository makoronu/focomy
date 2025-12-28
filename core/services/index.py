"""
Index Service - Create database indexes for indexed fields.

Reads YAML content type definitions and creates appropriate indexes.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .field import field_service


class IndexService:
    """Service for managing database indexes based on YAML field definitions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_indexes_for_all_types(self) -> dict[str, list[str]]:
        """
        Create indexes for all indexed fields in all content types.

        Returns:
            Dict mapping content type to list of created index names
        """
        results = {}
        content_types = field_service.get_all_content_types()

        for type_name, ct in content_types.items():
            created = await self.create_indexes_for_type(type_name, ct)
            if created:
                results[type_name] = created

        return results

    async def create_indexes_for_type(self, type_name: str, content_type) -> list[str]:
        """
        Create indexes for indexed fields in a content type.

        Returns:
            List of created index names
        """
        created = []

        for field in content_type.fields:
            if not field.indexed:
                continue

            index_name = await self._create_field_index(type_name, field)
            if index_name:
                created.append(index_name)

        return created

    async def _create_field_index(self, type_name: str, field) -> str | None:
        """
        Create an index for a single field.

        Creates a partial index on entity_values for the specific field_name
        and value column based on field type.
        """
        # Determine which value column to index based on field type
        storage_type = self._get_storage_type(field.type)
        value_column = f"value_{storage_type}"

        # Create a unique index name
        index_name = f"idx_{type_name}_{field.name}"

        # Check if index already exists
        check_sql = text(
            """
            SELECT 1 FROM pg_indexes
            WHERE indexname = :index_name
        """
        )
        result = await self.db.execute(check_sql, {"index_name": index_name})
        if result.scalar():
            return None  # Index already exists

        # Create partial index for this field
        # This indexes only rows where field_name matches, making it efficient
        create_sql = text(
            f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON entity_values ({value_column})
            WHERE field_name = :field_name
        """
        )

        try:
            await self.db.execute(create_sql, {"field_name": field.name})
            await self.db.commit()
            return index_name
        except Exception as e:
            await self.db.rollback()
            print(f"Warning: Could not create index {index_name}: {e}")
            return None

    def _get_storage_type(self, field_type: str) -> str:
        """Map field type to storage column type."""
        type_mapping = {
            "string": "text",
            "text": "text",
            "slug": "text",
            "email": "text",
            "url": "text",
            "password": "text",
            "integer": "int",
            "float": "float",
            "boolean": "int",
            "datetime": "datetime",
            "date": "datetime",
            "select": "text",
            "multiselect": "json",
            "blocks": "json",
            "media": "text",
            "json": "json",
        }
        return type_mapping.get(field_type, "text")

    async def list_custom_indexes(self) -> list[dict[str, Any]]:
        """List all custom indexes created by this service."""
        sql = text(
            """
            SELECT indexname, tablename, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%_%'
            AND tablename = 'entity_values'
            ORDER BY indexname
        """
        )
        result = await self.db.execute(sql)
        rows = result.fetchall()

        return [
            {
                "name": row[0],
                "table": row[1],
                "definition": row[2],
            }
            for row in rows
        ]

    async def drop_index(self, index_name: str) -> bool:
        """Drop a custom index."""
        if not index_name.startswith("idx_"):
            return False

        try:
            sql = text(f"DROP INDEX IF EXISTS {index_name}")
            await self.db.execute(sql)
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False
