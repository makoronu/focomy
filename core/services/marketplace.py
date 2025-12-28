"""Plugin Marketplace Service."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue
from .entity import EntityService

# Price caps (in USD cents) - Anti-gouging policy
MAX_ONE_TIME_PRICE = 2000  # $20.00
MAX_SUBSCRIPTION_PRICE = 500  # $5.00/month


class MarketplaceService:
    """Service for plugin marketplace operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def list_plugins(
        self,
        category: str | None = None,
        search: str | None = None,
        featured_only: bool = False,
        sort_by: str = "downloads",
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Entity], int]:
        """List approved plugins with filters."""
        query = select(Entity).where(
            Entity.type == "plugin",
            Entity.deleted_at.is_(None),
        )

        # Only show approved plugins
        query = query.join(EntityValue, Entity.id == EntityValue.entity_id)
        query = query.where(
            EntityValue.field == "status",
            EntityValue.value_string == "approved",
        )

        # Category filter
        if category:
            category_subquery = select(EntityValue.entity_id).where(
                EntityValue.field == "category",
                EntityValue.value_string == category,
            )
            query = query.where(Entity.id.in_(category_subquery))

        # Featured filter
        if featured_only:
            featured_subquery = select(EntityValue.entity_id).where(
                EntityValue.field == "is_featured",
                EntityValue.value_boolean,
            )
            query = query.where(Entity.id.in_(featured_subquery))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Sorting
        if sort_by == "downloads":
            download_subquery = (
                select(EntityValue.entity_id, EntityValue.value_integer.label("downloads"))
                .where(EntityValue.field == "download_count")
                .subquery()
            )
            query = query.outerjoin(
                download_subquery, Entity.id == download_subquery.c.entity_id
            ).order_by(download_subquery.c.downloads.desc().nullslast())
        elif sort_by == "rating":
            rating_subquery = (
                select(EntityValue.entity_id, EntityValue.value_decimal.label("rating"))
                .where(EntityValue.field == "rating_average")
                .subquery()
            )
            query = query.outerjoin(
                rating_subquery, Entity.id == rating_subquery.c.entity_id
            ).order_by(rating_subquery.c.rating.desc().nullslast())
        elif sort_by == "newest":
            query = query.order_by(Entity.created_at.desc())
        elif sort_by == "price_low":
            price_subquery = (
                select(EntityValue.entity_id, EntityValue.value_integer.label("price"))
                .where(EntityValue.field == "price")
                .subquery()
            )
            query = query.outerjoin(
                price_subquery, Entity.id == price_subquery.c.entity_id
            ).order_by(price_subquery.c.price.asc().nullslast())

        # Pagination
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.db.execute(query.distinct())
        plugins = list(result.scalars().all())

        return plugins, total

    async def get_plugin_by_slug(self, slug: str) -> Entity | None:
        """Get plugin by slug."""
        return await self.entity_svc.get_by_slug("plugin", slug)

    async def validate_price(
        self,
        pricing_type: str,
        price: int | None,
        subscription_price: int | None,
    ) -> tuple[bool, str | None]:
        """Validate plugin pricing against caps."""
        if pricing_type == "free":
            return True, None

        if pricing_type == "one_time":
            if price is None or price < 0:
                return False, "価格を入力してください"
            if price > MAX_ONE_TIME_PRICE:
                return (
                    False,
                    f"価格は${MAX_ONE_TIME_PRICE / 100:.2f}以下にしてください（ぼったくり防止）",
                )

        if pricing_type == "subscription":
            if subscription_price is None or subscription_price < 0:
                return False, "月額を入力してください"
            if subscription_price > MAX_SUBSCRIPTION_PRICE:
                return (
                    False,
                    f"月額は${MAX_SUBSCRIPTION_PRICE / 100:.2f}以下にしてください（ぼったくり防止）",
                )

        return True, None

    async def increment_download(self, plugin_id: int) -> None:
        """Increment download count."""
        plugin = await self.entity_svc.get_by_id(plugin_id)
        if not plugin:
            return

        data = self.entity_svc.serialize(plugin)
        current_count = data.get("download_count", 0) or 0
        data["download_count"] = current_count + 1
        await self.entity_svc.update(plugin, data)

    async def submit_review(
        self,
        plugin_id: int,
        user_id: int,
        rating: int,
        title: str | None,
        content: str,
    ) -> Entity:
        """Submit a plugin review."""
        plugin = await self.entity_svc.get_by_id(plugin_id)
        if not plugin:
            raise ValueError("プラグインが見つかりません")

        # Validate rating
        if rating < 1 or rating > 5:
            raise ValueError("評価は1〜5の間で入力してください")

        # Create review
        plugin_data = self.entity_svc.serialize(plugin)
        review_data = {
            "rating": rating,
            "title": title,
            "content": content,
            "version_reviewed": plugin_data.get("version"),
            "status": "pending",
        }

        review = await self.entity_svc.create("plugin_review", review_data)

        # Set relations
        await self.entity_svc.set_relation(review, "plugin_review_plugin", [plugin_id])
        await self.entity_svc.set_relation(review, "plugin_review_user", [user_id])

        return review

    async def update_plugin_rating(self, plugin_id: int) -> None:
        """Recalculate and update plugin average rating."""
        # Get all approved reviews for this plugin
        query = (
            select(EntityValue.value_integer)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "plugin_review",
                Entity.deleted_at.is_(None),
                EntityValue.field == "rating",
            )
        )

        # TODO: Filter by plugin relation and approved status

        result = await self.db.execute(query)
        ratings = [r[0] for r in result.fetchall() if r[0] is not None]

        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            count = len(ratings)
        else:
            avg_rating = 0
            count = 0

        # Update plugin
        plugin = await self.entity_svc.get_by_id(plugin_id)
        if plugin:
            data = self.entity_svc.serialize(plugin)
            data["rating_average"] = round(avg_rating, 1)
            data["rating_count"] = count
            await self.entity_svc.update(plugin, data)

    async def get_developer_stats(self, developer_id: int) -> dict:
        """Get developer statistics."""
        # Get all plugins by this developer
        query = select(Entity).where(
            Entity.type == "plugin",
            Entity.deleted_at.is_(None),
        )

        result = await self.db.execute(query)
        plugins = list(result.scalars().all())

        total_downloads = 0
        total_earnings = 0
        plugin_count = 0

        for plugin in plugins:
            data = self.entity_svc.serialize(plugin)
            # TODO: Check developer relation
            total_downloads += data.get("download_count", 0) or 0
            plugin_count += 1

        return {
            "plugin_count": plugin_count,
            "total_downloads": total_downloads,
            "total_earnings": total_earnings,
        }

    def format_price(self, cents: int | None) -> str:
        """Format price in cents to display string."""
        if cents is None or cents == 0:
            return "無料"
        return f"${cents / 100:.2f}"


marketplace_service = MarketplaceService
