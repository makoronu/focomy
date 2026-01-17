"""Channel service - Default channel management."""

import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService

logger = structlog.get_logger(__name__)

DEFAULT_CHANNEL_SLUG = "posts"


async def get_or_create_posts_channel(db: AsyncSession) -> str:
    """Get or create the default 'posts' channel.

    Returns:
        Channel entity ID
    """
    entity_svc = EntityService(db)

    # Try to find existing posts channel
    entities = await entity_svc.find(
        "channel",
        filters={"slug": DEFAULT_CHANNEL_SLUG},
        limit=1,
    )

    if entities:
        channel_id = entities[0].id
        logger.debug("found_posts_channel", channel_id=channel_id)
        return channel_id

    # Create posts channel
    entity = await entity_svc.create(
        "channel",
        {
            "title": "Posts",
            "slug": DEFAULT_CHANNEL_SLUG,
            "description": "Default channel for posts",
            "sort_order": 0,
        },
    )

    logger.info("created_posts_channel", channel_id=entity.id)
    return entity.id


def is_protected_channel(slug: str) -> bool:
    """Check if a channel is protected from deletion.

    Args:
        slug: Channel slug

    Returns:
        True if protected
    """
    return slug == DEFAULT_CHANNEL_SLUG
