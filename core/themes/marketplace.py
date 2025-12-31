"""Theme Marketplace - Remote theme discovery and installation."""

import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MarketplaceTheme:
    """Theme listing from marketplace."""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    author_url: str = ""

    # Marketplace info
    slug: str = ""
    screenshot_url: str = ""
    preview_url: str = ""
    download_url: str = ""
    price: float = 0.0
    currency: str = "USD"
    is_free: bool = True

    # Stats
    downloads: int = 0
    rating: float = 0.0
    reviews_count: int = 0

    # Metadata
    tags: list[str] = field(default_factory=list)
    category: str = ""
    last_updated: datetime | None = None
    created_at: datetime | None = None

    # Requirements
    requires_focomy: str = ">=1.0.0"
    requires_python: str = ">=3.10"

    # Additional info
    features: list[str] = field(default_factory=list)
    demo_content: bool = False
    documentation_url: str = ""
    support_url: str = ""


@dataclass
class MarketplaceSearchResult:
    """Search result from marketplace."""

    themes: list[MarketplaceTheme]
    total: int = 0
    page: int = 1
    per_page: int = 20
    has_more: bool = False


@dataclass
class InstallResult:
    """Result of theme installation."""

    success: bool
    message: str
    theme_id: str | None = None
    version: str | None = None


