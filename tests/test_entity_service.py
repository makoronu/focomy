"""Tests for EntityService.

Tests entity CRUD operations, soft delete, and unique constraints.
"""

import pytest

from core.services.entity import EntityService, QueryParams


class TestEntityService:
    """EntityService test cases."""

    @pytest.mark.asyncio
    async def test_create_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test creating a new entity."""
        entity = await entity_service.create(
            type_name="post",
            data=sample_post_data,
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
            data=sample_post_data,
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
            data=sample_post_data,
            user_id="test_user",
        )

        updated = await entity_service.update(
            entity_id=entity.id,
            data={"title": "Updated Title"},
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
            data=sample_post_data,
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
            data=sample_post_data,
            user_id="test_user",
        )

        await entity_service.delete(entity.id, user_id="test_user")
        restored = await entity_service.restore(entity.id, user_id="test_user")

        assert restored is not None
        assert restored.deleted_at is None

    @pytest.mark.asyncio
    async def test_find_entities(self, entity_service: EntityService, sample_post_data: dict):
        """Test finding entities of a type."""
        # Create multiple entities
        for i in range(5):
            data = sample_post_data.copy()
            data["slug"] = f"test-post-{i}"
            await entity_service.create(
                type_name="post",
                data=data,
                user_id="test_user",
            )

        entities = await entity_service.find("post", limit=10)

        assert len(entities) == 5

    @pytest.mark.asyncio
    async def test_list_deleted_entities(
        self, entity_service: EntityService, sample_post_data: dict
    ):
        """Test listing only deleted entities."""
        # Create and delete entities
        for i in range(3):
            data = sample_post_data.copy()
            data["slug"] = f"deleted-post-{i}"
            entity = await entity_service.create(
                type_name="post",
                data=data,
                user_id="test_user",
            )
            await entity_service.delete(entity.id, user_id="test_user")

        # Create a non-deleted entity
        data = sample_post_data.copy()
        data["slug"] = "active-post"
        await entity_service.create(
            type_name="post",
            data=data,
            user_id="test_user",
        )

        # list_deleted returns (entities, count)
        deleted, count = await entity_service.list_deleted("post")

        assert len(deleted) == 3
        assert count == 3

    @pytest.mark.asyncio
    async def test_entity_version_increment(
        self, entity_service: EntityService, sample_post_data: dict
    ):
        """Test that entity version increments on update."""
        entity = await entity_service.create(
            type_name="post",
            data=sample_post_data,
            user_id="test_user",
        )

        initial_version = entity.version or 1

        updated = await entity_service.update(
            entity_id=entity.id,
            data={"title": "Updated Title"},
            user_id="test_user",
        )

        assert updated.version == initial_version + 1


class TestEntityUniqueness:
    """Test unique constraint enforcement."""

    @pytest.mark.asyncio
    async def test_duplicate_slug_rejected(
        self, entity_service: EntityService, sample_post_data: dict
    ):
        """Test that duplicate slugs are rejected."""
        await entity_service.create(
            type_name="post",
            data=sample_post_data,
            user_id="test_user",
        )

        # Try to create another with same slug
        with pytest.raises(ValueError, match="[Uu]nique"):
            await entity_service.create(
                type_name="post",
                data=sample_post_data,
                user_id="test_user",
            )

    @pytest.mark.asyncio
    async def test_unique_slug_across_types(
        self, entity_service: EntityService, sample_post_data: dict, sample_page_data: dict
    ):
        """Test that slugs can be duplicated across different types."""
        sample_post_data["slug"] = "shared-slug"
        sample_page_data["slug"] = "shared-slug"

        post = await entity_service.create(
            type_name="post",
            data=sample_post_data,
            user_id="test_user",
        )

        page = await entity_service.create(
            type_name="page",
            data=sample_page_data,
            user_id="test_user",
        )

        assert post is not None
        assert page is not None


class TestQueryParams:
    """Test QueryParams dataclass."""

    def test_query_params_defaults(self):
        """Test QueryParams default values."""
        params = QueryParams()

        assert params.filters == {}
        assert params.sort == "-created_at"
        assert params.page == 1
        assert params.per_page == 20
        assert params.include_deleted is False
        assert params.search == ""

    def test_query_params_with_values(self):
        """Test QueryParams with custom values."""
        params = QueryParams(
            filters={"status": "published"},
            sort="title",
            page=2,
            per_page=10,
        )

        assert params.filters == {"status": "published"}
        assert params.sort == "title"
        assert params.page == 2
        assert params.per_page == 10


class TestEntitySerialization:
    """Test entity serialization."""

    @pytest.mark.asyncio
    async def test_serialize_entity(self, entity_service: EntityService, sample_post_data: dict):
        """Test serializing an entity to dict."""
        entity = await entity_service.create(
            type_name="post",
            data=sample_post_data,
            user_id="test_user",
        )

        serialized = entity_service.serialize(entity)

        assert serialized["id"] == entity.id
        assert serialized["type"] == "post"
        assert serialized["created_by"] == "test_user"
        assert "created_at" in serialized
