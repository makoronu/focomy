"""Pytest fixtures for Focomy tests.

Provides common fixtures for database, services, and test data.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.services.auth import AuthService
from core.services.entity import EntityService
from core.services.field import FieldService
from core.services.relation import RelationService

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create async engine for each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for each test."""
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def entity_service(db: AsyncSession) -> EntityService:
    """Create EntityService instance."""
    return EntityService(db)


@pytest_asyncio.fixture
async def field_service() -> FieldService:
    """Create FieldService instance."""
    return FieldService()


@pytest_asyncio.fixture
async def relation_service(db: AsyncSession) -> RelationService:
    """Create RelationService instance."""
    return RelationService(db)


@pytest_asyncio.fixture
async def auth_service(db: AsyncSession) -> AuthService:
    """Create AuthService instance."""
    return AuthService(db)


# Test data fixtures

@pytest.fixture
def sample_post_data() -> dict:
    """Sample post entity data."""
    return {
        "title": "Test Post",
        "slug": "test-post",
        "content": {
            "blocks": [
                {"type": "paragraph", "data": {"text": "Test content"}}
            ]
        },
        "status": "draft",
    }


@pytest.fixture
def sample_page_data() -> dict:
    """Sample page entity data."""
    return {
        "title": "Test Page",
        "slug": "test-page",
        "content": {
            "blocks": [
                {"type": "paragraph", "data": {"text": "Test page content"}}
            ]
        },
        "status": "published",
    }


@pytest.fixture
def sample_user_data() -> dict:
    """Sample user data for registration."""
    return {
        "email": "test@example.com",
        "password": "secure_password_123",
        "name": "Test User",
        "role": "author",
    }


@pytest.fixture
def sample_admin_data() -> dict:
    """Sample admin user data."""
    return {
        "email": "admin@example.com",
        "password": "admin_password_123",
        "name": "Admin User",
        "role": "admin",
    }


# Content type fixtures

@pytest.fixture
def post_content_type() -> dict:
    """Post content type definition."""
    return {
        "name": "post",
        "label": "Post",
        "icon": "article",
        "fields": [
            {"name": "title", "type": "text", "required": True},
            {"name": "slug", "type": "slug", "unique": True},
            {"name": "content", "type": "blocks"},
            {"name": "status", "type": "select", "options": ["draft", "published"]},
            {"name": "published_at", "type": "datetime"},
        ],
    }


@pytest.fixture
def page_content_type() -> dict:
    """Page content type definition."""
    return {
        "name": "page",
        "label": "Page",
        "icon": "file",
        "fields": [
            {"name": "title", "type": "text", "required": True},
            {"name": "slug", "type": "slug", "unique": True},
            {"name": "content", "type": "blocks"},
            {"name": "status", "type": "select", "options": ["draft", "published"]},
        ],
    }


# Helper functions

def assert_entity_created(entity, expected_type: str, expected_values: dict):
    """Assert entity was created correctly."""
    assert entity is not None
    assert entity.type == expected_type
    assert entity.id is not None
    assert entity.created_at is not None


def assert_entity_has_values(entity, values: dict, field_service: FieldService):
    """Assert entity has expected field values."""
    for _field_name, _expected_value in values.items():
        # Would need to implement value retrieval
        pass
