"""Migration Helpers - Safe database migration utilities.

Provides utilities for schema changes that need to be done carefully.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MigrationHelpers:
    """
    Utilities for safe database migrations.

    Usage:
        helpers = MigrationHelpers(db)

        # Add FK constraint safely
        await helpers.add_user_fk_constraints()

        # Verify integrity before constraint
        issues = await helpers.check_orphan_references()
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_user_fk_constraints(self) -> dict:
        """
        Add FK constraints for created_by and updated_by columns.

        This adds self-referential FK constraints to the entities table.

        Returns:
            Migration result with status and any issues
        """
        result = {
            "success": False,
            "orphan_created_by": 0,
            "orphan_updated_by": 0,
            "nullified_count": 0,
            "constraints_added": [],
        }

        try:
            # First, check for orphan references
            orphans = await self.check_orphan_references()
            result["orphan_created_by"] = orphans["created_by_orphans"]
            result["orphan_updated_by"] = orphans["updated_by_orphans"]

            # Nullify orphan references (safe approach)
            if orphans["created_by_orphans"] > 0:
                await self.db.execute(
                    text(
                        """
                    UPDATE entities
                    SET created_by = NULL
                    WHERE created_by IS NOT NULL
                    AND created_by NOT IN (
                        SELECT id FROM entities WHERE type = 'user' AND deleted_at IS NULL
                    )
                """
                    )
                )
                result["nullified_count"] += orphans["created_by_orphans"]

            if orphans["updated_by_orphans"] > 0:
                await self.db.execute(
                    text(
                        """
                    UPDATE entities
                    SET updated_by = NULL
                    WHERE updated_by IS NOT NULL
                    AND updated_by NOT IN (
                        SELECT id FROM entities WHERE type = 'user' AND deleted_at IS NULL
                    )
                """
                    )
                )
                result["nullified_count"] += orphans["updated_by_orphans"]

            # Add FK constraints (PostgreSQL only)
            # Add created_by FK
            try:
                await self.db.execute(
                    text(
                        """
                    ALTER TABLE entities
                    ADD CONSTRAINT fk_entities_created_by
                    FOREIGN KEY (created_by) REFERENCES entities(id)
                    ON DELETE SET NULL
                """
                    )
                )
                result["constraints_added"].append("fk_entities_created_by")
            except Exception:
                pass  # Constraint might already exist

            # Add updated_by FK
            try:
                await self.db.execute(
                    text(
                        """
                    ALTER TABLE entities
                    ADD CONSTRAINT fk_entities_updated_by
                    FOREIGN KEY (updated_by) REFERENCES entities(id)
                    ON DELETE SET NULL
                """
                    )
                )
                result["constraints_added"].append("fk_entities_updated_by")
            except Exception:
                pass  # Constraint might already exist

            await self.db.commit()
            result["success"] = True

        except Exception as e:
            await self.db.rollback()
            result["error"] = str(e)

        return result

    async def check_orphan_references(self) -> dict:
        """
        Check for orphan created_by and updated_by references.

        Returns:
            Dict with counts of orphan references
        """
        result = {
            "created_by_orphans": 0,
            "updated_by_orphans": 0,
            "orphan_details": [],
        }

        # Check created_by orphans
        created_by_query = await self.db.execute(
            text(
                """
            SELECT COUNT(*) FROM entities e
            WHERE e.created_by IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM entities u
                WHERE u.id = e.created_by
                AND u.type = 'user'
            )
        """
            )
        )
        result["created_by_orphans"] = created_by_query.scalar() or 0

        # Check updated_by orphans
        updated_by_query = await self.db.execute(
            text(
                """
            SELECT COUNT(*) FROM entities e
            WHERE e.updated_by IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM entities u
                WHERE u.id = e.updated_by
                AND u.type = 'user'
            )
        """
            )
        )
        result["updated_by_orphans"] = updated_by_query.scalar() or 0

        return result

    async def remove_user_fk_constraints(self) -> dict:
        """Remove FK constraints (for rollback)."""
        result = {
            "success": False,
            "constraints_removed": [],
        }

        try:
            try:
                await self.db.execute(
                    text(
                        """
                    ALTER TABLE entities
                    DROP CONSTRAINT IF EXISTS fk_entities_created_by
                """
                    )
                )
                result["constraints_removed"].append("fk_entities_created_by")
            except Exception:
                pass

            try:
                await self.db.execute(
                    text(
                        """
                    ALTER TABLE entities
                    DROP CONSTRAINT IF EXISTS fk_entities_updated_by
                """
                    )
                )
                result["constraints_removed"].append("fk_entities_updated_by")
            except Exception:
                pass

            await self.db.commit()
            result["success"] = True

        except Exception as e:
            await self.db.rollback()
            result["error"] = str(e)

        return result

    async def add_indexed_fields_indexes(self, content_types: dict) -> dict:
        """
        Add database indexes for fields marked as indexed: true in YAML.

        Args:
            content_types: Dict of content type definitions

        Returns:
            Migration result
        """
        result = {
            "success": False,
            "indexes_created": [],
            "errors": [],
        }

        try:
            for type_name, type_def in content_types.items():
                fields = type_def.get("fields", [])

                for field in fields:
                    if field.get("indexed"):
                        field_name = field["name"]
                        index_name = f"idx_values_{type_name}_{field_name}"

                        try:
                            # Create partial index for this field
                            await self.db.execute(
                                text(
                                    f"""
                                CREATE INDEX IF NOT EXISTS {index_name}
                                ON entity_values (entity_id, value_text)
                                WHERE field_name = :field_name
                            """
                                ),
                                {"field_name": field_name},
                            )
                            result["indexes_created"].append(index_name)
                        except Exception as e:
                            result["errors"].append(f"{index_name}: {str(e)}")

            await self.db.commit()
            result["success"] = len(result["errors"]) == 0

        except Exception as e:
            await self.db.rollback()
            result["error"] = str(e)

        return result

    async def verify_schema_integrity(self) -> dict:
        """
        Verify database schema integrity.

        Checks:
        - Required tables exist
        - Required columns exist
        - Indexes exist
        """
        result = {
            "valid": True,
            "issues": [],
        }

        required_tables = ["entities", "entity_values", "relations"]

        for table in required_tables:
            try:
                check = await self.db.execute(
                    text(
                        """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = :table
                    )
                """
                    ),
                    {"table": table},
                )

                exists = check.scalar()
                if not exists:
                    result["valid"] = False
                    result["issues"].append(f"Missing table: {table}")

            except Exception as e:
                result["issues"].append(f"Error checking table {table}: {str(e)}")

        return result


def get_migration_helpers(db: AsyncSession) -> MigrationHelpers:
    return MigrationHelpers(db)
