"""Redirect Generator - Creates URL redirects for WordPress migration."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse


@dataclass
class Redirect:
    """Represents a URL redirect."""

    from_path: str
    to_path: str
    status_code: int = 301
    regex: bool = False
    preserve_query: bool = True
    priority: int = 0
    comment: str = ""


@dataclass
class RedirectReport:
    """Report of generated redirects."""

    redirects: list[Redirect] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


class RedirectGenerator:
    """
    Generates URL redirects for WordPress migration.

    Supports:
    - Post/page URL changes
    - Category/tag archive redirects
    - Author archive redirects
    - Date archive redirects
    - Attachment redirects
    - Custom permalink patterns
    - Regex redirects for patterns
    """

    def __init__(
        self,
        old_base_url: str,
        new_base_url: str,
        old_permalink_structure: str = "/%postname%/",
    ):
        """
        Initialize RedirectGenerator.

        Args:
            old_base_url: Old WordPress site URL
            new_base_url: New Focomy site URL
            old_permalink_structure: WordPress permalink structure
        """
        self.old_base = old_base_url.rstrip("/")
        self.new_base = new_base_url.rstrip("/")
        self.permalink_structure = old_permalink_structure

        # Parse old URL
        parsed = urlparse(old_base_url)
        self.old_domain = parsed.netloc

    def generate_from_posts(
        self,
        posts: list[dict],
        new_path_prefix: str = "/blog",
    ) -> list[Redirect]:
        """
        Generate redirects from WordPress posts.

        Args:
            posts: List of post data with old_url, new_slug, post_type
            new_path_prefix: New URL prefix for posts

        Returns:
            List of redirects
        """
        redirects = []

        for post in posts:
            old_url = post.get("old_url", "")
            new_slug = post.get("new_slug", post.get("slug", ""))
            post_type = post.get("post_type", "post")

            if not old_url or not new_slug:
                continue

            # Extract path from old URL
            old_path = self._url_to_path(old_url)
            if not old_path:
                continue

            # Determine new path
            if post_type == "page":
                new_path = f"/page/{new_slug}"
            elif post_type == "attachment":
                # Skip attachments or redirect to media
                continue
            else:
                new_path = f"{new_path_prefix}/{new_slug}"

            redirects.append(
                Redirect(
                    from_path=old_path,
                    to_path=new_path,
                    status_code=301,
                    comment=f"Post: {post.get('title', new_slug)[:50]}",
                )
            )

            # Also handle variations (with/without trailing slash)
            if old_path.endswith("/"):
                redirects.append(
                    Redirect(
                        from_path=old_path.rstrip("/"),
                        to_path=new_path,
                        status_code=301,
                    )
                )
            else:
                redirects.append(
                    Redirect(
                        from_path=old_path + "/",
                        to_path=new_path,
                        status_code=301,
                    )
                )

        return redirects

    def generate_from_categories(
        self,
        categories: list[dict],
        new_path_prefix: str = "/category",
    ) -> list[Redirect]:
        """
        Generate redirects for category archives.

        Args:
            categories: List of category data with old_slug, new_slug
            new_path_prefix: New URL prefix for categories

        Returns:
            List of redirects
        """
        redirects = []

        for cat in categories:
            old_slug = cat.get("old_slug", cat.get("slug", ""))
            new_slug = cat.get("new_slug", old_slug)

            if not old_slug:
                continue

            # WordPress default category URL
            old_path = f"/category/{old_slug}"
            new_path = f"{new_path_prefix}/{new_slug}"

            redirects.append(
                Redirect(
                    from_path=old_path,
                    to_path=new_path,
                    status_code=301,
                    comment=f"Category: {cat.get('name', old_slug)}",
                )
            )

            # With trailing slash
            redirects.append(
                Redirect(
                    from_path=old_path + "/",
                    to_path=new_path,
                    status_code=301,
                )
            )

            # Paginated
            redirects.append(
                Redirect(
                    from_path=f"{old_path}/page/(.+)",
                    to_path=f"{new_path}?page=$1",
                    status_code=301,
                    regex=True,
                )
            )

        return redirects

    def generate_from_tags(
        self,
        tags: list[dict],
        new_path_prefix: str = "/tag",
    ) -> list[Redirect]:
        """
        Generate redirects for tag archives.

        Args:
            tags: List of tag data with old_slug, new_slug
            new_path_prefix: New URL prefix for tags

        Returns:
            List of redirects
        """
        redirects = []

        for tag in tags:
            old_slug = tag.get("old_slug", tag.get("slug", ""))
            new_slug = tag.get("new_slug", old_slug)

            if not old_slug:
                continue

            old_path = f"/tag/{old_slug}"
            new_path = f"{new_path_prefix}/{new_slug}"

            redirects.append(
                Redirect(
                    from_path=old_path,
                    to_path=new_path,
                    status_code=301,
                    comment=f"Tag: {tag.get('name', old_slug)}",
                )
            )

            redirects.append(
                Redirect(
                    from_path=old_path + "/",
                    to_path=new_path,
                    status_code=301,
                )
            )

        return redirects

    def generate_from_authors(
        self,
        authors: list[dict],
        new_path_prefix: str = "/author",
    ) -> list[Redirect]:
        """
        Generate redirects for author archives.

        Args:
            authors: List of author data with login, new_slug
            new_path_prefix: New URL prefix for authors

        Returns:
            List of redirects
        """
        redirects = []

        for author in authors:
            old_login = author.get("login", "")
            new_slug = author.get("new_slug", old_login)

            if not old_login:
                continue

            old_path = f"/author/{old_login}"
            new_path = f"{new_path_prefix}/{new_slug}"

            redirects.append(
                Redirect(
                    from_path=old_path,
                    to_path=new_path,
                    status_code=301,
                    comment=f"Author: {author.get('display_name', old_login)}",
                )
            )

            redirects.append(
                Redirect(
                    from_path=old_path + "/",
                    to_path=new_path,
                    status_code=301,
                )
            )

        return redirects

    def generate_date_archive_redirects(
        self,
        archive_path: str = "/blog/archive",
    ) -> list[Redirect]:
        """
        Generate redirects for date-based archives.

        Args:
            archive_path: New archive path

        Returns:
            List of regex-based redirects
        """
        return [
            # Year archive: /2023/ -> /blog/archive/2023
            Redirect(
                from_path=r"^/(\d{4})/?$",
                to_path=f"{archive_path}/$1",
                status_code=301,
                regex=True,
                comment="Year archive",
            ),
            # Month archive: /2023/01/ -> /blog/archive/2023/01
            Redirect(
                from_path=r"^/(\d{4})/(\d{2})/?$",
                to_path=f"{archive_path}/$1/$2",
                status_code=301,
                regex=True,
                comment="Month archive",
            ),
            # Day archive: /2023/01/15/ -> /blog/archive/2023/01/15
            Redirect(
                from_path=r"^/(\d{4})/(\d{2})/(\d{2})/?$",
                to_path=f"{archive_path}/$1/$2/$3",
                status_code=301,
                regex=True,
                comment="Day archive",
            ),
        ]

    def generate_feed_redirects(
        self,
        new_feed_path: str = "/blog/feed.xml",
    ) -> list[Redirect]:
        """
        Generate redirects for RSS feeds.

        Args:
            new_feed_path: New feed URL

        Returns:
            List of redirects
        """
        return [
            Redirect(from_path="/feed", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/feed/", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/rss", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/rss/", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/atom", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/atom/", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/feed/rss", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/feed/rss2", to_path=new_feed_path, status_code=301),
            Redirect(from_path="/feed/atom", to_path=new_feed_path, status_code=301),
        ]

    def generate_wp_admin_redirects(
        self,
        new_admin_path: str = "/admin",
    ) -> list[Redirect]:
        """
        Generate redirects for wp-admin URLs.

        Args:
            new_admin_path: New admin URL

        Returns:
            List of redirects
        """
        return [
            Redirect(
                from_path="/wp-admin",
                to_path=new_admin_path,
                status_code=301,
                comment="Admin redirect",
            ),
            Redirect(
                from_path="/wp-admin/",
                to_path=new_admin_path,
                status_code=301,
            ),
            Redirect(
                from_path="/wp-login.php",
                to_path=f"{new_admin_path}/login",
                status_code=301,
            ),
            # Block wp-content access
            Redirect(
                from_path="/wp-content/",
                to_path="/",
                status_code=410,  # Gone
                comment="Block old wp-content",
            ),
        ]

    def generate_all(
        self,
        posts: list[dict],
        categories: list[dict],
        tags: list[dict],
        authors: list[dict],
        config: dict | None = None,
    ) -> RedirectReport:
        """
        Generate all redirects.

        Args:
            posts: Post data
            categories: Category data
            tags: Tag data
            authors: Author data
            config: Optional configuration overrides

        Returns:
            RedirectReport with all generated redirects
        """
        config = config or {}
        report = RedirectReport()

        # Collect all redirects
        all_redirects = []

        # Post redirects
        all_redirects.extend(
            self.generate_from_posts(
                posts,
                config.get("post_path_prefix", "/blog"),
            )
        )

        # Category redirects
        all_redirects.extend(
            self.generate_from_categories(
                categories,
                config.get("category_path_prefix", "/category"),
            )
        )

        # Tag redirects
        all_redirects.extend(
            self.generate_from_tags(
                tags,
                config.get("tag_path_prefix", "/tag"),
            )
        )

        # Author redirects
        all_redirects.extend(
            self.generate_from_authors(
                authors,
                config.get("author_path_prefix", "/author"),
            )
        )

        # Date archives
        if config.get("include_date_archives", True):
            all_redirects.extend(
                self.generate_date_archive_redirects(
                    config.get("archive_path", "/blog/archive"),
                )
            )

        # Feeds
        if config.get("include_feeds", True):
            all_redirects.extend(
                self.generate_feed_redirects(
                    config.get("feed_path", "/blog/feed.xml"),
                )
            )

        # Admin redirects
        if config.get("include_admin_redirects", True):
            all_redirects.extend(
                self.generate_wp_admin_redirects(
                    config.get("admin_path", "/admin"),
                )
            )

        # Detect conflicts
        seen_paths = {}
        for redirect in all_redirects:
            path = redirect.from_path
            if path in seen_paths:
                report.conflicts.append(
                    {
                        "path": path,
                        "redirect1": seen_paths[path].to_path,
                        "redirect2": redirect.to_path,
                    }
                )
            else:
                seen_paths[path] = redirect
                report.redirects.append(redirect)

        return report

    def _url_to_path(self, url: str) -> str | None:
        """Extract path from URL."""
        if not url:
            return None

        parsed = urlparse(url)
        path = parsed.path

        # Remove base path if present
        old_parsed = urlparse(self.old_base)
        if old_parsed.path and path.startswith(old_parsed.path):
            path = path[len(old_parsed.path) :]

        return path if path else "/"

    def export_nginx(self, redirects: list[Redirect]) -> str:
        """
        Export redirects as nginx configuration.

        Args:
            redirects: List of redirects

        Returns:
            nginx configuration string
        """
        lines = [
            "# Generated by Focomy WordPress Import",
            f"# Generated at: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]

        # Non-regex redirects first
        for r in redirects:
            if r.regex:
                continue

            if r.status_code == 410:
                lines.append(f"location = {r.from_path} {{ return 410; }}")
            else:
                lines.append(f"location = {r.from_path} {{ return {r.status_code} {r.to_path}; }}")

        lines.append("")
        lines.append("# Regex redirects")

        # Regex redirects
        for r in redirects:
            if not r.regex:
                continue

            if r.status_code == 410:
                lines.append(f"location ~ {r.from_path} {{ return 410; }}")
            else:
                lines.append(f"location ~ {r.from_path} {{ return {r.status_code} {r.to_path}; }}")

        return "\n".join(lines)

    def export_apache(self, redirects: list[Redirect]) -> str:
        """
        Export redirects as Apache .htaccess rules.

        Args:
            redirects: List of redirects

        Returns:
            .htaccess content string
        """
        lines = [
            "# Generated by Focomy WordPress Import",
            f"# Generated at: {datetime.now(timezone.utc).isoformat()}",
            "",
            "RewriteEngine On",
            "",
        ]

        # Non-regex redirects
        for r in redirects:
            if r.regex:
                continue

            if r.status_code == 410:
                lines.append(f"Redirect 410 {r.from_path}")
            else:
                lines.append(f"Redirect {r.status_code} {r.from_path} {r.to_path}")

        lines.append("")
        lines.append("# Regex redirects")

        # Regex redirects
        for r in redirects:
            if not r.regex:
                continue

            if r.status_code == 410:
                lines.append(f"RewriteRule {r.from_path} - [G]")
            else:
                lines.append(f"RewriteRule {r.from_path} {r.to_path} [R={r.status_code},L]")

        return "\n".join(lines)

    def export_json(self, redirects: list[Redirect]) -> str:
        """
        Export redirects as JSON.

        Args:
            redirects: List of redirects

        Returns:
            JSON string
        """
        import json

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "redirects": [
                {
                    "from": r.from_path,
                    "to": r.to_path,
                    "status": r.status_code,
                    "regex": r.regex,
                    "comment": r.comment,
                }
                for r in redirects
            ],
        }

        return json.dumps(data, indent=2, ensure_ascii=False)

    def export_yaml(self, redirects: list[Redirect]) -> str:
        """
        Export redirects as YAML (for Focomy config).

        Args:
            redirects: List of redirects

        Returns:
            YAML string
        """
        import yaml

        data = {
            "redirects": [
                {
                    "from": r.from_path,
                    "to": r.to_path,
                    "status": r.status_code,
                    **({"regex": True} if r.regex else {}),
                    **({"comment": r.comment} if r.comment else {}),
                }
                for r in redirects
            ],
        }

        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
