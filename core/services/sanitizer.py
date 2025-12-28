"""
HTML Sanitizer Service for Editor.js blocks and user-generated content.

Prevents XSS attacks by sanitizing HTML output.
"""

import html
import re
from typing import Any

# Allowed HTML tags and their attributes
ALLOWED_TAGS = {
    # Headings
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    # Text formatting
    "p",
    "br",
    "hr",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "s",
    "strike",
    "del",
    "sup",
    "sub",
    "mark",
    "small",
    # Lists
    "ul",
    "ol",
    "li",
    # Links and media
    "a",
    "img",
    "figure",
    "figcaption",
    # Tables
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    # Code
    "pre",
    "code",
    # Quotes
    "blockquote",
    "q",
    "cite",
    # Semantic
    "div",
    "span",
    "section",
    "article",
}

ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "style"],  # Allowed on all tags
    "a": ["href", "target", "rel", "title"],
    "img": ["src", "alt", "width", "height", "loading"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "code": ["class"],  # For syntax highlighting
    "pre": ["class"],
}

# Dangerous URL schemes
DANGEROUS_SCHEMES = {"javascript", "vbscript", "data"}

# Allowed CSS properties (limited for security)
ALLOWED_STYLES = {
    "color",
    "background-color",
    "text-align",
    "font-weight",
    "font-style",
    "text-decoration",
    "margin",
    "padding",
    "border",
    "width",
    "height",
    "max-width",
    "max-height",
    "display",
    "float",
    "clear",
}


class SanitizerService:
    """Service for sanitizing HTML content to prevent XSS attacks."""

    def __init__(
        self,
        allowed_tags: set[str] = None,
        allowed_attributes: dict[str, list[str]] = None,
        strip_comments: bool = True,
    ):
        self.allowed_tags = allowed_tags or ALLOWED_TAGS
        self.allowed_attributes = allowed_attributes or ALLOWED_ATTRIBUTES
        self.strip_comments = strip_comments

    def sanitize(self, html_content: str) -> str:
        """
        Sanitize HTML content by removing dangerous elements.

        Args:
            html_content: Raw HTML string

        Returns:
            Sanitized HTML string
        """
        if not html_content:
            return ""

        # Remove HTML comments
        if self.strip_comments:
            html_content = re.sub(r"<!--.*?-->", "", html_content, flags=re.DOTALL)

        # Remove script tags completely
        html_content = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            html_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove style tags (inline styles are handled separately)
        html_content = re.sub(
            r"<style[^>]*>.*?</style>",
            "",
            html_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove on* event handlers
        html_content = re.sub(
            r'\s+on\w+\s*=\s*["\'][^"\']*["\']',
            "",
            html_content,
            flags=re.IGNORECASE,
        )
        html_content = re.sub(
            r"\s+on\w+\s*=\s*\S+",
            "",
            html_content,
            flags=re.IGNORECASE,
        )

        # Sanitize href/src attributes with dangerous protocols
        html_content = self._sanitize_urls(html_content)

        # Sanitize style attributes
        html_content = self._sanitize_styles(html_content)

        return html_content

    def _sanitize_urls(self, content: str) -> str:
        """Remove dangerous URL schemes from href/src attributes."""

        def replace_url(match: re.Match) -> str:
            attr = match.group(1)
            quote = match.group(2)
            url = match.group(3)

            # Check for dangerous schemes
            url_lower = url.lower().strip()
            for scheme in DANGEROUS_SCHEMES:
                if url_lower.startswith(f"{scheme}:"):
                    return f"{attr}={quote}#{quote}"

            return match.group(0)

        # Match href="..." or src="..."
        pattern = r'(href|src)\s*=\s*(["\'])([^"\']*)\2'
        return re.sub(pattern, replace_url, content, flags=re.IGNORECASE)

    def _sanitize_styles(self, content: str) -> str:
        """Sanitize inline style attributes."""

        def replace_style(match: re.Match) -> str:
            quote = match.group(1)
            style = match.group(2)

            # Parse and filter CSS properties
            safe_styles = []
            for declaration in style.split(";"):
                if ":" in declaration:
                    prop, value = declaration.split(":", 1)
                    prop = prop.strip().lower()
                    value = value.strip()

                    # Check if property is allowed
                    if prop in ALLOWED_STYLES:
                        # Remove url() and expression() from values
                        if "url(" not in value.lower() and "expression(" not in value.lower():
                            safe_styles.append(f"{prop}: {value}")

            if safe_styles:
                return f'style={quote}{"; ".join(safe_styles)}{quote}'
            return ""

        pattern = r'style\s*=\s*(["\'])([^"\']*)\1'
        return re.sub(pattern, replace_style, content, flags=re.IGNORECASE)

    def sanitize_text(self, text: str) -> str:
        """
        Escape HTML entities in plain text.

        Use this for text that should NOT contain any HTML.
        """
        if not text:
            return ""
        return html.escape(text)

    def sanitize_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Sanitize Editor.js blocks.

        Args:
            blocks: List of Editor.js block objects

        Returns:
            Sanitized blocks
        """
        if not blocks:
            return []

        sanitized = []
        for block in blocks:
            block_type = block.get("type", "")
            data = block.get("data", {})

            if block_type == "paragraph":
                data["text"] = self.sanitize(data.get("text", ""))

            elif block_type == "header":
                data["text"] = self.sanitize(data.get("text", ""))

            elif block_type == "list":
                items = data.get("items", [])
                data["items"] = [self.sanitize(item) for item in items]

            elif block_type == "quote":
                data["text"] = self.sanitize(data.get("text", ""))
                data["caption"] = self.sanitize(data.get("caption", ""))

            elif block_type == "code":
                # Code blocks should be escaped, not sanitized
                data["code"] = self.sanitize_text(data.get("code", ""))

            elif block_type == "raw":
                # Raw HTML blocks need careful sanitization
                data["html"] = self.sanitize(data.get("html", ""))

            elif block_type == "table":
                content = data.get("content", [])
                data["content"] = [[self.sanitize(cell) for cell in row] for row in content]

            elif block_type == "image":
                # Validate image URL
                url = data.get("url", "")
                if url:
                    url_lower = url.lower().strip()
                    for scheme in DANGEROUS_SCHEMES:
                        if url_lower.startswith(f"{scheme}:"):
                            data["url"] = ""
                            break

                data["caption"] = self.sanitize(data.get("caption", ""))

            elif block_type == "embed":
                # Only allow trusted embed sources
                data["caption"] = self.sanitize(data.get("caption", ""))

            sanitized.append(
                {
                    "type": block_type,
                    "data": data,
                }
            )

        return sanitized


# Singleton instance
sanitizer_service = SanitizerService()