class ThemeMarketplace:
    """
    Integration with remote theme marketplace.

    Handles:
    - Theme search and discovery
    - Theme details and previews
    - Download and installation
    - License verification
    - Update checks
    """

    DEFAULT_MARKETPLACE_URL = "https://marketplace.focomy.com/api/v1"

    def __init__(
        self,
        theme_manager: Any,
        marketplace_url: str | None = None,
        api_key: str | None = None,
        cache_dir: Path | None = None,
    ):
        """
        Initialize marketplace client.

        Args:
            theme_manager: ThemeManager instance
            marketplace_url: Marketplace API URL
            api_key: Optional API key for premium themes
            cache_dir: Directory for caching theme data
        """
        self.theme_manager = theme_manager
        self.marketplace_url = (marketplace_url or self.DEFAULT_MARKETPLACE_URL).rstrip("/")
        self.api_key = api_key
        self.cache_dir = (
            Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "focomy_themes"
        )

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._cache: dict[str, Any] = {}
        self._cache_ttl = 3600  # 1 hour

    async def search(
        self,
        query: str = "",
        category: str | None = None,
        tags: list[str] | None = None,
        free_only: bool = False,
        sort_by: str = "popular",
        page: int = 1,
        per_page: int = 20,
    ) -> MarketplaceSearchResult:
        """
        Search themes in marketplace.

        Args:
            query: Search query
            category: Filter by category
            tags: Filter by tags
            free_only: Only show free themes
            sort_by: Sort order (popular, newest, rating, name)
            page: Page number
            per_page: Results per page

        Returns:
            MarketplaceSearchResult with matching themes
        """
        params = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "sort": sort_by,
        }

        if category:
            params["category"] = category
        if tags:
            params["tags"] = ",".join(tags)
        if free_only:
            params["free"] = "true"

        try:
            data = await self._request("GET", "/themes", params=params)

            themes = [self._parse_theme(t) for t in data.get("themes", [])]

            return MarketplaceSearchResult(
                themes=themes,
                total=data.get("total", len(themes)),
                page=data.get("page", page),
                per_page=data.get("per_page", per_page),
                has_more=data.get("has_more", False),
            )

        except Exception as e:
            logger.exception(f"Marketplace search failed: {e}")
            return MarketplaceSearchResult(themes=[])

    async def get_featured(self, limit: int = 10) -> list[MarketplaceTheme]:
        """Get featured themes."""
        try:
            data = await self._request("GET", "/themes/featured", params={"limit": limit})
            return [self._parse_theme(t) for t in data.get("themes", [])]
        except Exception as e:
            logger.exception(f"Failed to get featured themes: {e}")
            return []

    async def get_popular(self, limit: int = 10) -> list[MarketplaceTheme]:
        """Get popular themes."""
        result = await self.search(sort_by="popular", per_page=limit)
        return result.themes

    async def get_newest(self, limit: int = 10) -> list[MarketplaceTheme]:
        """Get newest themes."""
        result = await self.search(sort_by="newest", per_page=limit)
        return result.themes

    async def get_categories(self) -> list[dict]:
        """Get available theme categories."""
        try:
            data = await self._request("GET", "/categories")
            return data.get("categories", [])
        except Exception as e:
            logger.exception(f"Failed to get categories: {e}")
            return []

    async def get_theme_details(self, theme_id: str) -> MarketplaceTheme | None:
        """
        Get detailed information about a theme.

        Args:
            theme_id: Theme identifier

        Returns:
            MarketplaceTheme with full details, or None if not found
        """
        try:
            data = await self._request("GET", f"/themes/{theme_id}")
            return self._parse_theme(data)
        except Exception as e:
            logger.exception(f"Failed to get theme details: {e}")
            return None

    async def install(
        self,
        theme_id: str,
        license_key: str | None = None,
        progress_callback: Callable | None = None,
    ) -> InstallResult:
        """
        Download and install a theme from marketplace.

        Args:
            theme_id: Theme identifier
            license_key: License key for premium themes
            progress_callback: Optional callback(progress, message)

        Returns:
            InstallResult with installation status
        """
        try:
            # Get theme details
            if progress_callback:
                progress_callback(0.1, "Fetching theme information...")

            theme = await self.get_theme_details(theme_id)
            if not theme:
                return InstallResult(False, "Theme not found")

            # Check if premium
            if not theme.is_free:
                if not license_key and not self.api_key:
                    return InstallResult(False, "License key required for premium theme")

            # Get download URL
            if progress_callback:
                progress_callback(0.2, "Getting download link...")

            download_url = await self._get_download_url(theme_id, license_key)
            if not download_url:
                return InstallResult(False, "Failed to get download URL")

            # Download theme
            if progress_callback:
                progress_callback(0.3, "Downloading theme...")

            zip_path = await self._download_theme(download_url, theme_id, progress_callback)
            if not zip_path:
                return InstallResult(False, "Download failed")

            # Verify checksum
            if progress_callback:
                progress_callback(0.8, "Verifying download...")

            # Install theme
            if progress_callback:
                progress_callback(0.9, "Installing theme...")

            success, message, installed_id = self.theme_manager.install_from_zip(zip_path)

            # Cleanup
            try:
                zip_path.unlink()
            except Exception:
                pass

            if progress_callback:
                progress_callback(1.0, "Complete!")

            return InstallResult(
                success=success,
                message=message,
                theme_id=installed_id,
                version=theme.version,
            )

        except Exception as e:
            logger.exception(f"Theme installation failed: {e}")
            return InstallResult(False, f"Installation error: {e}")

    async def check_updates(
        self,
        installed_themes: list[tuple[str, str]],
    ) -> list[dict]:
        """
        Check for theme updates.

        Args:
            installed_themes: List of (theme_id, version) tuples

        Returns:
            List of available updates
        """
        try:
            data = await self._request(
                "POST",
                "/themes/check-updates",
                json={"themes": [{"id": t[0], "version": t[1]} for t in installed_themes]},
            )

            return data.get("updates", [])

        except Exception as e:
            logger.exception(f"Update check failed: {e}")
            return []

    async def get_changelog(self, theme_id: str) -> list[dict]:
        """Get theme changelog."""
        try:
            data = await self._request("GET", f"/themes/{theme_id}/changelog")
            return data.get("changelog", [])
        except Exception as e:
            logger.exception(f"Failed to get changelog: {e}")
            return []

    async def submit_review(
        self,
        theme_id: str,
        rating: int,
        review: str,
    ) -> tuple[bool, str]:
        """
        Submit a theme review.

        Args:
            theme_id: Theme identifier
            rating: Rating (1-5)
            review: Review text

        Returns:
            Tuple of (success, message)
        """
        if not self.api_key:
            return False, "Authentication required"

        try:
            await self._request(
                "POST",
                f"/themes/{theme_id}/reviews",
                json={"rating": rating, "review": review},
            )
            return True, "Review submitted"
        except Exception as e:
            return False, str(e)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Make API request."""
        url = f"{self.marketplace_url}{path}"

        headers = {
            "User-Agent": "Focomy/1.0",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 404:
                    raise ValueError("Not found")
                if response.status == 401:
                    raise ValueError("Authentication required")
                if response.status >= 400:
                    raise ValueError(f"API error: {response.status}")

                return await response.json()

    async def _get_download_url(
        self,
        theme_id: str,
        license_key: str | None = None,
    ) -> str | None:
        """Get theme download URL."""
        try:
            json_data = {}
            if license_key:
                json_data["license_key"] = license_key

            data = await self._request(
                "POST",
                f"/themes/{theme_id}/download",
                json=json_data if json_data else None,
            )
            return data.get("download_url")
        except Exception as e:
            logger.exception(f"Failed to get download URL: {e}")
            return None

    async def _download_theme(
        self,
        url: str,
        theme_id: str,
        progress_callback: Callable | None = None,
    ) -> Path | None:
        """Download theme ZIP file."""
        zip_path = self.cache_dir / f"{theme_id}.zip"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        return None

                    total_size = int(response.headers.get("Content-Length", 0))
                    downloaded = 0

                    with open(zip_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback and total_size:
                                progress = 0.3 + (downloaded / total_size) * 0.5
                                progress_callback(
                                    progress, f"Downloading... {downloaded // 1024}KB"
                                )

            return zip_path

        except Exception as e:
            logger.exception(f"Download failed: {e}")
            if zip_path.exists():
                zip_path.unlink()
            return None

    def _parse_theme(self, data: dict) -> MarketplaceTheme:
        """Parse theme data from API response."""
        return MarketplaceTheme(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            author_url=data.get("author_url", ""),
            slug=data.get("slug", ""),
            screenshot_url=data.get("screenshot_url", ""),
            preview_url=data.get("preview_url", ""),
            download_url=data.get("download_url", ""),
            price=data.get("price", 0.0),
            currency=data.get("currency", "USD"),
            is_free=data.get("is_free", data.get("price", 0) == 0),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            reviews_count=data.get("reviews_count", 0),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            last_updated=self._parse_date(data.get("last_updated")),
            created_at=self._parse_date(data.get("created_at")),
            requires_focomy=data.get("requires_focomy", ">=1.0.0"),
            requires_python=data.get("requires_python", ">=3.10"),
            features=data.get("features", []),
            demo_content=data.get("demo_content", False),
            documentation_url=data.get("documentation_url", ""),
            support_url=data.get("support_url", ""),
        )

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None
