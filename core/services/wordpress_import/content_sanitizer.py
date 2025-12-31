"""Content Sanitizer - Remove dangerous HTML tags and attributes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from bs4.element import Tag

logger = logging.getLogger(__name__)


@dataclass
class SanitizeWarning:
    """Warning about sanitized content."""

    type: str  # dangerous_tag, dangerous_attr, suspicious_base64, javascript_url
    detail: str
    original: str


@dataclass
class SanitizeResult:
    """Result of content sanitization."""

    content: str
    warnings: list[SanitizeWarning] = field(default_factory=list)

    @property
    def had_issues(self) -> bool:
        """Check if any issues were found."""
        return len(self.warnings) > 0


class ContentSanitizer:
    """
    Sanitize HTML content for security.

    Removes dangerous tags (script, iframe, etc.) and attributes
    (onclick, onerror, etc.) to prevent XSS attacks.
    """

    # Tags that should be completely removed
    DANGEROUS_TAGS = frozenset([
        "script",
        "iframe",
        "object",
        "embed",
        "form",
        "applet",
        "meta",
        "link",
        "style",
        "base",
        "frame",
        "frameset",
        "noscript",
    ])

    # Attributes that should be removed (event handlers and dangerous attributes)
    DANGEROUS_ATTRS = frozenset([
        # Mouse events
        "onclick",
        "ondblclick",
        "onmousedown",
        "onmouseup",
        "onmouseover",
        "onmousemove",
        "onmouseout",
        "onmouseenter",
        "onmouseleave",
        # Keyboard events
        "onkeydown",
        "onkeypress",
        "onkeyup",
        # Form events
        "onsubmit",
        "onreset",
        "onchange",
        "oninput",
        "onfocus",
        "onblur",
        # Load events
        "onload",
        "onerror",
        "onunload",
        "onbeforeunload",
        "onabort",
        # Other events
        "onscroll",
        "onresize",
        "ondrag",
        "ondrop",
        "oncopy",
        "onpaste",
        "oncut",
        "oncontextmenu",
        "onauxclick",
        # Other dangerous attributes
        "formaction",
        "xlink:href",
        "xmlns",
    ])

    # Pattern for javascript: URLs
    JAVASCRIPT_URL_PATTERN = re.compile(
        r"^\s*javascript\s*:",
        re.IGNORECASE,
    )

    # Pattern for suspicious base64 data (potential malware)
    BASE64_PATTERN = re.compile(
        r"data:[^;]+;base64,[A-Za-z0-9+/=]{100,}",
    )

    # Suspicious keywords in base64 content that might indicate scripts
    SUSPICIOUS_BASE64_KEYWORDS = [
        b"<script",
        b"javascript:",
        b"eval(",
        b"document.cookie",
        b"document.write",
        b".innerHTML",
    ]

    def sanitize(self, content: str) -> SanitizeResult:
        """
        Sanitize HTML content.

        Args:
            content: HTML content to sanitize

        Returns:
            SanitizeResult with cleaned content and list of warnings
        """
        if not content:
            return SanitizeResult(content="")

        warnings: list[SanitizeWarning] = []

        try:
            soup = BeautifulSoup(content, "html.parser")

            # Remove dangerous tags
            self._remove_dangerous_tags(soup, warnings)

            # Remove dangerous attributes
            self._remove_dangerous_attributes(soup, warnings)

            # Remove javascript: URLs
            self._remove_javascript_urls(soup, warnings)

            # Check for suspicious base64 content
            self._check_suspicious_base64(soup, warnings)

            cleaned_content = str(soup)

            # Log warnings
            if warnings:
                logger.warning(
                    f"Content sanitized: {len(warnings)} issues found",
                    extra={"warnings": [w.type for w in warnings]},
                )
                for warning in warnings:
                    logger.warning(
                        f"  - [{warning.type}] {warning.detail}: {warning.original[:50]}..."
                    )

            return SanitizeResult(content=cleaned_content, warnings=warnings)

        except Exception as e:
            logger.error(f"Error sanitizing content: {e}")
            # Return original content on error to avoid data loss
            return SanitizeResult(content=content)

    def _remove_dangerous_tags(
        self, soup: BeautifulSoup, warnings: list[SanitizeWarning]
    ) -> None:
        """Remove dangerous HTML tags."""
        for tag_name in self.DANGEROUS_TAGS:
            for tag in soup.find_all(tag_name):
                original = str(tag)[:100]
                warnings.append(
                    SanitizeWarning(
                        type="dangerous_tag",
                        detail=f"Removed <{tag_name}> tag",
                        original=original,
                    )
                )
                tag.decompose()

    def _remove_dangerous_attributes(
        self, soup: BeautifulSoup, warnings: list[SanitizeWarning]
    ) -> None:
        """Remove dangerous HTML attributes."""
        for tag in soup.find_all():
            if not hasattr(tag, "attrs"):
                continue

            attrs_to_remove = []
            for attr in tag.attrs.keys():
                attr_lower = attr.lower()
                if attr_lower in self.DANGEROUS_ATTRS:
                    attrs_to_remove.append(attr)

            for attr in attrs_to_remove:
                original = f'{attr}="{str(tag.get(attr, ""))[:50]}"'
                warnings.append(
                    SanitizeWarning(
                        type="dangerous_attr",
                        detail=f"Removed {attr} attribute from <{tag.name}>",
                        original=original,
                    )
                )
                del tag[attr]

    def _remove_javascript_urls(
        self, soup: BeautifulSoup, warnings: list[SanitizeWarning]
    ) -> None:
        """Remove javascript: URLs from href and src attributes."""
        url_attrs = ["href", "src", "action", "data"]

        for tag in soup.find_all():
            if not hasattr(tag, "attrs"):
                continue

            for attr in url_attrs:
                value = tag.get(attr)
                if value and self.JAVASCRIPT_URL_PATTERN.match(str(value)):
                    original = f'{attr}="{str(value)[:50]}"'
                    warnings.append(
                        SanitizeWarning(
                            type="javascript_url",
                            detail=f"Removed javascript: URL from <{tag.name}> {attr}",
                            original=original,
                        )
                    )
                    del tag[attr]

    def _check_suspicious_base64(
        self, soup: BeautifulSoup, warnings: list[SanitizeWarning]
    ) -> None:
        """Check for suspicious base64 encoded content."""
        content_str = str(soup)

        for match in self.BASE64_PATTERN.finditer(content_str):
            base64_data = match.group()
            if self._is_suspicious_base64(base64_data):
                warnings.append(
                    SanitizeWarning(
                        type="suspicious_base64",
                        detail="Suspicious base64 encoded content detected",
                        original=base64_data[:50] + "...",
                    )
                )

    def _is_suspicious_base64(self, data: str) -> bool:
        """
        Check if base64 data contains suspicious content.

        Args:
            data: Base64 data URL string

        Returns:
            True if suspicious content is detected
        """
        import base64

        try:
            # Extract base64 portion
            if ";base64," in data:
                base64_part = data.split(";base64,")[1]
                # Add padding if needed
                padding = 4 - len(base64_part) % 4
                if padding != 4:
                    base64_part += "=" * padding

                decoded = base64.b64decode(base64_part)

                # Check for suspicious keywords
                for keyword in self.SUSPICIOUS_BASE64_KEYWORDS:
                    if keyword.lower() in decoded.lower():
                        return True

        except Exception:
            # If we can't decode it, that's suspicious too
            pass

        return False


# Singleton instance for convenience
_sanitizer: ContentSanitizer | None = None


def get_sanitizer() -> ContentSanitizer:
    """Get the singleton ContentSanitizer instance."""
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = ContentSanitizer()
    return _sanitizer


def sanitize_content(content: str) -> SanitizeResult:
    """
    Convenience function to sanitize content.

    Args:
        content: HTML content to sanitize

    Returns:
        SanitizeResult with cleaned content and warnings
    """
    return get_sanitizer().sanitize(content)
