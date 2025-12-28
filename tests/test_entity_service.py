"""Tests for EntityService.

Tests entity CRUD operations, soft delete, and unique constraints.
"""

import pytest
import pytest_asyncio
from datetime import datetime

from core.services.entity import EntityService
from core.models import Entity


class TestEntityService:
    """EntityService test cases."""

    @pytest.mark.asyncio
    async def test_create_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test creating a new entity."""
        entity = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        assert entity is not None
        assert entity.type == "post"
        assert entity.id is not None
        assert entity.created_at is not None
        assert entity.created_by == "test_user"

    @pytest.mark.asyncio
    async def test_get_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test retrieving an entity by ID."""
        created = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        retrieved = await entity_service.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.type == "post"

    @pytest.mark.asyncio
    async def test_update_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test updating an entity."""
        entity = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        updated = await entity_service.update(
            entity_id=entity.id,
            values={"title": "Updated Title"},
            user_id="test_user",
        )

        assert updated is not None
        assert updated.updated_at is not None
        assert updated.updated_by == "test_user"

    @pytest.mark.asyncio
    async def test_soft_delete_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test soft deleting an entity."""
        entity = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        result = await entity_service.delete(entity.id, user_id="test_user")
        assert result is True

        # Should not be found with normal get
        deleted = await entity_service.get(entity.id)
        assert deleted is None

        # Should be found with include_deleted
        deleted = await entity_service.get(entity.id, include_deleted=True)
        assert deleted is not None
        assert deleted.deleted_at is not None

    @pytest.mark.asyncio
    async def test_restore_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test restoring a soft-deleted entity."""
        entity = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        await entity_service.delete(entity.id, user_id="test_user")
        restored = await entity_service.restore(entity.id, user_id="test_user")

        assert restored is not None
        assert restored.deleted_at is None

    @pytest.mark.asyncio
    async def test_list_entities(self, entity_service: EntityService, sample_post_data: dict):
        """Test listing entities of a type."""
        # Create multiple entities
        for i in range(5):
            data = sample_post_data.copy()
            data["slug"] = f"test-post-{i}"
            await entity_service.create(
                type_name="post",
                values=data,
                user_id="test_user",
            )

        entities = await entity_service.list("post", limit=10)

        assert len(entities) == 5

    @pytest.mark.asyncio
    async def test_list_deleted_entities(self, entity_service: EntityService, sample_post_data: dict):
        """Test listing only deleted entities."""
        # Create and delete entities
        for i in range(3):
            data = sample_post_data.copy()
            data["slug"] = f"deleted-post-{i}"
            entity = await entity_service.create(
                type_name="post",
                values=data,
                user_id="test_user",
            )
            await entity_service.delete(entity.id, user_id="test_user")

        # Create a non-deleted entity
        data = sample_post_data.copy()
        data["slug"] = "active-post"
        await entity_service.create(
            type_name="post",
            values=data,
            user_id="test_user",
        )

        deleted = await entity_service.list_deleted("post")

        assert len(deleted) == 3

    @pytest.mark.asyncio
    async def test_entity_version_increment(self, entity_service: EntityService, sample_post_data: dict):
        """Test that entity version increments on update."""
        entity = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        initial_version = entity.version or 1

        updated = await entity_service.update(
            entity_id=entity.id,
            values={"title": "Updated Title"},
            user_id="test_user",
        )

        assert updated.version == initial_version + 1


class TestEntityUniqueness:
    """Test unique constraint enforcement."""

    @pytest.mark.asyncio
    async def test_duplicate_slug_rejected(self, entity_service: EntityService, sample_post_data: dict):
        """Test that duplicate slugs are rejected."""
        await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        # Try to create another with same slug
        with pytest.raises(ValueError, match="unique"):
            await entity_service.create(
                type_name="post",
                values=sample_post_data,
                user_id="test_user",
            )

    @pytest.mark.asyncio
    async def test_unique_slug_across_types(self, entity_service: EntityService, sample_post_data: dict, sample_page_data: dict):
        """Test that slugs can be duplicated across different types."""
        sample_post_data["slug"] = "shared-slug"
        sample_page_data["slug"] = "shared-slug"

        post = await entity_service.create(
            type_name="post",
            values=sample_post_data,
            user_id="test_user",
        )

        page = await entity_service.create(
            type_name="page",
            values=sample_page_data,
            user_id="test_user",
        )

        assert post is not None
        assert page is not None
