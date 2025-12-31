"""WXR Parser - WordPress eXtended RSS format parser."""

import xml.etree.ElementTree as ET
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...utils import utcnow
from html import unescape
from pathlib import Path
from typing import Any

# WordPress XML namespaces
WP_NS = "http://wordpress.org/export/1.2/"
EXCERPT_NS = "http://wordpress.org/export/1.2/excerpt/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
DC_NS = "http://purl.org/dc/elements/1.1/"

NAMESPACES = {
    "wp": WP_NS,
    "excerpt": EXCERPT_NS,
    "content": CONTENT_NS,
    "dc": DC_NS,
}


@dataclass
class WXRPost:
    """Parsed WordPress post."""

    id: int
    title: str
    slug: str
    content: str
    excerpt: str
    status: str
    post_type: str
    author_id: int
    author_login: str
    created_at: datetime
    modified_at: datetime
    parent_id: int = 0
    menu_order: int = 0
    password: str = ""
    comment_status: str = "open"
    ping_status: str = "open"
    guid: str = ""
    link: str = ""
    categories: list[dict] = field(default_factory=list)
    tags: list[dict] = field(default_factory=list)
    custom_taxonomies: list[dict] = field(default_factory=list)
    postmeta: dict[str, Any] = field(default_factory=dict)
    comments: list["WXRComment"] = field(default_factory=list)


@dataclass
class WXRComment:
    """Parsed WordPress comment."""

    id: int
    post_id: int
    author: str
    author_email: str
    author_url: str
    author_ip: str
    date: datetime
    content: str
    approved: str
    parent_id: int = 0
    user_id: int = 0


@dataclass
class WXRTerm:
    """Parsed WordPress term (category/tag/custom taxonomy)."""

    id: int
    name: str
    slug: str
    taxonomy: str
    description: str = ""
    parent_id: int = 0


@dataclass
class WXRAuthor:
    """Parsed WordPress author."""

    id: int
    login: str
    email: str
    display_name: str
    first_name: str = ""
    last_name: str = ""


@dataclass
class WXRMenuItem:
    """Parsed WordPress menu item."""

    id: int
    title: str
    url: str
    menu_id: int
    parent_id: int = 0
    order: int = 0
    object_type: str = ""  # post, page, category, custom
    object_id: int = 0
    target: str = ""
    classes: list[str] = field(default_factory=list)


@dataclass
class WXRSiteInfo:
    """WordPress site information."""

    title: str
    link: str
    description: str
    language: str
    base_site_url: str
    base_blog_url: str
    wp_version: str = ""


@dataclass
class WXRData:
    """Complete parsed WXR data."""

    site: WXRSiteInfo
    authors: list[WXRAuthor]
    categories: list[WXRTerm]
    tags: list[WXRTerm]
    terms: list[WXRTerm]
    posts: list[WXRPost]
    menus: dict[str, list[WXRMenuItem]]


