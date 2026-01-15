"""MenuService - navigation menu management.

Database-only approach: menus are stored in DB.
YAML config is only used for initial import via import_from_yaml().
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import MenuItemConfig, settings
from ..models import Entity
from .entity import EntityService
from .field import field_service
from .relation import RelationService


@dataclass
class MenuItem:
    """Resolved menu item for rendering."""

    id: str
    label: str
    url: str
    target: str = "_self"
    icon: str = ""
    is_active: bool = True
    sort_order: int = 0
    children: list["MenuItem"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for templates."""
        return {
            "id": self.id,
            "label": self.label,
            "url": self.url,
            "target": self.target,
            "icon": self.icon,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "children": [c.to_dict() for c in self.children],
        }


class MenuService:
    """
    Menu management service.

    Provides menus for templates with hybrid YAML/DB approach.
    """

    LOCATIONS = ("header", "footer", "sidebar")

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self.relation_svc = RelationService(db)

    async def get_menu(self, location: str) -> list[MenuItem]:
        """
        Get menu items for a location.

        Returns DB items only. No YAML fallback.
        """
        if location not in self.LOCATIONS:
            return []

        db_items = await self._get_db_menu_items(location)
        return self._build_tree(db_items)

    async def get_all_menus(self) -> dict[str, list[MenuItem]]:
        """Get all menus for all locations."""
        return {location: await self.get_menu(location) for location in self.LOCATIONS}

    async def _get_db_menu_items(self, location: str) -> list[dict[str, Any]]:
        """Get menu items from database for a location."""
        # Query entities with location filter
        query = select(Entity).where(
            and_(
                Entity.type == "menu_item",
                Entity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        entities = list(result.scalars().all())

        if not entities:
            return []

        # Filter by location and build item dicts
        items = []
        for entity in entities:
            item_data = self.entity_svc.serialize(entity)

            # Check location matches
            if item_data.get("location") != location:
                continue

            # Only include active items
            if not item_data.get("is_active", True):
                continue

            # Get parent relation
            parent_relations = await self.relation_svc.get_relations(
                entity.id, "menu_item_parent", direction="from"
            )
            parent_id = parent_relations[0].to_entity_id if parent_relations else None

            # Resolve URL if link_type is not custom
            url = await self._resolve_url(item_data)

            items.append(
                {
                    "id": entity.id,
                    "label": item_data.get("label", ""),
                    "url": url,
                    "target": item_data.get("target", "_self"),
                    "icon": item_data.get("icon", ""),
                    "is_active": item_data.get("is_active", True),
                    "sort_order": item_data.get("sort_order", 0),
                    "parent_id": parent_id,
                }
            )

        return items

    async def _resolve_url(self, item_data: dict[str, Any]) -> str:
        """Resolve URL based on link type."""
        link_type = item_data.get("link_type", "custom")
        url = item_data.get("url", "#")

        if link_type == "custom":
            return url or "#"

        # Get linked entity if specified
        linked_id = item_data.get("linked_entity_id")

        # If linked_entity_id is set, resolve to individual page
        if linked_id:
            entity = await self.entity_svc.get(linked_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                slug = entity_data.get("slug", "")
                if slug:
                    return self._get_url_for_type(link_type, slug)

        # No linked_entity_id: return listing page URL
        return self._get_listing_url(link_type)

    def _get_url_for_type(self, link_type: str, slug: str) -> str:
        """Get individual page URL for a content type."""
        # Fixed routes
        fixed_routes = {
            "page": f"/page/{slug}",
            "category": f"/category/{slug}",
            "channel": f"/channel/{slug}",
            "series": f"/series/{slug}",
            "form": f"/forms/{slug}",
        }

        if link_type in fixed_routes:
            return fixed_routes[link_type]

        # Dynamic routes based on path_prefix
        ct = field_service.get_content_type(link_type)
        if ct and ct.path_prefix:
            prefix = ct.path_prefix.strip("/")
            return f"/{prefix}/{slug}"

        return f"/{link_type}/{slug}"

    def _get_listing_url(self, link_type: str) -> str:
        """Get listing page URL for a content type."""
        # Fixed listing routes
        fixed_listings = {
            "page": "/",  # No listing for pages
            "category": "/",  # No listing for categories
            "channel": "/",  # Channels don't have a unified listing
            "series": "/",  # Series don't have a unified listing
            "form": "/forms",
            "post": "/post",
            "news": "/news",
            "tag": "/tags",
        }

        if link_type in fixed_listings:
            return fixed_listings[link_type]

        # Dynamic routes based on path_prefix
        ct = field_service.get_content_type(link_type)
        if ct and ct.path_prefix:
            prefix = ct.path_prefix.strip("/")
            return f"/{prefix}"

        return f"/{link_type}s"

    def _build_tree(self, items: list[dict[str, Any]]) -> list[MenuItem]:
        """Build hierarchical tree from flat list."""
        # Sort by sort_order
        items = sorted(items, key=lambda x: x.get("sort_order", 0))

        # Create MenuItem objects
        item_map: dict[str, MenuItem] = {}
        for item in items:
            item_map[item["id"]] = MenuItem(
                id=item["id"],
                label=item["label"],
                url=item["url"],
                target=item.get("target", "_self"),
                icon=item.get("icon", ""),
                is_active=item.get("is_active", True),
                sort_order=item.get("sort_order", 0),
            )

        # Build tree
        root_items: list[MenuItem] = []
        for item in items:
            menu_item = item_map[item["id"]]
            parent_id = item.get("parent_id")

            if parent_id and parent_id in item_map:
                item_map[parent_id].children.append(menu_item)
            else:
                root_items.append(menu_item)

        # Sort children by sort_order
        for item in item_map.values():
            item.children.sort(key=lambda x: x.sort_order)

        return root_items

    def _get_yaml_menu(self, location: str) -> list[MenuItem]:
        """Get menu from YAML config."""
        menus_config = getattr(settings, "menus", None)
        if not menus_config:
            return []

        items_config: list[MenuItemConfig] = getattr(menus_config, location, [])
        return [self._config_to_menu_item(c, i) for i, c in enumerate(items_config)]

    def _config_to_menu_item(
        self,
        config: MenuItemConfig,
        index: int,
        parent_id: str = None,
    ) -> MenuItem:
        """Convert MenuItemConfig to MenuItem."""
        item_id = f"yaml_{parent_id}_{index}" if parent_id else f"yaml_{index}"
        return MenuItem(
            id=item_id,
            label=config.label,
            url=config.url,
            target=config.target,
            icon=config.icon,
            sort_order=index,
            children=[
                self._config_to_menu_item(c, i, item_id) for i, c in enumerate(config.children)
            ],
        )

    async def has_db_menu(self, location: str) -> bool:
        """Check if DB has menu items for this location."""
        items = await self._get_db_menu_items(location)
        return len(items) > 0

    async def create_menu_item(
        self,
        location: str,
        label: str,
        url: str = "#",
        target: str = "_self",
        icon: str = "",
        link_type: str = "custom",
        linked_entity_id: str = None,
        parent_id: str = None,
        sort_order: int = 0,
        user_id: str = None,
    ) -> Entity:
        """Create a new menu item."""
        data = {
            "label": label,
            "url": url,
            "target": target,
            "location": location,
            "link_type": link_type,
            "linked_entity_id": linked_entity_id or "",
            "icon": icon,
            "sort_order": sort_order,
            "is_active": True,
        }

        entity = await self.entity_svc.create("menu_item", data, user_id)

        # Set parent relation if specified
        if parent_id:
            await self.relation_svc.attach(entity.id, parent_id, "menu_item_parent")

        return entity

    async def update_menu_item(
        self,
        menu_item_id: str,
        data: dict[str, Any],
        parent_id: str = None,
        user_id: str = None,
    ) -> Entity | None:
        """Update a menu item."""
        entity = await self.entity_svc.update(menu_item_id, data, user_id, create_revision=False)

        if not entity:
            return None

        # Update parent relation
        if parent_id is not None:
            # Clear existing parent relations
            current_parents = await self.relation_svc.get_relations(
                menu_item_id, "menu_item_parent", direction="from"
            )
            for rel in current_parents:
                await self.relation_svc.detach(menu_item_id, rel.to_entity_id, "menu_item_parent")

            # Set new parent if specified
            if parent_id:
                await self.relation_svc.attach(menu_item_id, parent_id, "menu_item_parent")

        return entity

    async def delete_menu_item(self, menu_item_id: str, user_id: str = None) -> bool:
        """Delete a menu item (soft delete)."""
        return await self.entity_svc.delete(menu_item_id, user_id)

    async def reorder_menu_items(
        self,
        location: str,
        item_orders: list[dict[str, Any]],
        user_id: str = None,
    ) -> bool:
        """
        Reorder menu items.

        item_orders: [{"id": "xxx", "sort_order": 0, "parent_id": null}, ...]
        """
        for order in item_orders:
            item_id = order["id"]
            sort_order = order.get("sort_order", 0)
            parent_id = order.get("parent_id")

            await self.update_menu_item(
                item_id,
                {"sort_order": sort_order},
                parent_id=parent_id,
                user_id=user_id,
            )

        return True

    async def get_flat_menu_items(self, location: str) -> list[dict[str, Any]]:
        """Get flat list of menu items for admin editing."""
        items = await self._get_db_menu_items(location)
        return items

    async def import_from_yaml(self, location: str, user_id: str = None) -> int:
        """Import YAML config items to database."""
        yaml_items = self._get_yaml_menu(location)
        if not yaml_items:
            return 0

        count = 0
        for item in yaml_items:
            await self._import_menu_item(item, location, None, user_id)
            count += 1
            count += len(item.children)

        return count

    async def _import_menu_item(
        self,
        item: MenuItem,
        location: str,
        parent_id: str,
        user_id: str,
    ) -> Entity:
        """Recursively import a menu item and its children."""
        entity = await self.create_menu_item(
            location=location,
            label=item.label,
            url=item.url,
            target=item.target,
            icon=item.icon,
            parent_id=parent_id,
            sort_order=item.sort_order,
            user_id=user_id,
        )

        for child in item.children:
            await self._import_menu_item(child, location, entity.id, user_id)

        return entity
