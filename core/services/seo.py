"""SEOService - automatic SEO metadata generation."""

import json
import re
from typing import Any

from ..models import Entity
from .entity import EntityService
from .field import field_service


class SEOService:
    """
    SEO metadata generator.

    Automatically generates:
    - title, description
    - OGP meta tags
    - JSON-LD structured data
    - sitemap.xml
    """

    def __init__(self, entity_svc: EntityService, site_url: str = "", site_settings: dict = None):
        self.entity_svc = entity_svc
        self.site_url = site_url.rstrip("/")
        self.site_settings = site_settings or {}

    def generate_meta(self, entity: Entity) -> dict[str, Any]:
        """Generate SEO meta tags for an entity."""
        data = self.entity_svc.serialize(entity)
        ct = field_service.get_content_type(entity.type)

        # Use page-specific SEO settings if available
        title = data.get("seo_title") or self._get_title(data, ct)
        description = data.get("seo_description") or self._get_description(data, ct)
        canonical_url = data.get("seo_canonical") or self._get_url(entity, data)
        image = self._get_image(data)

        # OGP specific overrides
        og_title = data.get("og_title") or title
        og_description = data.get("og_description") or description
        og_image = data.get("og_image") or image

        # noindex/nofollow
        robots = []
        if data.get("seo_noindex"):
            robots.append("noindex")
        if data.get("seo_nofollow"):
            robots.append("nofollow")

        return {
            "title": title,
            "description": description,
            "canonical": canonical_url,
            "robots": ", ".join(robots) if robots else None,
            "ogp": self._generate_ogp(
                og_title, og_description, canonical_url, og_image, entity.type, data
            ),
            "json_ld": self._generate_json_ld(
                entity, data, title, description, canonical_url, image
            ),
        }

    def _get_title(self, data: dict, ct) -> str:
        """Extract title from entity data."""
        for field in ["title", "name"]:
            if field in data and data[field]:
                return str(data[field])
        return ct.label if ct else "Untitled"

    def _get_description(self, data: dict, ct) -> str:
        """Extract or generate description."""
        # Try explicit fields
        for field in ["description", "excerpt", "summary"]:
            if field in data and data[field]:
                return self._truncate(str(data[field]), 160)

        # Try to extract from body/content
        for field in ["body", "content"]:
            if field in data and data[field]:
                text = self._extract_text(data[field])
                if text:
                    return self._truncate(text, 160)

        return ""

    def _get_url(self, entity: Entity, data: dict) -> str:
        """Generate canonical URL."""
        slug = data.get("slug", entity.id)
        return f"{self.site_url}/{entity.type}/{slug}"

    def _get_image(self, data: dict) -> str | None:
        """Extract featured image."""
        for field in ["featured_image", "image", "thumbnail", "og_image"]:
            if field in data and data[field]:
                img = data[field]
                if isinstance(img, str):
                    if img.startswith("/"):
                        return f"{self.site_url}{img}"
                    return img
        return None

    def _generate_ogp(
        self,
        title: str,
        description: str,
        url: str,
        image: str | None,
        entity_type: str,
        entity_data: dict = None,
    ) -> dict[str, str]:
        """Generate Open Graph Protocol meta tags."""
        og_type = "article" if entity_type in ("post", "page") else "website"
        data = entity_data or {}

        ogp = {
            "og:type": og_type,
            "og:title": title,
            "og:description": description,
            "og:url": url,
        }

        # Add site name and locale from settings
        if self.site_settings.get("name"):
            ogp["og:site_name"] = self.site_settings["name"]
        ogp["og:locale"] = self.site_settings.get("locale", "ja_JP")

        if image:
            ogp["og:image"] = image

        # Article-specific tags
        if og_type == "article":
            if data.get("created_at"):
                ogp["article:published_time"] = data["created_at"]
            if data.get("updated_at"):
                ogp["article:modified_time"] = data["updated_at"]
            # Author info if available
            if data.get("author_name"):
                ogp["article:author"] = data["author_name"]

        # Twitter Card
        ogp["twitter:card"] = "summary_large_image" if image else "summary"
        ogp["twitter:title"] = title
        ogp["twitter:description"] = description
        if image:
            ogp["twitter:image"] = image
        # Twitter site from settings
        if self.site_settings.get("twitter_site"):
            ogp["twitter:site"] = self.site_settings["twitter_site"]
        # Twitter creator (author's twitter handle if available)
        if data.get("twitter_creator"):
            ogp["twitter:creator"] = data["twitter_creator"]

        return ogp

    def _generate_json_ld(
        self,
        entity: Entity,
        data: dict,
        title: str,
        description: str,
        url: str,
        image: str | None,
    ) -> dict[str, Any]:
        """Generate JSON-LD structured data."""
        if entity.type == "post":
            return self._json_ld_article(entity, data, title, description, url, image)
        elif entity.type == "page":
            return self._json_ld_webpage(title, description, url)
        else:
            return self._json_ld_thing(title, description, url)

    def _json_ld_article(
        self,
        entity: Entity,
        data: dict,
        title: str,
        description: str,
        url: str,
        image: str | None,
    ) -> dict[str, Any]:
        """Generate Article JSON-LD."""
        ld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": description,
            "url": url,
            "datePublished": entity.created_at.isoformat() if entity.created_at else None,
            "dateModified": entity.updated_at.isoformat() if entity.updated_at else None,
        }

        if image:
            ld["image"] = image

        # Author info would come from relations
        # For now, use a placeholder
        ld["author"] = {
            "@type": "Person",
            "name": "Author",
        }

        return ld

    def _json_ld_webpage(
        self,
        title: str,
        description: str,
        url: str,
    ) -> dict[str, Any]:
        """Generate WebPage JSON-LD."""
        return {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": url,
        }

    def _json_ld_thing(
        self,
        title: str,
        description: str,
        url: str,
    ) -> dict[str, Any]:
        """Generate generic Thing JSON-LD."""
        return {
            "@context": "https://schema.org",
            "@type": "Thing",
            "name": title,
            "description": description,
            "url": url,
        }

    def _extract_text(self, content: Any) -> str:
        """Extract plain text from content (Editor.js JSON or HTML)."""
        if not content:
            return ""

        data = content

        # Parse JSON string if needed
        if isinstance(content, str):
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                # Treat as HTML/plain text
                return self._strip_html(content)

        # Handle Editor.js blocks (dict with "blocks" key)
        if isinstance(data, dict) and "blocks" in data:
            texts = []
            for block in data["blocks"]:
                if block.get("type") == "paragraph":
                    text = block.get("data", {}).get("text", "")
                    texts.append(self._strip_html(text))
                elif block.get("type") == "header":
                    text = block.get("data", {}).get("text", "")
                    texts.append(self._strip_html(text))
            return " ".join(texts)

        # Fallback: convert to string
        if isinstance(data, str):
            return self._strip_html(data)

        return str(content)

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        return re.sub(r"<[^>]+>", "", text)

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        text = text.strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3].rsplit(" ", 1)[0] + "..."

    async def generate_sitemap(self, content_types: list[str] = None) -> str:
        """Generate sitemap.xml content."""
        if content_types is None:
            content_types = ["post", "page"]

        urls = []

        for ct_name in content_types:
            entities = await self.entity_svc.find(
                ct_name,
                limit=10000,
                filters={"status": "published"} if ct_name == "post" else {},
            )

            for entity in entities:
                data = self.entity_svc.serialize(entity)
                url = self._get_url(entity, data)
                lastmod = entity.updated_at.strftime("%Y-%m-%d") if entity.updated_at else ""

                urls.append(
                    {
                        "loc": url,
                        "lastmod": lastmod,
                        "changefreq": "weekly" if ct_name == "post" else "monthly",
                        "priority": "0.8" if ct_name == "post" else "0.5",
                    }
                )

        # Generate XML
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

        for url_data in urls:
            xml_parts.append("  <url>")
            xml_parts.append(f"    <loc>{url_data['loc']}</loc>")
            if url_data["lastmod"]:
                xml_parts.append(f"    <lastmod>{url_data['lastmod']}</lastmod>")
            xml_parts.append(f"    <changefreq>{url_data['changefreq']}</changefreq>")
            xml_parts.append(f"    <priority>{url_data['priority']}</priority>")
            xml_parts.append("  </url>")

        xml_parts.append("</urlset>")

        return "\n".join(xml_parts)

    def generate_site_json_ld(self) -> list[dict[str, Any]]:
        """Generate site-wide JSON-LD (Organization, WebSite)."""
        schemas = []

        site_name = self.site_settings.get("name", "Focomy")
        site_description = self.site_settings.get("description", "")

        # Organization schema
        org = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": site_name,
            "url": self.site_url,
        }
        if self.site_settings.get("logo"):
            org["logo"] = self.site_settings["logo"]
        if self.site_settings.get("email"):
            org["email"] = self.site_settings["email"]
        if self.site_settings.get("social_links"):
            org["sameAs"] = self.site_settings["social_links"]
        schemas.append(org)

        # WebSite schema with SearchAction
        website = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site_name,
            "url": self.site_url,
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": f"{self.site_url}/search?q={{search_term_string}}",
                },
                "query-input": "required name=search_term_string",
            },
        }
        if site_description:
            website["description"] = site_description
        schemas.append(website)

        return schemas

    def generate_person_json_ld(self, author_data: dict) -> dict[str, Any]:
        """Generate Person JSON-LD for author."""
        person = {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": author_data.get("name", "Author"),
        }
        if author_data.get("email"):
            person["email"] = author_data["email"]
        if author_data.get("url"):
            person["url"] = author_data["url"]
        if author_data.get("image"):
            person["image"] = author_data["image"]
        if author_data.get("description"):
            person["description"] = author_data["description"]
        if author_data.get("social_links"):
            person["sameAs"] = author_data["social_links"]
        return person

    def generate_faq_json_ld(self, faq_items: list[dict]) -> dict[str, Any]:
        """Generate FAQPage JSON-LD.

        Args:
            faq_items: List of {"question": str, "answer": str}
        """
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                }
                for item in faq_items
            ],
        }

    def generate_breadcrumb_json_ld(self, items: list[dict]) -> dict[str, Any]:
        """Generate BreadcrumbList JSON-LD.

        Args:
            items: List of {"name": str, "url": str}
        """
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": item["name"], "item": item["url"]}
                for i, item in enumerate(items)
            ],
        }

    def render_meta_tags(self, meta: dict) -> str:
        """Render meta tags as HTML."""
        lines = []

        # Basic meta
        if meta.get("title"):
            lines.append(f'<title>{meta["title"]}</title>')
        if meta.get("description"):
            lines.append(f'<meta name="description" content="{meta["description"]}">')
        if meta.get("canonical"):
            lines.append(f'<link rel="canonical" href="{meta["canonical"]}">')
        if meta.get("robots"):
            lines.append(f'<meta name="robots" content="{meta["robots"]}">')

        # OGP
        for key, value in meta.get("ogp", {}).items():
            if key.startswith("twitter:"):
                lines.append(f'<meta name="{key}" content="{value}">')
            else:
                lines.append(f'<meta property="{key}" content="{value}">')

        # JSON-LD
        if meta.get("json_ld"):
            json_ld = json.dumps(meta["json_ld"], ensure_ascii=False)
            lines.append(f'<script type="application/ld+json">{json_ld}</script>')

        return "\n".join(lines)

    def render_site_json_ld(self) -> str:
        """Render site-wide JSON-LD as HTML script tags."""
        schemas = self.generate_site_json_ld()
        lines = []
        for schema in schemas:
            json_ld = json.dumps(schema, ensure_ascii=False)
            lines.append(f'<script type="application/ld+json">{json_ld}</script>')
        return "\n".join(lines)
