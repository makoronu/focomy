"""Routing Service - Path prefix collision detection and custom routing.

Handles:
- Detection of path_prefix collisions
- Custom routing patterns (hierarchical, date-based, etc.)
- URL generation
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RoutingPattern = Literal[
    "simple",  # /{type}/{slug}
    "hierarchical",  # /{parent}/{child}/{slug}
    "date-based",  # /{year}/{month}/{slug}
    "date-slug",  # /{year}/{month}/{day}/{slug}
    "category",  # /{category}/{slug}
    "custom",  # User-defined pattern
]


@dataclass
class PathCollision:
    """Path prefix collision info."""

    path: str
    types: list[str]
    severity: str  # "error" or "warning"
    message: str


@dataclass
class RouteMatch:
    """Route matching result."""

    matched: bool
    content_type: str
    entity_id: str | None
    params: dict


@dataclass
class RouteConfig:
    """Routing configuration for a content type."""

    content_type: str
    pattern: RoutingPattern
    prefix: str
    custom_pattern: str | None = None
    params: dict = None


class RoutingService:
    """
    Service for URL routing and path collision detection.

    Usage:
        routing = RoutingService()

        # Check for collisions
        collisions = routing.detect_collisions(content_types)

        # Generate URL
        url = routing.generate_url("post", entity, config)

        # Parse URL
        match = routing.match_url("/blog/2024/01/my-post")
    """

    def __init__(self):
        self._routes: dict[str, RouteConfig] = {}
        self._patterns: dict[str, re.Pattern] = {}

    def detect_collisions(
        self,
        content_types: dict,
    ) -> list[PathCollision]:
        """
        Detect path_prefix collisions between content types.

        Args:
            content_types: Dict of content type definitions

        Returns:
            List of collision info
        """
        collisions = []
        prefixes: dict[str, list[str]] = {}

        # Collect all prefixes
        for type_name, config in content_types.items():
            prefix = config.get("path_prefix", f"/{type_name}")
            prefix = self._normalize_path(prefix)

            if prefix not in prefixes:
                prefixes[prefix] = []
            prefixes[prefix].append(type_name)

        # Check for exact collisions
        for prefix, types in prefixes.items():
            if len(types) > 1:
                collisions.append(
                    PathCollision(
                        path=prefix,
                        types=types,
                        severity="error",
                        message=f"Multiple types share the same path_prefix: {', '.join(types)}",
                    )
                )

        # Check for overlapping prefixes
        sorted_prefixes = sorted(prefixes.keys())
        for i, prefix1 in enumerate(sorted_prefixes):
            for prefix2 in sorted_prefixes[i + 1 :]:
                if self._is_overlapping(prefix1, prefix2):
                    collisions.append(
                        PathCollision(
                            path=f"{prefix1} <-> {prefix2}",
                            types=prefixes[prefix1] + prefixes[prefix2],
                            severity="warning",
                            message="Overlapping path prefixes may cause routing ambiguity",
                        )
                    )

        return collisions

    def _normalize_path(self, path: str) -> str:
        """Normalize path for comparison."""
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        return path.rstrip("/")

    def _is_overlapping(self, prefix1: str, prefix2: str) -> bool:
        """Check if two prefixes overlap."""
        # One is a prefix of the other
        if prefix1.startswith(prefix2) or prefix2.startswith(prefix1):
            return True
        return False

    def register_route(self, config: RouteConfig) -> None:
        """Register a route configuration."""
        self._routes[config.content_type] = config

        # Compile pattern for matching
        pattern = self._build_regex_pattern(config)
        self._patterns[config.content_type] = re.compile(pattern)

    def _build_regex_pattern(self, config: RouteConfig) -> str:
        """Build regex pattern from route config."""
        prefix = self._normalize_path(config.prefix)

        if config.pattern == "simple":
            return f"^{re.escape(prefix)}/(?P<slug>[^/]+)/?$"

        elif config.pattern == "date-based":
            return f"^{re.escape(prefix)}/(?P<year>\\d{{4}})/(?P<month>\\d{{2}})/(?P<slug>[^/]+)/?$"

        elif config.pattern == "date-slug":
            return f"^{re.escape(prefix)}/(?P<year>\\d{{4}})/(?P<month>\\d{{2}})/(?P<day>\\d{{2}})/(?P<slug>[^/]+)/?$"

        elif config.pattern == "hierarchical":
            return f"^{re.escape(prefix)}/(?P<path>.+)/(?P<slug>[^/]+)/?$"

        elif config.pattern == "category":
            return f"^{re.escape(prefix)}/(?P<category>[^/]+)/(?P<slug>[^/]+)/?$"

        elif config.pattern == "custom" and config.custom_pattern:
            return self._compile_custom_pattern(config.custom_pattern)

        return f"^{re.escape(prefix)}/(?P<slug>[^/]+)/?$"

    def _compile_custom_pattern(self, pattern: str) -> str:
        """Convert custom pattern to regex."""
        # Replace {param} with named capture groups
        regex = pattern
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", regex)
        regex = re.sub(r"\{(\w+):int\}", r"(?P<\1>\\d+)", regex)
        regex = re.sub(r"\{(\w+):slug\}", r"(?P<\1>[a-z0-9-]+)", regex)
        return f"^{regex}/?$"

    def generate_url(
        self,
        content_type: str,
        entity_data: dict,
        config: RouteConfig = None,
    ) -> str:
        """
        Generate URL for an entity.

        Args:
            content_type: Content type name
            entity_data: Entity values (slug, created_at, category, etc.)
            config: Route config (uses registered if not provided)

        Returns:
            URL path
        """
        config = config or self._routes.get(content_type)
        if not config:
            # Default simple pattern
            slug = entity_data.get("slug", entity_data.get("id", ""))
            return f"/{content_type}/{slug}"

        prefix = self._normalize_path(config.prefix)
        slug = entity_data.get("slug", "")

        if config.pattern == "simple":
            return f"{prefix}/{slug}"

        elif config.pattern == "date-based":
            created_at = entity_data.get("created_at") or datetime.now()
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            return f"{prefix}/{created_at.year}/{created_at.month:02d}/{slug}"

        elif config.pattern == "date-slug":
            created_at = entity_data.get("created_at") or datetime.now()
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            return f"{prefix}/{created_at.year}/{created_at.month:02d}/{created_at.day:02d}/{slug}"

        elif config.pattern == "hierarchical":
            parent_path = entity_data.get("parent_path", "")
            if parent_path:
                return f"{prefix}/{parent_path}/{slug}"
            return f"{prefix}/{slug}"

        elif config.pattern == "category":
            category = entity_data.get("category_slug") or entity_data.get(
                "category", "uncategorized"
            )
            return f"{prefix}/{category}/{slug}"

        elif config.pattern == "custom" and config.custom_pattern:
            return self._render_custom_url(config.custom_pattern, entity_data)

        return f"{prefix}/{slug}"

    def _render_custom_url(self, pattern: str, data: dict) -> str:
        """Render custom URL pattern with data."""
        url = pattern

        # Replace {param} with values
        for key, value in data.items():
            url = url.replace(f"{{{key}}}", str(value))

        # Handle date fields
        if "{year}" in url or "{month}" in url or "{day}" in url:
            created_at = data.get("created_at") or datetime.now()
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            url = url.replace("{year}", str(created_at.year))
            url = url.replace("{month}", f"{created_at.month:02d}")
            url = url.replace("{day}", f"{created_at.day:02d}")

        return url

    def match_url(self, url: str) -> RouteMatch | None:
        """
        Match URL to a registered route.

        Args:
            url: URL path to match

        Returns:
            RouteMatch if matched, None otherwise
        """
        url = self._normalize_path(url)

        for content_type, pattern in self._patterns.items():
            match = pattern.match(url)
            if match:
                return RouteMatch(
                    matched=True,
                    content_type=content_type,
                    entity_id=None,  # Would need DB lookup
                    params=match.groupdict(),
                )

        return None

    def get_route_config(self, content_type: str) -> RouteConfig | None:
        """Get route configuration for a content type."""
        return self._routes.get(content_type)

    def validate_route_config(self, config: RouteConfig) -> list[str]:
        """Validate a route configuration."""
        errors = []

        if not config.content_type:
            errors.append("content_type is required")

        if not config.prefix:
            errors.append("prefix is required")

        if config.pattern == "custom" and not config.custom_pattern:
            errors.append("custom_pattern is required for custom pattern type")

        # Check for invalid characters
        if config.prefix:
            if not config.prefix.startswith("/"):
                errors.append("prefix must start with /")
            if "//" in config.prefix:
                errors.append("prefix cannot contain //")

        return errors


class URLBuilder:
    """
    Helper for building URLs with the routing service.

    Usage:
        builder = URLBuilder(routing_service)
        url = builder.for_entity("post", entity).absolute()
    """

    def __init__(self, routing: RoutingService, base_url: str = ""):
        self.routing = routing
        self.base_url = base_url.rstrip("/")
        self._path = ""

    def for_entity(self, content_type: str, entity_data: dict) -> "URLBuilder":
        """Generate URL for an entity."""
        self._path = self.routing.generate_url(content_type, entity_data)
        return self

    def for_path(self, path: str) -> "URLBuilder":
        """Set a specific path."""
        self._path = path
        return self

    def with_query(self, **params) -> "URLBuilder":
        """Add query parameters."""
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            self._path = f"{self._path}?{query}"
        return self

    def relative(self) -> str:
        """Get relative URL."""
        return self._path

    def absolute(self) -> str:
        """Get absolute URL."""
        return f"{self.base_url}{self._path}"


def get_routing_service() -> RoutingService:
    return RoutingService()
