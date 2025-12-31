"""WordPress REST API Client - Fetch data directly from WordPress sites."""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...utils import utcnow
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from .wxr_parser import (
    WXRAuthor,
    WXRComment,
    WXRData,
    WXRMenuItem,
    WXRPost,
    WXRSiteInfo,
    WXRTerm,
)

logger = logging.getLogger(__name__)


@dataclass
class RESTClientConfig:
    """Configuration for WordPress REST API client."""

    site_url: str
    username: str = ""
    password: str = ""  # Application Password
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    per_page: int = 100
    rate_limit_delay: float = 0.1  # Delay between requests


@dataclass
class ConnectionTestResult:
    """Result of connection test."""

    success: bool = False
    message: str = ""
    wp_version: str = ""
    site_name: str = ""
    authenticated: bool = False
    available_endpoints: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class WordPressRESTClient:
    """
    WordPress REST API client.

    Fetches all site data via REST API instead of WXR export.
    Supports authentication via Application Passwords.
    """

    def __init__(self, config: RESTClientConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._api_base = self._normalize_api_url(config.site_url)

    def _normalize_api_url(self, url: str) -> str:
        """Normalize site URL to API base URL."""
        url = url.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return f"{url}/wp-json/wp/v2"

    def _get_auth_header(self) -> dict[str, str]:
        """Get authentication header."""
        if not self.config.username or not self.config.password:
            return {}

        credentials = f"{self.config.username}:{self.config.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    async def __aenter__(self):
        """Enter async context."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            headers={
                "User-Agent": "Focomy-Importer/1.0",
                **self._get_auth_header(),
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._session:
            await self._session.close()
            self._session = None

    async def test_connection(self) -> ConnectionTestResult:
        """
        Test connection to WordPress site.

        Returns:
            ConnectionTestResult with connection status and site info
        """
        result = ConnectionTestResult()

        try:
            # Test root endpoint
            root_url = self.config.site_url.rstrip("/") + "/wp-json"
            async with self._session.get(root_url) as response:
                if response.status == 200:
                    data = await response.json()
                    result.site_name = data.get("name", "")
                    result.wp_version = data.get("namespaces", [])
                    result.available_endpoints = list(data.get("routes", {}).keys())
                    result.success = True
                    result.message = "Connection successful"
                elif response.status == 401:
                    result.message = "Authentication required"
                    result.errors.append("Invalid credentials or authentication not configured")
                elif response.status == 404:
                    result.message = "REST API not found"
                    result.errors.append("WordPress REST API may be disabled")
                else:
                    result.message = f"HTTP {response.status}"
                    result.errors.append(await response.text())

            # Test authentication
            if result.success and self.config.username:
                users_url = f"{self._api_base}/users/me"
                async with self._session.get(users_url) as response:
                    if response.status == 200:
                        result.authenticated = True
                    else:
                        result.authenticated = False
                        result.errors.append("Authentication failed - check Application Password")

        except aiohttp.ClientError as e:
            result.success = False
            result.message = f"Connection error: {str(e)}"
            result.errors.append(str(e))
        except Exception as e:
            result.success = False
            result.message = f"Unexpected error: {str(e)}"
            result.errors.append(str(e))

        return result

    async def _request(
        self,
        endpoint: str,
        params: dict | None = None,
    ) -> tuple[Any, dict]:
        """
        Make API request with retry logic.

        Returns:
            Tuple of (response_data, headers)
        """
        url = f"{self._api_base}/{endpoint}"
        params = params or {}

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        headers = dict(response.headers)
                        await asyncio.sleep(self.config.rate_limit_delay)
                        return data, headers
                    elif response.status == 429:
                        # Rate limited
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    elif response.status in (500, 502, 503, 504):
                        # Server error, retry
                        delay = self.config.retry_delay * (2**attempt)
                        logger.warning(f"Server error {response.status}, retrying in {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")

            except aiohttp.ClientError as e:
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2**attempt)
                    logger.warning(f"Request failed, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    raise

        raise Exception(f"Max retries exceeded for {endpoint}")

    async def _fetch_all_pages(
        self,
        endpoint: str,
        params: dict | None = None,
        progress_callback: callable | None = None,
    ) -> list[dict]:
        """Fetch all pages of a paginated endpoint."""
        params = params or {}
        params["per_page"] = self.config.per_page
        params["page"] = 1

        all_items = []
        total_pages = 1

        while params["page"] <= total_pages:
            data, headers = await self._request(endpoint, params)

            if not isinstance(data, list):
                data = [data]

            all_items.extend(data)

            # Get total pages from headers
            if "X-WP-TotalPages" in headers:
                total_pages = int(headers["X-WP-TotalPages"])

            if progress_callback:
                total = int(headers.get("X-WP-Total", len(all_items)))
                progress_callback(len(all_items), total, endpoint)

            params["page"] += 1

        return all_items

    async def fetch_site_info(self) -> WXRSiteInfo:
        """Fetch site information."""
        root_url = self.config.site_url.rstrip("/") + "/wp-json"
        async with self._session.get(root_url) as response:
            data = await response.json()

            return WXRSiteInfo(
                title=data.get("name", ""),
                link=data.get("url", self.config.site_url),
                description=data.get("description", ""),
                language=data.get("language", "en"),
                base_site_url=data.get("url", self.config.site_url),
                base_blog_url=data.get("url", self.config.site_url),
                wp_version=str(data.get("namespaces", [])),
            )

    async def fetch_authors(
        self,
        progress_callback: callable | None = None,
    ) -> list[WXRAuthor]:
        """Fetch all users/authors."""
        users = await self._fetch_all_pages("users", progress_callback=progress_callback)

        return [
            WXRAuthor(
                id=user["id"],
                login=user.get("slug", ""),
                email=user.get("email", ""),  # Only available if authenticated
                display_name=user.get("name", ""),
                first_name=user.get("first_name", ""),
                last_name=user.get("last_name", ""),
            )
            for user in users
        ]

    async def fetch_categories(
        self,
        progress_callback: callable | None = None,
    ) -> list[WXRTerm]:
        """Fetch all categories."""
        categories = await self._fetch_all_pages("categories", progress_callback=progress_callback)

        return [
            WXRTerm(
                id=cat["id"],
                name=cat.get("name", ""),
                slug=cat.get("slug", ""),
                taxonomy="category",
                description=cat.get("description", ""),
                parent_id=cat.get("parent", 0),
            )
            for cat in categories
        ]

    async def fetch_tags(
        self,
        progress_callback: callable | None = None,
    ) -> list[WXRTerm]:
        """Fetch all tags."""
        tags = await self._fetch_all_pages("tags", progress_callback=progress_callback)

        return [
            WXRTerm(
                id=tag["id"],
                name=tag.get("name", ""),
                slug=tag.get("slug", ""),
                taxonomy="post_tag",
                description=tag.get("description", ""),
                parent_id=0,
            )
            for tag in tags
        ]

    async def fetch_posts(
        self,
        include_drafts: bool = True,
        progress_callback: callable | None = None,
    ) -> list[WXRPost]:
        """Fetch all posts."""
        params = {"status": "any" if include_drafts else "publish"}
        posts = await self._fetch_all_pages("posts", params, progress_callback)

        return [self._convert_post(post, "post") for post in posts]

    async def fetch_pages(
        self,
        include_drafts: bool = True,
        progress_callback: callable | None = None,
    ) -> list[WXRPost]:
        """Fetch all pages."""
        params = {"status": "any" if include_drafts else "publish"}
        pages = await self._fetch_all_pages("pages", params, progress_callback)

        return [self._convert_post(page, "page") for page in pages]

    async def fetch_media(
        self,
        progress_callback: callable | None = None,
    ) -> list[WXRPost]:
        """Fetch all media attachments."""
        media = await self._fetch_all_pages("media", progress_callback=progress_callback)

        return [self._convert_media(item) for item in media]

    async def fetch_comments(
        self,
        progress_callback: callable | None = None,
    ) -> list[WXRComment]:
        """Fetch all comments."""
        comments = await self._fetch_all_pages("comments", progress_callback=progress_callback)

        return [
            WXRComment(
                id=comment["id"],
                post_id=comment.get("post", 0),
                author=comment.get("author_name", ""),
                author_email=comment.get("author_email", ""),
                author_url=comment.get("author_url", ""),
                author_ip=comment.get("author_ip", ""),
                date=self._parse_date(comment.get("date_gmt", "")),
                content=comment.get("content", {}).get("rendered", ""),
                approved="1" if comment.get("status") == "approved" else "0",
                parent_id=comment.get("parent", 0),
                user_id=comment.get("author", 0),
            )
            for comment in comments
        ]

    async def fetch_menus(
        self,
        progress_callback: callable | None = None,
    ) -> dict[str, list[WXRMenuItem]]:
        """
        Fetch navigation menus.

        Note: Requires WP REST API Menus plugin or similar.
        """
        menus = {}

        try:
            # Try standard menu endpoint (requires plugin)
            menu_locations_url = self.config.site_url.rstrip("/") + "/wp-json/menus/v1/locations"
            async with self._session.get(menu_locations_url) as response:
                if response.status == 200:
                    locations = await response.json()

                    for location in locations:
                        menu_url = f"{self.config.site_url.rstrip('/')}/wp-json/menus/v1/menus/{location.get('ID', '')}"
                        async with self._session.get(menu_url) as menu_response:
                            if menu_response.status == 200:
                                menu_data = await menu_response.json()
                                menu_name = menu_data.get("name", "default")
                                menus[menu_name] = [
                                    WXRMenuItem(
                                        id=item.get("ID", 0),
                                        title=item.get("title", ""),
                                        url=item.get("url", ""),
                                        menu_id=menu_data.get("term_id", 0),
                                        parent_id=item.get("menu_item_parent", 0),
                                        order=item.get("menu_order", 0),
                                        object_type=item.get("object", ""),
                                        object_id=item.get("object_id", 0),
                                        target=item.get("target", ""),
                                        classes=item.get("classes", []),
                                    )
                                    for item in menu_data.get("items", [])
                                ]

        except Exception as e:
            logger.warning(f"Could not fetch menus (plugin may not be installed): {e}")

        return menus

    async def fetch_custom_post_types(
        self,
        progress_callback: callable | None = None,
    ) -> dict[str, list[WXRPost]]:
        """Fetch custom post types."""
        custom_posts = {}

        try:
            # Get available post types
            types_url = self.config.site_url.rstrip("/") + "/wp-json/wp/v2/types"
            async with self._session.get(types_url) as response:
                if response.status == 200:
                    types_data = await response.json()

                    # Skip built-in types
                    skip_types = {"post", "page", "attachment", "revision", "nav_menu_item"}

                    for type_slug, type_info in types_data.items():
                        if type_slug in skip_types:
                            continue

                        # Get REST base for this type
                        rest_base = type_info.get("rest_base", type_slug)

                        try:
                            params = {"status": "any"}
                            posts = await self._fetch_all_pages(
                                rest_base, params, progress_callback
                            )
                            custom_posts[type_slug] = [
                                self._convert_post(p, type_slug) for p in posts
                            ]
                        except Exception as e:
                            logger.warning(f"Could not fetch {type_slug}: {e}")

        except Exception as e:
            logger.warning(f"Could not fetch custom post types: {e}")

        return custom_posts

    def _convert_post(self, post: dict, post_type: str) -> WXRPost:
        """Convert REST API post to WXRPost."""
        # Extract categories and tags
        categories = [
            {"slug": str(cat_id), "name": str(cat_id)}
            for cat_id in post.get("categories", [])
        ]
        tags = [
            {"slug": str(tag_id), "name": str(tag_id)}
            for tag_id in post.get("tags", [])
        ]

        # Extract meta
        postmeta = post.get("meta", {}) or {}

        # ACF fields if available (must be dict, not list)
        acf = post.get("acf")
        if isinstance(acf, dict):
            for key, value in acf.items():
                postmeta[key] = value

        # Yoast SEO if available
        if "yoast_head_json" in post:
            yoast = post["yoast_head_json"]
            postmeta["_yoast_wpseo_title"] = yoast.get("title", "")
            postmeta["_yoast_wpseo_metadesc"] = yoast.get("description", "")

        return WXRPost(
            id=post["id"],
            title=post.get("title", {}).get("rendered", ""),
            slug=post.get("slug", ""),
            content=post.get("content", {}).get("rendered", ""),
            excerpt=post.get("excerpt", {}).get("rendered", ""),
            status=post.get("status", "draft"),
            post_type=post_type,
            author_id=post.get("author", 0),
            author_login="",
            created_at=self._parse_date(post.get("date_gmt", "")),
            modified_at=self._parse_date(post.get("modified_gmt", "")),
            parent_id=post.get("parent", 0),
            menu_order=post.get("menu_order", 0),
            guid=post.get("guid", {}).get("rendered", ""),
            link=post.get("link", ""),
            categories=categories,
            tags=tags,
            postmeta=postmeta,
        )

    def _convert_media(self, media: dict) -> WXRPost:
        """Convert REST API media to WXRPost (attachment type)."""
        postmeta = {
            "_wp_attachment_image_alt": media.get("alt_text", ""),
        }

        if "media_details" in media:
            details = media["media_details"]
            postmeta["_wp_attachment_metadata"] = {
                "width": details.get("width", 0),
                "height": details.get("height", 0),
                "file": details.get("file", ""),
            }

        return WXRPost(
            id=media["id"],
            title=media.get("title", {}).get("rendered", ""),
            slug=media.get("slug", ""),
            content=media.get("description", {}).get("rendered", ""),
            excerpt=media.get("caption", {}).get("rendered", ""),
            status="publish",
            post_type="attachment",
            author_id=media.get("author", 0),
            author_login="",
            created_at=self._parse_date(media.get("date_gmt", "")),
            modified_at=self._parse_date(media.get("modified_gmt", "")),
            guid=media.get("source_url", ""),
            link=media.get("link", ""),
            postmeta=postmeta,
        )

    def _parse_date(self, date_str: str) -> datetime:
        """Parse ISO date string."""
        if not date_str:
            return utcnow()

        try:
            # Remove timezone suffix if present
            if date_str.endswith("Z"):
                date_str = date_str[:-1]
            return datetime.fromisoformat(date_str)
        except ValueError:
            return utcnow()

    async def fetch_all(
        self,
        include_drafts: bool = True,
        include_media: bool = True,
        include_comments: bool = True,
        include_menus: bool = True,
        include_custom_types: bool = True,
        progress_callback: callable | None = None,
    ) -> WXRData:
        """
        Fetch all site data.

        Returns:
            WXRData compatible with WXR parser output
        """
        # Fetch site info
        site = await self.fetch_site_info()

        # Fetch authors
        if progress_callback:
            progress_callback(0, 0, "Fetching authors...")
        authors = await self.fetch_authors()

        # Fetch categories
        if progress_callback:
            progress_callback(0, 0, "Fetching categories...")
        categories = await self.fetch_categories()

        # Fetch tags
        if progress_callback:
            progress_callback(0, 0, "Fetching tags...")
        tags = await self.fetch_tags()

        # Fetch posts
        if progress_callback:
            progress_callback(0, 0, "Fetching posts...")
        posts = await self.fetch_posts(include_drafts)

        # Fetch pages
        if progress_callback:
            progress_callback(0, 0, "Fetching pages...")
        pages = await self.fetch_pages(include_drafts)

        all_posts = posts + pages

        # Fetch media
        if include_media:
            if progress_callback:
                progress_callback(0, 0, "Fetching media...")
            media = await self.fetch_media()
            all_posts.extend(media)

        # Fetch comments
        comments_list = []
        if include_comments:
            if progress_callback:
                progress_callback(0, 0, "Fetching comments...")
            comments_list = await self.fetch_comments()

            # Associate comments with posts
            comments_by_post = {}
            for comment in comments_list:
                if comment.post_id not in comments_by_post:
                    comments_by_post[comment.post_id] = []
                comments_by_post[comment.post_id].append(comment)

            for post in all_posts:
                post.comments = comments_by_post.get(post.id, [])

        # Fetch menus
        menus = {}
        if include_menus:
            if progress_callback:
                progress_callback(0, 0, "Fetching menus...")
            menus = await self.fetch_menus()

        # Fetch custom post types
        if include_custom_types:
            if progress_callback:
                progress_callback(0, 0, "Fetching custom post types...")
            custom_posts = await self.fetch_custom_post_types()
            for type_posts in custom_posts.values():
                all_posts.extend(type_posts)

        return WXRData(
            site=site,
            authors=authors,
            categories=categories,
            tags=tags,
            terms=[],  # Custom taxonomies via REST API require additional handling
            posts=all_posts,
            menus=menus,
        )


# Convenience function
async def fetch_wordpress_site(
    site_url: str,
    username: str = "",
    password: str = "",
    progress_callback: callable | None = None,
) -> WXRData:
    """
    Fetch all data from a WordPress site via REST API.

    Args:
        site_url: WordPress site URL
        username: WordPress username (optional)
        password: Application Password (optional)
        progress_callback: Progress callback

    Returns:
        WXRData with all site content
    """
    config = RESTClientConfig(
        site_url=site_url,
        username=username,
        password=password,
    )

    async with WordPressRESTClient(config) as client:
        return await client.fetch_all(progress_callback=progress_callback)