class WXRParser:
    """
    WordPress eXtended RSS (WXR) parser.

    Parses WordPress export XML files into structured data.
    Handles namespaces, serialized PHP data, and encoding issues.
    """

    def __init__(self):
        self._current_file: Path | None = None

    def parse(self, file_path: Path) -> WXRData:
        """
        Parse a WXR file.

        Args:
            file_path: Path to the WXR XML file

        Returns:
            WXRData containing all parsed content
        """
        self._current_file = file_path

        tree = ET.parse(file_path)
        root = tree.getroot()
        channel = root.find("channel")

        if channel is None:
            raise ValueError("Invalid WXR file: no channel element")

        # Parse site info
        site = self._parse_site_info(channel)

        # Parse authors
        authors = list(self._parse_authors(channel))

        # Parse categories and tags
        categories = []
        tags = []
        terms = []

        for term_el in channel.findall("wp:term", NAMESPACES):
            term = self._parse_term(term_el)
            if term:
                if term.taxonomy == "category":
                    categories.append(term)
                elif term.taxonomy == "post_tag":
                    tags.append(term)
                else:
                    terms.append(term)

        # Also parse old-style category elements
        for cat_el in channel.findall("wp:category", NAMESPACES):
            cat = self._parse_old_category(cat_el)
            if cat:
                categories.append(cat)

        for tag_el in channel.findall("wp:tag", NAMESPACES):
            tag = self._parse_old_tag(tag_el)
            if tag:
                tags.append(tag)

        # Parse posts (includes pages, attachments, menu items, etc.)
        posts = []
        menu_items: dict[str, list[WXRMenuItem]] = {}

        for item in channel.findall("item"):
            post_type = self._get_text(item, "wp:post_type")

            if post_type == "nav_menu_item":
                menu_item = self._parse_menu_item(item)
                if menu_item:
                    menu_name = self._get_menu_name(item, terms)
                    if menu_name not in menu_items:
                        menu_items[menu_name] = []
                    menu_items[menu_name].append(menu_item)
            else:
                post = self._parse_post(item)
                if post:
                    posts.append(post)

        return WXRData(
            site=site,
            authors=authors,
            categories=categories,
            tags=tags,
            terms=terms,
            posts=posts,
            menus=menu_items,
        )

    def parse_streaming(self, file_path: Path) -> Generator[WXRPost, None, None]:
        """
        Parse WXR file in streaming mode (for large files).

        Yields posts one at a time to reduce memory usage.
        """
        # Use iterparse for memory efficiency
        context = ET.iterparse(file_path, events=("end",))

        for _event, elem in context:
            if elem.tag == "item":
                post = self._parse_post(elem)
                if post:
                    yield post
                elem.clear()

    def _parse_site_info(self, channel: ET.Element) -> WXRSiteInfo:
        """Parse site information from channel."""
        return WXRSiteInfo(
            title=self._get_text(channel, "title") or "",
            link=self._get_text(channel, "link") or "",
            description=self._get_text(channel, "description") or "",
            language=self._get_text(channel, "language") or "en",
            base_site_url=self._get_text(channel, "wp:base_site_url") or "",
            base_blog_url=self._get_text(channel, "wp:base_blog_url") or "",
            wp_version=self._get_text(channel, "generator") or "",
        )

    def _parse_authors(self, channel: ET.Element) -> Generator[WXRAuthor, None, None]:
        """Parse authors from channel."""
        for author_el in channel.findall("wp:author", NAMESPACES):
            author_id = self._get_int(author_el, "wp:author_id")
            if author_id:
                yield WXRAuthor(
                    id=author_id,
                    login=self._get_text(author_el, "wp:author_login") or "",
                    email=self._get_text(author_el, "wp:author_email") or "",
                    display_name=self._get_text(author_el, "wp:author_display_name") or "",
                    first_name=self._get_text(author_el, "wp:author_first_name") or "",
                    last_name=self._get_text(author_el, "wp:author_last_name") or "",
                )

    def _parse_term(self, term_el: ET.Element) -> WXRTerm | None:
        """Parse a wp:term element."""
        term_id = self._get_int(term_el, "wp:term_id")
        if not term_id:
            return None

        return WXRTerm(
            id=term_id,
            name=self._get_text(term_el, "wp:term_name") or "",
            slug=self._get_text(term_el, "wp:term_slug") or "",
            taxonomy=self._get_text(term_el, "wp:term_taxonomy") or "",
            description=self._get_text(term_el, "wp:term_description") or "",
            parent_id=self._get_int(term_el, "wp:term_parent") or 0,
        )

    def _parse_old_category(self, cat_el: ET.Element) -> WXRTerm | None:
        """Parse old-style wp:category element."""
        return WXRTerm(
            id=self._get_int(cat_el, "wp:term_id") or 0,
            name=self._get_text(cat_el, "wp:cat_name") or "",
            slug=self._get_text(cat_el, "wp:category_nicename") or "",
            taxonomy="category",
            description=self._get_text(cat_el, "wp:category_description") or "",
            parent_id=0,  # Old format doesn't include parent
        )

    def _parse_old_tag(self, tag_el: ET.Element) -> WXRTerm | None:
        """Parse old-style wp:tag element."""
        return WXRTerm(
            id=self._get_int(tag_el, "wp:term_id") or 0,
            name=self._get_text(tag_el, "wp:tag_name") or "",
            slug=self._get_text(tag_el, "wp:tag_slug") or "",
            taxonomy="post_tag",
            description=self._get_text(tag_el, "wp:tag_description") or "",
            parent_id=0,
        )

    def _parse_post(self, item: ET.Element) -> WXRPost | None:
        """Parse a post/page/attachment item."""
        post_id = self._get_int(item, "wp:post_id")
        if not post_id:
            return None

        # Parse categories and tags
        categories = []
        tags = []
        custom_taxonomies = []

        for cat_el in item.findall("category"):
            domain = cat_el.get("domain", "category")
            nicename = cat_el.get("nicename", "")
            name = cat_el.text or ""

            term_data = {"slug": nicename, "name": name}

            if domain == "category":
                categories.append(term_data)
            elif domain == "post_tag":
                tags.append(term_data)
            else:
                custom_taxonomies.append(
                    {
                        "taxonomy": domain,
                        "slug": nicename,
                        "name": name,
                    }
                )

        # Parse post meta
        postmeta = {}
        for meta_el in item.findall("wp:postmeta", NAMESPACES):
            key = self._get_text(meta_el, "wp:meta_key")
            value = self._get_text(meta_el, "wp:meta_value")
            if key:
                postmeta[key] = value

        # Parse comments
        comments = []
        for comment_el in item.findall("wp:comment", NAMESPACES):
            comment = self._parse_comment(comment_el, post_id)
            if comment:
                comments.append(comment)

        # Parse dates
        created_at = self._parse_date(self._get_text(item, "wp:post_date_gmt"))
        modified_at = self._parse_date(self._get_text(item, "wp:post_modified_gmt"))

        return WXRPost(
            id=post_id,
            title=unescape(self._get_text(item, "title") or ""),
            slug=self._get_text(item, "wp:post_name") or "",
            content=self._get_text(item, "content:encoded") or "",
            excerpt=self._get_text(item, "excerpt:encoded") or "",
            status=self._get_text(item, "wp:status") or "draft",
            post_type=self._get_text(item, "wp:post_type") or "post",
            author_id=self._get_int(item, "dc:creator") or 0,
            author_login=self._get_text(item, "dc:creator") or "",
            created_at=created_at,
            modified_at=modified_at,
            parent_id=self._get_int(item, "wp:post_parent") or 0,
            menu_order=self._get_int(item, "wp:menu_order") or 0,
            password=self._get_text(item, "wp:post_password") or "",
            comment_status=self._get_text(item, "wp:comment_status") or "open",
            ping_status=self._get_text(item, "wp:ping_status") or "open",
            guid=self._get_text(item, "guid") or "",
            link=self._get_text(item, "link") or "",
            categories=categories,
            tags=tags,
            custom_taxonomies=custom_taxonomies,
            postmeta=postmeta,
            comments=comments,
        )

    def _parse_comment(self, comment_el: ET.Element, post_id: int) -> WXRComment | None:
        """Parse a comment."""
        comment_id = self._get_int(comment_el, "wp:comment_id")
        if not comment_id:
            return None

        return WXRComment(
            id=comment_id,
            post_id=post_id,
            author=self._get_text(comment_el, "wp:comment_author") or "",
            author_email=self._get_text(comment_el, "wp:comment_author_email") or "",
            author_url=self._get_text(comment_el, "wp:comment_author_url") or "",
            author_ip=self._get_text(comment_el, "wp:comment_author_IP") or "",
            date=self._parse_date(self._get_text(comment_el, "wp:comment_date_gmt")),
            content=self._get_text(comment_el, "wp:comment_content") or "",
            approved=self._get_text(comment_el, "wp:comment_approved") or "0",
            parent_id=self._get_int(comment_el, "wp:comment_parent") or 0,
            user_id=self._get_int(comment_el, "wp:comment_user_id") or 0,
        )

    def _parse_menu_item(self, item: ET.Element) -> WXRMenuItem | None:
        """Parse a navigation menu item."""
        post_id = self._get_int(item, "wp:post_id")
        if not post_id:
            return None

        postmeta = {}
        for meta_el in item.findall("wp:postmeta", NAMESPACES):
            key = self._get_text(meta_el, "wp:meta_key")
            value = self._get_text(meta_el, "wp:meta_value")
            if key:
                postmeta[key] = value

        return WXRMenuItem(
            id=post_id,
            title=unescape(self._get_text(item, "title") or ""),
            url=postmeta.get("_menu_item_url", ""),
            menu_id=0,  # Will be determined later
            parent_id=int(postmeta.get("_menu_item_menu_item_parent", 0)),
            order=self._get_int(item, "wp:menu_order") or 0,
            object_type=postmeta.get("_menu_item_object", ""),
            object_id=int(postmeta.get("_menu_item_object_id", 0)),
            target=postmeta.get("_menu_item_target", ""),
            classes=(
                postmeta.get("_menu_item_classes", "").split()
                if postmeta.get("_menu_item_classes")
                else []
            ),
        )

    def _get_menu_name(self, item: ET.Element, terms: list[WXRTerm]) -> str:
        """Get menu name from menu item's term relationship."""
        for cat_el in item.findall("category"):
            domain = cat_el.get("domain", "")
            if domain == "nav_menu":
                return cat_el.text or "default"
        return "default"

    def _get_text(self, el: ET.Element, path: str) -> str | None:
        """Get text content of a child element."""
        # Handle namespaced paths
        if ":" in path:
            prefix, local = path.split(":", 1)
            if prefix in NAMESPACES:
                full_path = f"{{{NAMESPACES[prefix]}}}{local}"
                child = el.find(full_path)
            else:
                child = el.find(path)
        else:
            child = el.find(path)

        if child is not None and child.text:
            return child.text
        return None

    def _get_int(self, el: ET.Element, path: str) -> int:
        """Get integer value of a child element."""
        text = self._get_text(el, path)
        if text:
            try:
                return int(text)
            except ValueError:
                pass
        return 0

    def _parse_date(self, date_str: str | None) -> datetime:
        """Parse WordPress date string."""
        if not date_str or date_str == "0000-00-00 00:00:00":
            return utcnow()

        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.fromisoformat(date_str)
            except ValueError:
                return utcnow()
