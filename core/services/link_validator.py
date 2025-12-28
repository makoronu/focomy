"""LinkValidatorService - detect broken links and orphan pages."""

import asyncio
import json
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService
from .field import field_service


class LinkValidatorService:
    """
    Link validation service.

    Detects:
    - Broken internal links (404s)
    - Broken external links (connection errors, 4xx/5xx)
    - Orphan pages (pages not linked from anywhere)
    """

    def __init__(self, db: AsyncSession, site_url: str = ""):
        self.db = db
        self.entity_svc = EntityService(db)
        self.site_url = site_url.rstrip("/")

    async def validate_all_links(self, check_external: bool = False) -> dict:
        """
        Validate all links across published content.

        Args:
            check_external: Whether to check external URLs (slow)

        Returns:
            Dict with broken_links, orphan_pages, and stats
        """
        # Collect all pages and their outbound links
        pages = await self._get_all_published_pages()
        all_links = await self._extract_all_links(pages)
        internal_pages = {p["url"] for p in pages}

        broken_links = []
        external_errors = []

        # Check internal links
        for link in all_links["internal"]:
            target_path = link["href"]
            # Normalize path
            if not target_path.startswith("/"):
                continue

            # Check if the target exists
            if not await self._internal_link_exists(target_path, internal_pages):
                broken_links.append(
                    {
                        "source_url": link["source_url"],
                        "source_title": link["source_title"],
                        "source_id": link["source_id"],
                        "target_url": target_path,
                        "type": "internal",
                        "status": "not_found",
                    }
                )

        # Check external links if requested
        if check_external:
            external_results = await self._check_external_links(all_links["external"])
            for result in external_results:
                if result["status"] != "ok":
                    external_errors.append(result)

        return {
            "broken_links": broken_links,
            "external_errors": external_errors if check_external else [],
            "stats": {
                "total_pages": len(pages),
                "total_internal_links": len(all_links["internal"]),
                "total_external_links": len(all_links["external"]),
                "broken_internal": len(broken_links),
                "broken_external": len(external_errors) if check_external else 0,
            },
        }

    async def find_orphan_pages(self) -> list[dict]:
        """
        Find pages that are not linked from anywhere.

        Returns:
            List of orphan pages with their details
        """
        pages = await self._get_all_published_pages()
        all_links = await self._extract_all_links(pages)

        # Build set of linked pages
        linked_urls = set()
        for link in all_links["internal"]:
            href = link["href"]
            if href.startswith("/"):
                linked_urls.add(href)

        # Find pages not in the linked set
        orphans = []
        for page in pages:
            page_url = page["url"]
            # Skip home page
            if page_url == "/":
                continue

            if page_url not in linked_urls:
                orphans.append(
                    {
                        "id": page["id"],
                        "title": page["title"],
                        "url": page_url,
                        "type": page["type"],
                        "created_at": page.get("created_at", ""),
                    }
                )

        return orphans

    async def validate_single_page(self, entity_id: str) -> dict:
        """Validate links in a single page."""
        entity = await self.entity_svc.get(entity_id)
        if not entity:
            return {"error": "Entity not found"}

        data = self.entity_svc.serialize(entity)
        links = self._extract_links_from_entity(entity.id, entity.type, data)

        broken = []
        pages = await self._get_all_published_pages()
        internal_pages = {p["url"] for p in pages}

        for link in links["internal"]:
            if not await self._internal_link_exists(link["href"], internal_pages):
                broken.append(
                    {
                        "target_url": link["href"],
                        "type": "internal",
                        "status": "not_found",
                    }
                )

        return {
            "entity_id": entity_id,
            "broken_links": broken,
            "total_links": len(links["internal"]) + len(links["external"]),
        }

    async def _get_all_published_pages(self) -> list[dict]:
        """Get all published pages and posts."""
        pages = []

        for ct_name in ["post", "page"]:
            ct = field_service.get_content_type(ct_name)
            if not ct:
                continue

            entities = await self.entity_svc.find(
                ct_name,
                limit=10000,
                filters={"status": "published"},
            )

            for entity in entities:
                data = self.entity_svc.serialize(entity)
                slug = data.get("slug", entity.id)
                path_prefix = ct.path_prefix.strip("/") if ct.path_prefix else ct_name

                pages.append(
                    {
                        "id": entity.id,
                        "type": ct_name,
                        "title": data.get("title", data.get("name", "Untitled")),
                        "url": f"/{path_prefix}/{slug}",
                        "data": data,
                        "created_at": data.get("created_at", ""),
                    }
                )

        # Also add category pages
        categories = await self.entity_svc.find("category", limit=1000)
        for cat in categories:
            data = self.entity_svc.serialize(cat)
            slug = data.get("slug", cat.id)
            pages.append(
                {
                    "id": cat.id,
                    "type": "category",
                    "title": data.get("name", "Untitled"),
                    "url": f"/category/{slug}",
                    "data": data,
                    "created_at": data.get("created_at", ""),
                }
            )

        return pages

    async def _extract_all_links(self, pages: list[dict]) -> dict:
        """Extract all links from all pages."""
        internal_links = []
        external_links = []

        for page in pages:
            links = self._extract_links_from_entity(
                page["id"],
                page["type"],
                page["data"],
            )

            for link in links["internal"]:
                link["source_url"] = page["url"]
                link["source_title"] = page["title"]
                link["source_id"] = page["id"]
                internal_links.append(link)

            for link in links["external"]:
                link["source_url"] = page["url"]
                link["source_title"] = page["title"]
                link["source_id"] = page["id"]
                external_links.append(link)

        return {
            "internal": internal_links,
            "external": external_links,
        }

    def _extract_links_from_entity(
        self,
        entity_id: str,
        entity_type: str,
        data: dict,
    ) -> dict:
        """Extract links from entity content."""
        internal = []
        external = []

        # Check body/content field (Editor.js format or HTML)
        for field in ["body", "content"]:
            if field not in data:
                continue

            content = data[field]
            if not content:
                continue

            # Parse Editor.js JSON
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    # Treat as HTML
                    links = self._extract_links_from_html(content)
                    for href in links:
                        if self._is_internal_link(href):
                            internal.append({"href": self._normalize_path(href)})
                        else:
                            external.append({"href": href})
                    continue

            # Process Editor.js blocks
            if isinstance(content, dict) and "blocks" in content:
                for block in content.get("blocks", []):
                    block_links = self._extract_links_from_block(block)
                    for href in block_links:
                        if self._is_internal_link(href):
                            internal.append({"href": self._normalize_path(href)})
                        else:
                            external.append({"href": href})

        return {"internal": internal, "external": external}

    def _extract_links_from_block(self, block: dict) -> list[str]:
        """Extract links from an Editor.js block."""
        links = []
        block_type = block.get("type", "")
        block_data = block.get("data", {})

        if block_type == "paragraph":
            text = block_data.get("text", "")
            links.extend(self._extract_links_from_html(text))
        elif block_type == "header":
            text = block_data.get("text", "")
            links.extend(self._extract_links_from_html(text))
        elif block_type == "list":
            for item in block_data.get("items", []):
                if isinstance(item, str):
                    links.extend(self._extract_links_from_html(item))
                elif isinstance(item, dict):
                    links.extend(self._extract_links_from_html(item.get("content", "")))
        elif block_type == "linkTool":
            link = block_data.get("link", "")
            if link:
                links.append(link)
        elif block_type == "image":
            # Image URLs are typically internal/CDN, skip for link checking
            pass

        return links

    def _extract_links_from_html(self, html: str) -> list[str]:
        """Extract href values from HTML content."""
        if not html:
            return []

        # Simple regex to extract href attributes
        pattern = r'href=["\']([^"\']+)["\']'
        matches = re.findall(pattern, html, re.IGNORECASE)
        return matches

    def _is_internal_link(self, href: str) -> bool:
        """Check if a link is internal."""
        if not href:
            return False

        # Relative paths are internal
        if href.startswith("/"):
            return True

        # Check if it's the same domain
        if self.site_url and href.startswith(self.site_url):
            return True

        # External
        if href.startswith(("http://", "https://", "//")):
            return False

        # Anchors, mailto, tel, etc.
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return False

        # Assume relative paths are internal
        return True

    def _normalize_path(self, href: str) -> str:
        """Normalize a path for comparison."""
        # Remove site URL prefix
        if self.site_url and href.startswith(self.site_url):
            href = href[len(self.site_url) :]

        # Ensure starts with /
        if not href.startswith("/"):
            href = "/" + href

        # Remove trailing slash (except for root)
        if href != "/" and href.endswith("/"):
            href = href[:-1]

        # Remove query string and fragment
        if "?" in href:
            href = href.split("?")[0]
        if "#" in href:
            href = href.split("#")[0]

        return href

    async def _internal_link_exists(
        self,
        path: str,
        known_pages: set[str],
    ) -> bool:
        """Check if an internal link target exists."""
        # Normalize path
        path = self._normalize_path(path)

        # Check in known pages
        if path in known_pages:
            return True

        # Check special routes
        special_routes = [
            "/",
            "/search",
            "/feed.xml",
            "/atom.xml",
            "/feed.json",
            "/sitemap.xml",
            "/robots.txt",
            "/manifest.json",
        ]

        if path in special_routes:
            return True

        # Check archive routes
        if re.match(r"^/archive/\d{4}/\d{1,2}$", path):
            return True

        return False

    async def _check_external_links(self, links: list[dict]) -> list[dict]:
        """Check external links for accessibility."""
        results = []

        # Deduplicate URLs
        unique_urls = {}
        for link in links:
            href = link["href"]
            if href not in unique_urls:
                unique_urls[href] = link

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for href, link in unique_urls.items():
                try:
                    response = await client.head(href)
                    if response.status_code >= 400:
                        results.append(
                            {
                                "source_url": link["source_url"],
                                "source_title": link["source_title"],
                                "source_id": link["source_id"],
                                "target_url": href,
                                "type": "external",
                                "status": f"http_{response.status_code}",
                            }
                        )
                    else:
                        results.append(
                            {
                                "target_url": href,
                                "type": "external",
                                "status": "ok",
                            }
                        )
                except httpx.TimeoutException:
                    results.append(
                        {
                            "source_url": link["source_url"],
                            "source_title": link["source_title"],
                            "source_id": link["source_id"],
                            "target_url": href,
                            "type": "external",
                            "status": "timeout",
                        }
                    )
                except httpx.RequestError:
                    results.append(
                        {
                            "source_url": link["source_url"],
                            "source_title": link["source_title"],
                            "source_id": link["source_id"],
                            "target_url": href,
                            "type": "external",
                            "status": "connection_error",
                        }
                    )

                # Rate limit
                await asyncio.sleep(0.1)

        return results
