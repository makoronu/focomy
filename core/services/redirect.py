"""RedirectService - URL redirect management."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


class RedirectService:
    """
    Redirect management service.

    Handles 301/302 redirects with support for:
    - Exact match
    - Prefix match
    - Regex match
    - Query string preservation
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self._cache: dict = {}
        self._cache_loaded = False

    async def get_all_active(self) -> list[dict]:
        """Get all active redirects."""
        entities = await self.entity_svc.find(
            "redirect",
            limit=1000,
            filters={"is_active": True},
        )

        redirects = []
        for entity in entities:
            data = self.entity_svc.serialize(entity)
            if data.get("is_active", True):
                redirects.append(
                    {
                        "id": entity.id,
                        "from_path": data.get("from_path", ""),
                        "to_path": data.get("to_path", ""),
                        "status_code": int(data.get("status_code", 301)),
                        "match_type": data.get("match_type", "exact"),
                        "preserve_query": data.get("preserve_query", True),
                    }
                )

        return redirects

    async def find_redirect(self, path: str, query_string: str = "") -> dict | None:
        """
        Find a matching redirect for the given path.

        Args:
            path: The request path (e.g., "/old-page")
            query_string: The query string (e.g., "foo=bar")

        Returns:
            Dict with redirect info or None if no match
        """
        # Load cache if needed
        if not self._cache_loaded:
            await self._load_cache()

        # Check exact matches first (fastest)
        if path in self._cache.get("exact", {}):
            redirect = self._cache["exact"][path]
            return self._build_redirect_response(redirect, path, query_string)

        # Check prefix matches
        for prefix, redirect in self._cache.get("prefix", {}).items():
            if path.startswith(prefix):
                # Replace prefix in target path
                suffix = path[len(prefix) :]
                return self._build_redirect_response(redirect, path, query_string, suffix)

        # Check regex matches (slowest)
        for pattern, redirect in self._cache.get("regex", []):
            match = pattern.match(path)
            if match:
                # Support group substitution in to_path
                to_path = redirect["to_path"]
                for i, group in enumerate(match.groups(), 1):
                    to_path = to_path.replace(f"${i}", group or "")
                redirect = {**redirect, "to_path": to_path}
                return self._build_redirect_response(redirect, path, query_string)

        return None

    def _build_redirect_response(
        self,
        redirect: dict,
        original_path: str,
        query_string: str,
        suffix: str = "",
    ) -> dict:
        """Build the redirect response dict."""
        to_path = redirect["to_path"]

        # For prefix matches, append the suffix
        if suffix and redirect.get("match_type") == "prefix":
            to_path = to_path.rstrip("/") + suffix

        # Preserve query string if configured
        if redirect.get("preserve_query", True) and query_string:
            separator = "&" if "?" in to_path else "?"
            to_path = f"{to_path}{separator}{query_string}"

        return {
            "to_path": to_path,
            "status_code": redirect.get("status_code", 301),
        }

    async def _load_cache(self):
        """Load all redirects into memory cache."""
        redirects = await self.get_all_active()

        self._cache = {
            "exact": {},
            "prefix": {},
            "regex": [],
        }

        for r in redirects:
            match_type = r.get("match_type", "exact")
            from_path = r.get("from_path", "")

            if match_type == "exact":
                self._cache["exact"][from_path] = r
            elif match_type == "prefix":
                self._cache["prefix"][from_path] = r
            elif match_type == "regex":
                try:
                    pattern = re.compile(from_path)
                    self._cache["regex"].append((pattern, r))
                except re.error:
                    pass  # Skip invalid regex

        self._cache_loaded = True

    def invalidate_cache(self):
        """Invalidate the redirect cache."""
        self._cache = {}
        self._cache_loaded = False

    async def create_redirect(
        self,
        from_path: str,
        to_path: str,
        status_code: int = 301,
        match_type: str = "exact",
        preserve_query: bool = True,
        notes: str = "",
        user_id: str | None = None,
    ) -> dict:
        """Create a new redirect rule."""
        # Validate paths
        if not from_path or not to_path:
            raise ValueError("from_path and to_path are required")

        # Normalize from_path
        if not from_path.startswith("/"):
            from_path = "/" + from_path

        # Check for duplicate
        existing = await self.entity_svc.find(
            "redirect",
            limit=1,
            filters={"from_path": from_path},
        )
        if existing:
            raise ValueError(f"Redirect from '{from_path}' already exists")

        entity = await self.entity_svc.create(
            "redirect",
            {
                "from_path": from_path,
                "to_path": to_path,
                "status_code": str(status_code),
                "match_type": match_type,
                "preserve_query": preserve_query,
                "is_active": True,
                "notes": notes,
            },
            user_id=user_id,
        )

        self.invalidate_cache()
        return self.entity_svc.serialize(entity)

    async def update_redirect(
        self,
        redirect_id: str,
        data: dict,
        user_id: str | None = None,
    ) -> dict | None:
        """Update a redirect rule."""
        entity = await self.entity_svc.update(redirect_id, data, user_id=user_id)
        if entity:
            self.invalidate_cache()
            return self.entity_svc.serialize(entity)
        return None

    async def delete_redirect(
        self,
        redirect_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Delete a redirect rule."""
        result = await self.entity_svc.delete(redirect_id, user_id=user_id)
        if result:
            self.invalidate_cache()
        return result

    async def get_all_redirects(self, include_inactive: bool = False) -> list[dict]:
        """Get all redirects for admin UI."""
        entities = await self.entity_svc.find(
            "redirect",
            limit=1000,
            order_by="-created_at",
        )

        redirects = []
        for entity in entities:
            data = self.entity_svc.serialize(entity)
            if include_inactive or data.get("is_active", True):
                redirects.append(data)

        return redirects

    async def get_redirect(self, redirect_id: str) -> dict | None:
        """Get a single redirect by ID."""
        entity = await self.entity_svc.get(redirect_id)
        if entity and entity.type == "redirect":
            return self.entity_svc.serialize(entity)
        return None

    async def toggle_active(
        self,
        redirect_id: str,
        user_id: str | None = None,
    ) -> dict | None:
        """Toggle redirect active status."""
        entity = await self.entity_svc.get(redirect_id)
        if not entity or entity.type != "redirect":
            return None

        data = self.entity_svc.serialize(entity)
        new_status = not data.get("is_active", True)

        return await self.update_redirect(
            redirect_id,
            {"is_active": new_status},
            user_id=user_id,
        )

    async def import_redirects(
        self,
        redirects: list[dict],
        user_id: str | None = None,
    ) -> int:
        """
        Bulk import redirects.

        Args:
            redirects: List of redirect dicts with from_path, to_path, etc.
            user_id: User performing the import

        Returns:
            Number of redirects imported
        """
        count = 0
        for r in redirects:
            try:
                await self.create_redirect(
                    from_path=r.get("from_path", ""),
                    to_path=r.get("to_path", ""),
                    status_code=int(r.get("status_code", 301)),
                    match_type=r.get("match_type", "exact"),
                    preserve_query=r.get("preserve_query", True),
                    notes=r.get("notes", ""),
                    user_id=user_id,
                )
                count += 1
            except ValueError:
                pass  # Skip duplicates or invalid entries

        return count

    async def test_redirect(self, path: str) -> dict | None:
        """
        Test a path against redirect rules.

        Returns the redirect result or None if no match.
        Useful for admin UI testing.
        """
        return await self.find_redirect(path)
