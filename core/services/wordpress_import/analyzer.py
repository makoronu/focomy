"""WordPress Analyzer - site analysis before import."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .wxr_parser import WXRData, WXRParser


@dataclass
class ContentStats:
    """Content statistics."""

    total: int = 0
    published: int = 0
    draft: int = 0
    private: int = 0
    pending: int = 0
    trash: int = 0


@dataclass
class TaxonomyStats:
    """Taxonomy statistics."""

    name: str
    slug: str
    count: int
    max_depth: int = 0


@dataclass
class PostTypeStats:
    """Custom post type statistics."""

    name: str
    count: int
    fields: list[str] = field(default_factory=list)


@dataclass
class PluginInfo:
    """Detected plugin information."""

    name: str
    slug: str
    detected_by: str  # How it was detected
    data_count: int = 0


@dataclass
class CustomFieldAnalysis:
    """Custom field analysis."""

    key: str
    count: int
    sample_values: list[Any]
    inferred_type: str
    is_acf: bool = False
    acf_field_key: str | None = None
    post_types: list[str] = field(default_factory=list)


@dataclass
class ShortcodeAnalysis:
    """Shortcode analysis."""

    name: str
    count: int
    sample_usages: list[str]
    conversion_status: str  # supported, partial, placeholder, unsupported
    conversion_notes: str = ""


@dataclass
class MediaStats:
    """Media statistics."""

    total_count: int = 0
    total_size: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    missing_alt: int = 0
    external_urls: list[str] = field(default_factory=list)


@dataclass
class AnalysisWarning:
    """Analysis warning."""

    code: str
    message: str
    details: str = ""
    count: int = 1


@dataclass
class AnalysisReport:
    """Complete analysis report."""

    # Site info
    site_url: str = ""
    site_name: str = ""
    wp_version: str = ""
    language: str = ""

    # Content stats
    posts: ContentStats = field(default_factory=ContentStats)
    pages: ContentStats = field(default_factory=ContentStats)
    attachments: ContentStats = field(default_factory=ContentStats)
    comments_count: int = 0
    users_count: int = 0
    revisions_count: int = 0

    # Taxonomies
    categories: list[TaxonomyStats] = field(default_factory=list)
    tags: list[TaxonomyStats] = field(default_factory=list)
    custom_taxonomies: list[TaxonomyStats] = field(default_factory=list)

    # Custom post types
    custom_post_types: list[PostTypeStats] = field(default_factory=list)

    # Plugins
    detected_plugins: list[PluginInfo] = field(default_factory=list)

    # Custom fields
    custom_fields: list[CustomFieldAnalysis] = field(default_factory=list)

    # Shortcodes
    shortcodes: list[ShortcodeAnalysis] = field(default_factory=list)

    # Media
    media_stats: MediaStats = field(default_factory=MediaStats)

    # URL structure
    permalink_structure: str = ""
    required_redirects: int = 0

    # Menus
    menus_count: int = 0
    menu_items_count: int = 0

    # Warnings
    warnings: list[AnalysisWarning] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Estimates
    estimated_time: str = ""
    estimated_storage: str = ""


class WordPressAnalyzer:
    """
    WordPress site analyzer.

    Analyzes WXR export files to provide detailed reports
    and recommendations before import.
    """

    # Known shortcodes and their conversion status
    SHORTCODE_SUPPORT = {
        # Fully supported
        "gallery": ("supported", "Converted to gallery block"),
        "caption": ("supported", "Converted to image with caption"),
        "video": ("supported", "Converted to video block"),
        "audio": ("supported", "Converted to audio block"),
        "embed": ("supported", "Converted to embed block"),
        # Partially supported
        "youtube": ("partial", "Converted to embed, some options may be lost"),
        "vimeo": ("partial", "Converted to embed"),
        "twitter": ("partial", "Converted to embed"),
        # Placeholders
        "contact-form-7": ("placeholder", "Form placeholder created"),
        "gravityform": ("placeholder", "Form placeholder created"),
        "wpforms": ("placeholder", "Form placeholder created"),
        # Unsupported
        "vc_row": ("unsupported", "Visual Composer - needs manual conversion"),
        "vc_column": ("unsupported", "Visual Composer - needs manual conversion"),
        "et_pb_section": ("unsupported", "Divi - needs manual conversion"),
        "elementor": ("unsupported", "Elementor - HTML preserved"),
    }

    def __init__(self):
        self.parser = WXRParser()

    def analyze(self, file_path: Path) -> AnalysisReport:
        """
        Analyze a WXR file.

        Args:
            file_path: Path to WXR export file

        Returns:
            AnalysisReport with complete analysis
        """
        data = self.parser.parse(file_path)
        return self.analyze_data(data)

    def analyze_data(self, data: WXRData) -> AnalysisReport:
        """
        Analyze WXR data directly.

        Args:
            data: WXRData object

        Returns:
            AnalysisReport with complete analysis
        """
        report = AnalysisReport()

        # Site info
        report.site_url = data.site.link
        report.site_name = data.site.title
        report.language = data.site.language
        report.wp_version = self._extract_wp_version(data.site.wp_version)

        # Users
        report.users_count = len(data.authors)

        # Content stats
        self._analyze_content(data, report)

        # Taxonomies
        self._analyze_taxonomies(data, report)

        # Custom post types
        self._analyze_custom_post_types(data, report)

        # Custom fields
        self._analyze_custom_fields(data, report)

        # Shortcodes
        self._analyze_shortcodes(data, report)

        # Plugins
        self._detect_plugins(data, report)

        # Media
        self._analyze_media(data, report)

        # Menus
        report.menus_count = len(data.menus)
        report.menu_items_count = sum(len(items) for items in data.menus.values())

        # Comments
        report.comments_count = sum(len(p.comments) for p in data.posts)

        # Estimates
        self._calculate_estimates(report)

        # Recommendations
        self._generate_recommendations(report)

        return report

    def _extract_wp_version(self, generator: str) -> str:
        """Extract WordPress version from generator string."""
        match = re.search(r"WordPress (\d+\.\d+(?:\.\d+)?)", generator)
        if match:
            return match.group(1)
        return ""

    def _analyze_content(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze content statistics."""
        for post in data.posts:
            stats = None

            if post.post_type == "post":
                stats = report.posts
            elif post.post_type == "page":
                stats = report.pages
            elif post.post_type == "attachment":
                stats = report.attachments
            elif post.post_type == "revision":
                report.revisions_count += 1
                continue

            if stats:
                stats.total += 1
                if post.status == "publish":
                    stats.published += 1
                elif post.status == "draft":
                    stats.draft += 1
                elif post.status == "private":
                    stats.private += 1
                elif post.status == "pending":
                    stats.pending += 1
                elif post.status == "trash":
                    stats.trash += 1

    def _analyze_taxonomies(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze taxonomy statistics."""
        # Categories
        cat_counts = {}
        for post in data.posts:
            for cat in post.categories:
                slug = cat.get("slug", "")
                cat_counts[slug] = cat_counts.get(slug, 0) + 1

        for term in data.categories:
            report.categories.append(
                TaxonomyStats(
                    name=term.name,
                    slug=term.slug,
                    count=cat_counts.get(term.slug, 0),
                )
            )

        # Tags
        tag_counts = {}
        for post in data.posts:
            for tag in post.tags:
                slug = tag.get("slug", "")
                tag_counts[slug] = tag_counts.get(slug, 0) + 1

        for term in data.tags:
            report.tags.append(
                TaxonomyStats(
                    name=term.name,
                    slug=term.slug,
                    count=tag_counts.get(term.slug, 0),
                )
            )

        # Custom taxonomies
        taxonomy_counts: dict[str, dict[str, int]] = {}
        for post in data.posts:
            for tax in post.custom_taxonomies:
                tax_name = tax.get("taxonomy", "")
                slug = tax.get("slug", "")
                if tax_name not in taxonomy_counts:
                    taxonomy_counts[tax_name] = {}
                taxonomy_counts[tax_name][slug] = taxonomy_counts[tax_name].get(slug, 0) + 1

        for tax_name, terms in taxonomy_counts.items():
            total = sum(terms.values())
            report.custom_taxonomies.append(
                TaxonomyStats(
                    name=tax_name,
                    slug=tax_name,
                    count=total,
                )
            )

    def _analyze_custom_post_types(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze custom post types."""
        post_type_counts: dict[str, int] = {}
        post_type_fields: dict[str, set[str]] = {}

        for post in data.posts:
            pt = post.post_type
            if pt in ("post", "page", "attachment", "revision", "nav_menu_item"):
                continue

            post_type_counts[pt] = post_type_counts.get(pt, 0) + 1

            if pt not in post_type_fields:
                post_type_fields[pt] = set()

            for key in post.postmeta.keys():
                if not key.startswith("_"):  # Skip internal fields
                    post_type_fields[pt].add(key)

        for pt, count in post_type_counts.items():
            report.custom_post_types.append(
                PostTypeStats(
                    name=pt,
                    count=count,
                    fields=list(post_type_fields.get(pt, [])),
                )
            )

    def _analyze_custom_fields(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze custom fields and infer types."""
        field_data: dict[str, dict] = {}

        for post in data.posts:
            for key, value in post.postmeta.items():
                # Skip WordPress internal fields
                if key.startswith("_wp_") or key.startswith("_edit_"):
                    continue
                # Skip ACF internal
                if key.startswith("_") and not key.startswith("_thumbnail"):
                    continue

                if key not in field_data:
                    field_data[key] = {
                        "count": 0,
                        "samples": [],
                        "post_types": set(),
                    }

                field_data[key]["count"] += 1
                field_data[key]["post_types"].add(post.post_type)

                if len(field_data[key]["samples"]) < 5:
                    field_data[key]["samples"].append(value)

        for key, data in field_data.items():
            inferred_type = self._infer_field_type(data["samples"])
            is_acf = (
                any(f"_{key}" in p.postmeta for p in data.posts if hasattr(p, "postmeta"))
                if hasattr(data, "posts")
                else False
            )

            report.custom_fields.append(
                CustomFieldAnalysis(
                    key=key,
                    count=data["count"],
                    sample_values=data["samples"][:3],
                    inferred_type=inferred_type,
                    is_acf=is_acf,
                    post_types=list(data["post_types"]),
                )
            )

    def _infer_field_type(self, samples: list[Any]) -> str:
        """Infer field type from sample values."""
        if not samples:
            return "string"

        # Filter empty
        non_empty = [s for s in samples if s]
        if not non_empty:
            return "string"

        # Check patterns
        all_numeric = all(str(s).isdigit() for s in non_empty)
        if all_numeric:
            return "number"

        all_float = all(self._is_float(s) for s in non_empty)
        if all_float:
            return "float"

        all_bool = all(
            str(s).lower() in ("true", "false", "1", "0", "yes", "no") for s in non_empty
        )
        if all_bool:
            return "boolean"

        all_url = all(str(s).startswith(("http://", "https://")) for s in non_empty)
        if all_url:
            return "url"

        all_email = all("@" in str(s) and "." in str(s) for s in non_empty)
        if all_email:
            return "email"

        # Check for serialized PHP
        if any(str(s).startswith(("a:", "s:", "O:")) for s in non_empty):
            return "json"

        # Long text
        if any(len(str(s)) > 500 for s in non_empty):
            return "text"

        return "string"

    def _is_float(self, value: Any) -> bool:
        """Check if value is a float."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    def _analyze_shortcodes(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze shortcodes in content."""
        shortcode_pattern = re.compile(
            r"\[([a-zA-Z0-9_-]+)(?:\s[^\]]*)?(?:\]|\].*?\[/\1\])", re.DOTALL
        )
        shortcode_counts: dict[str, list[str]] = {}

        for post in data.posts:
            content = post.content or ""
            matches = shortcode_pattern.findall(content)

            for match in matches:
                name = match.lower()
                if name not in shortcode_counts:
                    shortcode_counts[name] = []

                # Store sample (first 100 chars)
                sample_match = re.search(rf"\[{re.escape(match)}[^\]]*\]", content)
                if sample_match and len(shortcode_counts[name]) < 3:
                    shortcode_counts[name].append(sample_match.group()[:100])

        for name, samples in shortcode_counts.items():
            status, notes = self.SHORTCODE_SUPPORT.get(
                name, ("unsupported", "Unknown shortcode - will be preserved as text")
            )

            report.shortcodes.append(
                ShortcodeAnalysis(
                    name=name,
                    count=len(samples),
                    sample_usages=samples,
                    conversion_status=status,
                    conversion_notes=notes,
                )
            )

    def _detect_plugins(self, data: WXRData, report: AnalysisReport) -> None:
        """Detect WordPress plugins from data patterns."""
        plugin_indicators = {
            "yoast_seo": {
                "keys": ["_yoast_wpseo_title", "_yoast_wpseo_metadesc"],
                "name": "Yoast SEO",
            },
            "aioseo": {
                "keys": ["_aioseo_title", "_aioseo_description"],
                "name": "All in One SEO",
            },
            "rank_math": {
                "keys": ["rank_math_title", "rank_math_description"],
                "name": "Rank Math",
            },
            "acf": {
                "keys_pattern": r"^field_[a-f0-9]+$",
                "name": "Advanced Custom Fields",
            },
            "woocommerce": {
                "post_types": ["product", "shop_order"],
                "name": "WooCommerce",
            },
            "wpml": {
                "keys": ["_wpml_word_count", "_wpml_media_featured"],
                "name": "WPML",
            },
            "polylang": {
                "keys": ["_pll_strings_translations"],
                "name": "Polylang",
            },
        }

        detected = set()

        for post in data.posts:
            for plugin_slug, config in plugin_indicators.items():
                if plugin_slug in detected:
                    continue

                # Check keys
                if "keys" in config:
                    for key in config["keys"]:
                        if key in post.postmeta:
                            detected.add(plugin_slug)
                            report.detected_plugins.append(
                                PluginInfo(
                                    name=config["name"],
                                    slug=plugin_slug,
                                    detected_by=f"meta key: {key}",
                                )
                            )
                            break

                # Check post types
                if "post_types" in config:
                    if post.post_type in config["post_types"]:
                        detected.add(plugin_slug)
                        report.detected_plugins.append(
                            PluginInfo(
                                name=config["name"],
                                slug=plugin_slug,
                                detected_by=f"post type: {post.post_type}",
                            )
                        )

    def _analyze_media(self, data: WXRData, report: AnalysisReport) -> None:
        """Analyze media attachments."""
        for post in data.posts:
            if post.post_type != "attachment":
                continue

            report.media_stats.total_count += 1

            # Get MIME type
            mime_type = post.postmeta.get("_wp_attachment_metadata", "")
            if mime_type:
                # Count by type
                main_type = "other"
                if "image" in str(mime_type):
                    main_type = "image"
                elif "video" in str(mime_type):
                    main_type = "video"
                elif "audio" in str(mime_type):
                    main_type = "audio"
                elif "pdf" in str(mime_type):
                    main_type = "pdf"

                report.media_stats.by_type[main_type] = (
                    report.media_stats.by_type.get(main_type, 0) + 1
                )

            # Check for missing alt
            if not post.postmeta.get("_wp_attachment_image_alt"):
                report.media_stats.missing_alt += 1

            # Check for external URLs
            guid = post.guid
            if guid and not guid.startswith(data.site.base_site_url):
                report.media_stats.external_urls.append(guid)

    def _calculate_estimates(self, report: AnalysisReport) -> None:
        """Calculate time and storage estimates."""
        total_items = (
            report.posts.total
            + report.pages.total
            + report.attachments.total
            + report.comments_count
        )

        # Rough estimate: 100 items per minute
        minutes = total_items / 100
        if minutes < 1:
            report.estimated_time = "Less than 1 minute"
        elif minutes < 60:
            report.estimated_time = f"About {int(minutes)} minutes"
        else:
            hours = minutes / 60
            report.estimated_time = f"About {hours:.1f} hours"

        # Storage estimate (very rough)
        mb = total_items * 0.01  # 10KB per item average
        if report.media_stats.total_count > 0:
            mb += report.media_stats.total_count * 0.5  # 500KB per media average

        if mb < 1:
            report.estimated_storage = "Less than 1 MB"
        elif mb < 1000:
            report.estimated_storage = f"About {int(mb)} MB"
        else:
            report.estimated_storage = f"About {mb/1000:.1f} GB"

    def _generate_recommendations(self, report: AnalysisReport) -> None:
        """Generate recommendations based on analysis."""
        # Large media library
        if report.media_stats.total_count > 1000:
            report.recommendations.append(
                "Large media library detected. Consider running media import in batches."
            )

        # Missing alt text
        if report.media_stats.missing_alt > 100:
            report.recommendations.append(
                f"{report.media_stats.missing_alt} images are missing alt text. "
                "Consider adding alt text for accessibility and SEO."
            )

        # Unsupported shortcodes
        unsupported = [s for s in report.shortcodes if s.conversion_status == "unsupported"]
        if unsupported:
            report.recommendations.append(
                f"{len(unsupported)} unsupported shortcodes detected. "
                "Manual conversion may be required after import."
            )
            report.warnings.append(
                AnalysisWarning(
                    code="UNSUPPORTED_SHORTCODES",
                    message=f"{len(unsupported)} unsupported shortcodes",
                    details=", ".join(s.name for s in unsupported),
                )
            )

        # Custom post types
        if report.custom_post_types:
            report.recommendations.append(
                f"{len(report.custom_post_types)} custom post types will be created. "
                "Review the generated content type definitions after import."
            )

        # Many revisions
        if report.revisions_count > 1000:
            report.recommendations.append(
                f"{report.revisions_count} revisions found. "
                "Consider skipping revisions to speed up import."
            )

        # External media
        if report.media_stats.external_urls:
            report.warnings.append(
                AnalysisWarning(
                    code="EXTERNAL_MEDIA",
                    message=f"{len(report.media_stats.external_urls)} external media URLs",
                    details="These files are hosted externally and won't be imported",
                )
            )
