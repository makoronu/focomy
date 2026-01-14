"""WidgetService - sidebar and footer widget management.

Provides customizable widgets for sidebars and footers.
Each widget type has its own rendering logic.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


@dataclass
class WidgetContext:
    """Context passed to widget renderers."""

    db: AsyncSession
    entity_svc: EntityService
    request_context: dict[str, Any]


class BaseWidget(ABC):
    """Base class for all widgets."""

    name: str = "base"
    label: str = "Base Widget"

    @abstractmethod
    async def render(self, config: dict, context: WidgetContext) -> str:
        """Render the widget HTML."""
        pass


class RecentPostsWidget(BaseWidget):
    """Display recent posts."""

    name = "recent_posts"
    label = "Recent Posts"

    async def render(self, config: dict, context: WidgetContext) -> str:
        limit = config.get("limit", 5)

        posts = await context.entity_svc.find(
            "post",
            limit=limit,
            order_by="-created_at",
            filters={"status": "published"},
        )

        items = []
        for p in posts:
            data = context.entity_svc.serialize(p)
            title = data.get("title", "Untitled")
            slug = data.get("slug", "")
            date = data.get("created_at", "")[:10] if data.get("created_at") else ""
            items.append(
                f"""
                <li class="widget-post-item">
                    <a href="/post/{slug}">{title}</a>
                    <span class="widget-post-date">{date}</span>
                </li>
            """
            )

        return f"""
            <ul class="widget-posts-list">
                {"".join(items)}
            </ul>
        """


class CategoriesWidget(BaseWidget):
    """Display category list."""

    name = "categories"
    label = "Categories"

    async def render(self, config: dict, context: WidgetContext) -> str:
        config.get("show_count", True)

        categories = await context.entity_svc.find(
            "category",
            limit=50,
            order_by="name",
        )

        items = []
        for cat in categories:
            data = context.entity_svc.serialize(cat)
            name = data.get("name", "")
            slug = data.get("slug", "")
            items.append(
                f"""
                <li class="widget-category-item">
                    <a href="/category/{slug}">{name}</a>
                </li>
            """
            )

        return f"""
            <ul class="widget-categories-list">
                {"".join(items)}
            </ul>
        """


class ChannelListWidget(BaseWidget):
    """Display channel list."""

    name = "channel_list"
    label = "Channel List"

    async def render(self, config: dict, context: WidgetContext) -> str:
        channels = await context.entity_svc.find(
            "channel",
            limit=50,
            order_by="title",
        )

        items = []
        for ch in channels:
            data = context.entity_svc.serialize(ch)
            title = data.get("title", "")
            slug = data.get("slug", "")
            items.append(
                f"""
                <li class="widget-channel-item">
                    <a href="/channel/{slug}">{title}</a>
                </li>
            """
            )

        return f"""
            <ul class="widget-channels-list">
                {"".join(items)}
            </ul>
        """


class SeriesListWidget(BaseWidget):
    """Display series list."""

    name = "series_list"
    label = "Series List"

    async def render(self, config: dict, context: WidgetContext) -> str:
        series_list = await context.entity_svc.find(
            "series",
            limit=50,
            order_by="title",
        )

        items = []
        for s in series_list:
            data = context.entity_svc.serialize(s)
            title = data.get("title", "")
            slug = data.get("slug", "")
            items.append(
                f"""
                <li class="widget-series-item">
                    <a href="/series/{slug}">{title}</a>
                </li>
            """
            )

        return f"""
            <ul class="widget-series-list">
                {"".join(items)}
            </ul>
        """


class SearchWidget(BaseWidget):
    """Display search form."""

    name = "search"
    label = "Search"

    async def render(self, config: dict, context: WidgetContext) -> str:
        placeholder = config.get("placeholder", "Search...")
        return f"""
            <form action="/search" method="GET" class="widget-search-form">
                <input type="text" name="q" placeholder="{placeholder}" class="widget-search-input">
                <button type="submit" class="widget-search-button">Search</button>
            </form>
        """


class ArchivesWidget(BaseWidget):
    """Display monthly archives."""

    name = "archives"
    label = "Archives"

    async def render(self, config: dict, context: WidgetContext) -> str:
        limit = config.get("limit", 12)

        # Get posts to extract unique months
        posts = await context.entity_svc.find(
            "post",
            limit=500,
            order_by="-created_at",
            filters={"status": "published"},
        )

        # Extract unique year-month combinations
        months = {}
        for p in posts:
            data = context.entity_svc.serialize(p)
            created = data.get("created_at", "")
            if created and len(created) >= 7:
                ym = created[:7]
                months[ym] = months.get(ym, 0) + 1

        # Sort and limit
        sorted_months = sorted(months.items(), reverse=True)[:limit]

        items = []
        for ym, count in sorted_months:
            year, month = ym.split("-")
            label = f"{year}年{month}月"
            items.append(
                f"""
                <li class="widget-archive-item">
                    <a href="/archive/{year}/{month}">{label}</a>
                    <span class="widget-archive-count">({count})</span>
                </li>
            """
            )

        return f"""
            <ul class="widget-archives-list">
                {"".join(items)}
            </ul>
        """


class CustomHtmlWidget(BaseWidget):
    """Display custom HTML content."""

    name = "custom_html"
    label = "Custom HTML"

    async def render(self, config: dict, context: WidgetContext) -> str:
        html = config.get("html", "")
        return f'<div class="widget-custom-html">{html}</div>'


class WidgetService:
    """
    Widget management and rendering service.

    Handles widget CRUD and rendering for all areas.
    """

    AREAS = ("sidebar", "footer_1", "footer_2", "footer_3")

    # Register widget types
    WIDGET_TYPES: dict[str, type[BaseWidget]] = {
        "recent_posts": RecentPostsWidget,
        "categories": CategoriesWidget,
        "channel_list": ChannelListWidget,
        "series_list": SeriesListWidget,
        "search": SearchWidget,
        "archives": ArchivesWidget,
        "custom_html": CustomHtmlWidget,
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def get_widgets_for_area(self, area: str) -> list[dict[str, Any]]:
        """Get all active widgets for an area."""
        if area not in self.AREAS:
            return []

        entities = await self.entity_svc.find(
            "widget",
            limit=50,
            order_by="sort_order",
            filters={"area": area, "is_active": True},
        )

        widgets = []
        for e in entities:
            data = self.entity_svc.serialize(e)
            # Parse config JSON
            config = data.get("config")
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}
            data["config"] = config or {}
            widgets.append(data)

        return widgets

    async def render_area(
        self,
        area: str,
        request_context: dict[str, Any] = None,
    ) -> str:
        """Render all widgets for an area."""
        widgets = await self.get_widgets_for_area(area)
        if not widgets:
            return ""

        context = WidgetContext(
            db=self.db,
            entity_svc=self.entity_svc,
            request_context=request_context or {},
        )

        rendered = []
        for widget_data in widgets:
            widget_type = widget_data.get("widget_type", "custom_html")
            title = widget_data.get("title", "")
            config = widget_data.get("config", {})

            # For custom_html, pass the HTML in config
            if widget_type == "custom_html":
                config["html"] = widget_data.get("custom_html", "")

            # Get widget class
            widget_class = self.WIDGET_TYPES.get(widget_type)
            if not widget_class:
                continue

            widget = widget_class()

            try:
                content = await widget.render(config, context)
            except Exception as e:
                content = f'<p class="widget-error">Widget error: {str(e)}</p>'

            title_html = f'<h3 class="widget-title">{title}</h3>' if title else ""
            rendered.append(
                f"""
                <div class="widget widget--{widget_type}">
                    {title_html}
                    <div class="widget-content">
                        {content}
                    </div>
                </div>
            """
            )

        return "\n".join(rendered)

    async def render_all_areas(
        self,
        request_context: dict[str, Any] = None,
    ) -> dict[str, str]:
        """Render all widget areas."""
        return {area: await self.render_area(area, request_context) for area in self.AREAS}

    async def create_widget(
        self,
        widget_type: str,
        area: str,
        title: str = "",
        config: dict = None,
        custom_html: str = "",
        sort_order: int = 0,
        user_id: str = None,
    ):
        """Create a new widget."""
        data = {
            "title": title,
            "widget_type": widget_type,
            "area": area,
            "sort_order": sort_order,
            "config": json.dumps(config or {}),
            "custom_html": custom_html,
            "is_active": True,
        }
        return await self.entity_svc.create("widget", data, user_id)

    async def update_widget(
        self,
        widget_id: str,
        data: dict[str, Any],
        user_id: str = None,
    ):
        """Update a widget."""
        if "config" in data and isinstance(data["config"], dict):
            data["config"] = json.dumps(data["config"])
        return await self.entity_svc.update(widget_id, data, user_id, create_revision=False)

    async def delete_widget(self, widget_id: str, user_id: str = None) -> bool:
        """Delete a widget."""
        return await self.entity_svc.delete(widget_id, user_id)

    async def reorder_widgets(
        self,
        area: str,
        widget_orders: list[dict[str, Any]],
        user_id: str = None,
    ) -> bool:
        """Reorder widgets in an area."""
        for order in widget_orders:
            widget_id = order["id"]
            sort_order = order.get("sort_order", 0)
            await self.update_widget(
                widget_id,
                {"sort_order": sort_order},
                user_id=user_id,
            )
        return True

    @classmethod
    def get_available_widget_types(cls) -> list[dict[str, str]]:
        """Get list of available widget types."""
        return [
            {"value": name, "label": widget_class.label}
            for name, widget_class in cls.WIDGET_TYPES.items()
        ]
