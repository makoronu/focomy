"""ThemeService - theme management and rendering."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import escape

from ..config import settings
from .assets import get_asset_url, get_static_url, get_upload_url


class ThemeConfig:
    """Theme configuration."""

    # Default values for CSS variables (used when theme.yaml is incomplete)
    DEFAULT_COLORS = {
        "primary": "#2563eb",
        "primary-hover": "#1d4ed8",
        "background": "#ffffff",
        "surface": "#f8fafc",
        "text": "#1e293b",
        "text-muted": "#64748b",
        "border": "#e2e8f0",
        "success": "#22c55e",
        "error": "#ef4444",
        "warning": "#f59e0b",
    }
    DEFAULT_FONTS = {
        "sans": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "serif": "Georgia, 'Times New Roman', serif",
        "mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
    }
    DEFAULT_SPACING = {
        "xs": "0.25rem",
        "sm": "0.5rem",
        "md": "1rem",
        "lg": "1.5rem",
        "xl": "2rem",
        "2xl": "3rem",
    }

    def __init__(self, data: dict):
        self.name = data.get("name", "default")
        self.label = data.get("label", "Default Theme")
        self.version = data.get("version", "1.0.0")
        self.author = data.get("author", "")
        self.description = data.get("description", "")
        self.preview = data.get("preview", "")

        # CSS variables (fallback to defaults if empty/missing)
        self.colors = data.get("colors") or self.DEFAULT_COLORS
        self.fonts = data.get("fonts") or self.DEFAULT_FONTS
        self.spacing = data.get("spacing") or self.DEFAULT_SPACING

        # Customization config
        self.config = data.get("config", {})

        # Widget areas and menu locations
        self.widget_areas = data.get("widget_areas", [])
        self.menu_locations = data.get("menu_locations", [])

        # Templates
        self.templates = data.get("templates", {})

        # Custom CSS
        self.custom_css = data.get("custom_css", "")


class ThemeService:
    """
    Theme management service.

    Features:
    - CSS variables from YAML config
    - Jinja2 template rendering
    - Template inheritance
    - Custom CSS injection
    """

    def __init__(self):
        self.themes_dir = settings.base_dir / "themes"
        self.themes_dir.mkdir(exist_ok=True)
        self._themes: dict[str, ThemeConfig] = {}
        self._current_theme: str = "default"
        self._env: Environment | None = None

    def _load_themes(self):
        """Load all theme configurations."""
        if self._themes:
            return

        for theme_dir in self.themes_dir.iterdir():
            if theme_dir.is_dir():
                config_path = theme_dir / "theme.yaml"
                if config_path.exists():
                    try:
                        with open(config_path, encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                            if data:
                                theme = ThemeConfig(data)
                                self._themes[theme.name] = theme
                    except Exception as e:
                        print(f"Error loading theme {theme_dir}: {e}")

        # Ensure default theme exists
        if "default" not in self._themes:
            self._create_default_theme()

    def _create_default_theme(self):
        """Create default theme if not exists."""
        default_dir = self.themes_dir / "default"
        default_dir.mkdir(exist_ok=True)

        # Create theme.yaml
        config = {
            "name": "default",
            "label": "Default Theme",
            "version": "1.0.0",
            "colors": {
                "primary": "#2563eb",
                "primary-hover": "#1d4ed8",
                "background": "#ffffff",
                "surface": "#f8fafc",
                "text": "#1e293b",
                "text-muted": "#64748b",
                "border": "#e2e8f0",
                "success": "#22c55e",
                "error": "#ef4444",
                "warning": "#f59e0b",
            },
            "fonts": {
                "sans": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                "serif": "Georgia, 'Times New Roman', serif",
                "mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
            },
            "spacing": {
                "xs": "0.25rem",
                "sm": "0.5rem",
                "md": "1rem",
                "lg": "1.5rem",
                "xl": "2rem",
                "2xl": "3rem",
            },
        }

        with open(default_dir / "theme.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        # Create templates directory
        (default_dir / "templates").mkdir(exist_ok=True)

        # Create base template
        base_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {% block meta %}{% endblock %}
    <title>{% block title %}{{ site_name }}{% endblock %}</title>
    <style>
        {{ theme_css }}
        {% block styles %}{% endblock %}
    </style>
</head>
<body>
    <header class="site-header">
        {% block header %}
        <div class="container">
            <a href="/" class="site-logo">{{ site_name }}</a>
            <nav class="site-nav">
                {% block nav %}{% endblock %}
            </nav>
        </div>
        {% endblock %}
    </header>

    <main class="site-main">
        {% block content %}{% endblock %}
    </main>

    <footer class="site-footer">
        {% block footer %}
        <div class="container">
            <p>&copy; {{ current_year }} {{ site_name }}</p>
        </div>
        {% endblock %}
    </footer>

    {% block scripts %}{% endblock %}
</body>
</html>
"""
        with open(default_dir / "templates" / "base.html", "w", encoding="utf-8") as f:
            f.write(base_template)

        # Create post template
        post_template = """{% extends "base.html" %}

{% block title %}{{ post.title }} - {{ site_name }}{% endblock %}

{% block meta %}
{{ seo_meta | safe }}
{% endblock %}

{% block content %}
<article class="post">
    <header class="post-header">
        <h1>{{ post.title }}</h1>
        <div class="post-meta">
            <time datetime="{{ post.created_at }}">{{ post.created_at[:10] }}</time>
        </div>
    </header>

    <div class="post-content">
        {{ post.body | render_blocks | safe }}
    </div>
</article>
{% endblock %}
"""
        with open(default_dir / "templates" / "post.html", "w", encoding="utf-8") as f:
            f.write(post_template)

        # Create index template
        index_template = """{% extends "base.html" %}

{% block title %}{{ site_name }}{% endblock %}

{% block content %}
<div class="posts-list">
    {% for post in posts %}
    <article class="post-card">
        <h2><a href="/{{ post.type }}/{{ post.slug }}">{{ post.title }}</a></h2>
        <p>{{ post.excerpt or (post.body | excerpt) }}</p>
        <time datetime="{{ post.created_at }}">{{ post.created_at[:10] }}</time>
    </article>
    {% else %}
    <p>No posts yet.</p>
    {% endfor %}
</div>
{% endblock %}
"""
        with open(default_dir / "templates" / "home.html", "w", encoding="utf-8") as f:
            f.write(index_template)

        # Create category template
        category_template = """{% extends "base.html" %}

{% block title %}{{ category.name }} - {{ site_name }}{% endblock %}

{% block content %}
<div class="category-page">
    <h1>{{ category.name }}</h1>
    {% if category.description %}
    <p class="category-description">{{ category.description }}</p>
    {% endif %}

    <div class="posts-list">
        {% for post in posts %}
        <article class="post-card">
            <h2><a href="/{{ post.type }}/{{ post.slug }}">{{ post.title }}</a></h2>
            <p>{{ post.excerpt or (post.body | excerpt) }}</p>
            <time datetime="{{ post.created_at }}">{{ post.created_at[:10] }}</time>
        </article>
        {% else %}
        <p>No posts in this category.</p>
        {% endfor %}
    </div>

    {% if total_pages > 1 %}
    <nav class="pagination">
        {% if page > 1 %}<a href="?page={{ page - 1 }}">&laquo; Prev</a>{% endif %}
        <span>Page {{ page }} of {{ total_pages }}</span>
        {% if page < total_pages %}<a href="?page={{ page + 1 }}">Next &raquo;</a>{% endif %}
    </nav>
    {% endif %}
</div>
{% endblock %}
"""
        with open(default_dir / "templates" / "category.html", "w", encoding="utf-8") as f:
            f.write(category_template)

        # Create archive template
        archive_template = """{% extends "base.html" %}

{% block title %}Archive: {{ year }}/{{ month }} - {{ site_name }}{% endblock %}

{% block content %}
<div class="archive-page">
    <h1>Archive: {{ year }}/{{ "%02d" | format(month) }}</h1>

    <div class="posts-list">
        {% for post in posts %}
        <article class="post-card">
            <h2><a href="/{{ post.type }}/{{ post.slug }}">{{ post.title }}</a></h2>
            <p>{{ post.excerpt or (post.body | excerpt) }}</p>
            <time datetime="{{ post.created_at }}">{{ post.created_at[:10] }}</time>
        </article>
        {% else %}
        <p>No posts in this period.</p>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""
        with open(default_dir / "templates" / "archive.html", "w", encoding="utf-8") as f:
            f.write(archive_template)

        # Create search template
        search_template = """{% extends "base.html" %}

{% block title %}Search{% if query %}: {{ query }}{% endif %} - {{ site_name }}{% endblock %}

{% block content %}
<div class="search-page">
    <h1>Search</h1>

    <form action="/search" method="get" class="search-form">
        <input type="text" name="q" value="{{ query }}" placeholder="Search...">
        <button type="submit">Search</button>
    </form>

    {% if query %}
    <p class="search-results-count">{{ total }} result{% if total != 1 %}s{% endif %} for "{{ query }}"</p>

    <div class="posts-list">
        {% for post in posts %}
        <article class="post-card">
            <h2><a href="/{{ post.type }}/{{ post.slug }}">{{ post.title }}</a></h2>
            <p>{{ post.excerpt or (post.body | excerpt) }}</p>
            <time datetime="{{ post.created_at }}">{{ post.created_at[:10] }}</time>
        </article>
        {% else %}
        <p>No results found.</p>
        {% endfor %}
    </div>

    {% if total_pages > 1 %}
    <nav class="pagination">
        {% if page > 1 %}<a href="?q={{ query }}&page={{ page - 1 }}">&laquo; Prev</a>{% endif %}
        <span>Page {{ page }} of {{ total_pages }}</span>
        {% if page < total_pages %}<a href="?q={{ query }}&page={{ page + 1 }}">Next &raquo;</a>{% endif %}
    </nav>
    {% endif %}
    {% endif %}
</div>
{% endblock %}
"""
        with open(default_dir / "templates" / "search.html", "w", encoding="utf-8") as f:
            f.write(search_template)

        self._themes["default"] = ThemeConfig(config)

    def get_theme(self, name: str = None) -> ThemeConfig | None:
        """Get theme configuration."""
        self._load_themes()
        name = name or self._current_theme
        return self._themes.get(name)

    def get_all_themes(self) -> dict[str, ThemeConfig]:
        """Get all themes."""
        self._load_themes()
        return self._themes.copy()

    def set_current_theme(self, name: str):
        """Set current theme."""
        self._load_themes()
        if name in self._themes:
            self._current_theme = name
            self._env = None  # Reset environment

    def _minify_css(self, css: str) -> str:
        """Minify CSS by removing unnecessary whitespace and comments."""
        import re

        # Remove comments
        css = re.sub(r"/\*[\s\S]*?\*/", "", css)
        # Remove newlines and extra spaces
        css = re.sub(r"\s+", " ", css)
        # Remove spaces around special characters
        css = re.sub(r"\s*([{};:,>+~])\s*", r"\1", css)
        # Remove trailing semicolons before closing braces
        css = re.sub(r";\s*}", "}", css)
        return css.strip()

    def get_css_variables(self, theme_name: str = None, minify: bool = True) -> str:
        """Generate CSS variables from theme config with customizations applied."""
        theme = self.get_theme(theme_name)
        if not theme:
            return ""

        # Get user customizations
        customizations = self.get_customizations(theme_name)

        lines = [":root {"]

        # Colors (with customization override)
        for name, default_value in theme.colors.items():
            value = customizations.get(f"color_{name}", default_value)
            lines.append(f"  --color-{name}: {value};")

        # Fonts (with customization override)
        for name, default_value in theme.fonts.items():
            value = customizations.get(f"font_{name}", default_value)
            lines.append(f"  --font-{name}: {value};")

        # Spacing (with customization override)
        for name, default_value in theme.spacing.items():
            value = customizations.get(f"space_{name}", default_value)
            lines.append(f"  --space-{name}: {value};")

        # Header/Background images
        header_image = customizations.get("header_image", "")
        background_image = customizations.get("background_image", "")
        if header_image:
            lines.append(f"  --header-image: url({header_image});")
        if background_image:
            lines.append(f"  --background-image: url({background_image});")

        lines.append("}")

        # Add base styles
        lines.append(
            """
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: var(--font-sans);
    background: var(--background-image, var(--color-background));
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    color: var(--color-text);
    line-height: 1.6;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 var(--space-lg);
}

.site-header {
    background: var(--header-image, var(--color-surface));
    background-size: cover;
    background-position: center;
    border-bottom: 1px solid var(--color-border);
    padding: var(--space-md) 0;
}

.site-header .container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.site-logo {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-primary);
    text-decoration: none;
}

.site-nav a {
    color: var(--color-text);
    text-decoration: none;
    margin-left: var(--space-lg);
}

.site-nav a:hover {
    color: var(--color-primary);
}

.site-main {
    padding: var(--space-2xl) 0;
}

.site-footer {
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
    padding: var(--space-lg) 0;
    color: var(--color-text-muted);
    text-align: center;
}

/* Post styles */
.post {
    max-width: 800px;
    margin: 0 auto;
}

.post-header {
    margin-bottom: var(--space-xl);
}

.post-header h1 {
    font-size: 2.5rem;
    margin-bottom: var(--space-sm);
}

.post-meta {
    color: var(--color-text-muted);
}

.post-content {
    font-size: 1.125rem;
}

.post-content p {
    margin-bottom: var(--space-md);
}

.post-content h1 { font-size: 2.25rem; margin-top: var(--space-2xl); margin-bottom: var(--space-lg); }
.post-content h2, .post-content h3 {
    margin-top: var(--space-xl);
    margin-bottom: var(--space-md);
}
.post-content h4 { font-size: 1.25rem; }
.post-content h5 { font-size: 1.125rem; color: var(--color-text-muted); }
.post-content h6 { font-size: 1rem; color: var(--color-text-muted); }

.post-content img {
    max-width: 100%;
    height: auto;
    border-radius: 0.5rem;
}

.post-content blockquote {
    border-left: 4px solid var(--color-primary);
    padding-left: var(--space-lg);
    margin: var(--space-lg) 0;
    font-style: italic;
    color: var(--color-text-muted);
}

.post-content pre {
    background: var(--color-surface);
    padding: var(--space-md);
    border-radius: 0.5rem;
    overflow-x: auto;
    font-family: var(--font-mono);
}

/* Post list styles */
.posts-list {
    max-width: 800px;
    margin: 0 auto;
}

.post-card {
    padding: var(--space-lg) 0;
    border-bottom: 1px solid var(--color-border);
}

.post-card h2 {
    font-size: 1.5rem;
    margin-bottom: var(--space-sm);
}

.post-card h2 a {
    color: var(--color-text);
    text-decoration: none;
}

.post-card h2 a:hover {
    color: var(--color-primary);
}

.post-card time {
    color: var(--color-text-muted);
    font-size: 0.875rem;
}

/* Checklist */
.checklist { list-style: none; padding: 0; }
.checklist-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0; }
.checklist-item input { width: 1.25rem; height: 1.25rem; }

/* Alert */
.alert { padding: 1rem 1.25rem; border-radius: 0.5rem; margin: 1rem 0; border-left: 4px solid; }
.alert--info { background: #eff6ff; border-color: #3b82f6; color: #1e40af; }
.alert--warning { background: #fffbeb; border-color: #f59e0b; color: #92400e; }
.alert--success { background: #f0fdf4; border-color: #22c55e; color: #166534; }
.alert--error { background: #fef2f2; border-color: #ef4444; color: #991b1b; }

/* Button */
.button-block { text-align: center; padding: 1rem 0; }
.btn { display: inline-block; padding: 0.75rem 2rem; border-radius: 0.5rem; text-decoration: none; font-weight: 600; }
.btn--primary { background: var(--color-primary); color: white; }
.btn--secondary { background: var(--color-surface); color: var(--color-text); border: 1px solid var(--color-border); }
.btn--outline { background: transparent; color: var(--color-primary); border: 2px solid var(--color-primary); }

/* Link card */
.linkcard { display: flex; gap: 1rem; border: 1px solid var(--color-border); border-radius: 0.5rem; padding: 1rem; text-decoration: none; color: inherit; margin: 1rem 0; }
.linkcard:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.linkcard__image { width: 120px; height: 80px; object-fit: cover; border-radius: 0.25rem; }
.linkcard__title { font-weight: 600; margin-bottom: 0.25rem; }
.linkcard__description { font-size: 0.875rem; color: var(--color-text-muted); }

/* Columns */
.columns { display: flex; gap: 1.5rem; margin: 1rem 0; }
.columns--2 .column { width: 50%; }
.columns--3 .column { width: 33.333%; }

/* Embed */
.embed { margin: 1.5rem 0; }
.embed iframe { border-radius: 0.5rem; }
.embed__caption { text-align: center; font-size: 0.875rem; color: var(--color-text-muted); margin-top: 0.5rem; }

/* Video embeds (YouTube, Vimeo, Twitch) - 16:9 aspect ratio */
.embed--youtube, .embed--vimeo, .embed--twitch { position: relative; padding-bottom: 56.25%; height: 0; }
.embed--youtube iframe, .embed--vimeo iframe, .embed--twitch iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }

/* Google Maps */
.embed--googleMaps iframe { width: 100%; height: 400px; border-radius: 0.5rem; }

/* Spotify */
.embed--spotify iframe { border-radius: 12px; }

/* SoundCloud */
.embed--soundcloud iframe { border-radius: 0.5rem; }

/* Social embeds */
.embed--twitter, .embed--instagram { max-width: 550px; margin-left: auto; margin-right: auto; }

/* Map */
.map { margin: 1.5rem 0; }
.map iframe { border-radius: 0.5rem; }
.map__caption { text-align: center; font-size: 0.875rem; color: var(--color-text-muted); margin-top: 0.5rem; }

/* Video */
.video { margin: 1.5rem 0; }
.video--youtube, .video--vimeo { position: relative; padding-bottom: 56.25%; height: 0; }
.video--youtube iframe, .video--vimeo iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 0.5rem; }
.video--native video { width: 100%; border-radius: 0.5rem; }
.video__caption { text-align: center; font-size: 0.875rem; color: var(--color-text-muted); margin-top: 0.5rem; }

/* Spacer */
.spacer { display: block; }

/* Group */
.group { border-radius: 0.5rem; margin: 1.5rem 0; }

/* Cover */
.cover { position: relative; display: flex; align-items: center; justify-content: center; background-size: cover; background-position: center; border-radius: 0.5rem; margin: 1.5rem 0; overflow: hidden; }
.cover__overlay { position: absolute; inset: 0; }
.cover__content { position: relative; z-index: 1; text-align: center; padding: 2rem; max-width: 80%; }
.cover__title { font-size: 2rem; font-weight: 700; color: white; margin: 0; }
.cover__subtitle { font-size: 1.25rem; color: rgba(255,255,255,0.9); margin-top: 0.5rem; }

/* Gallery */
.gallery { margin: 1.5rem 0; }
.gallery__grid { display: grid; gap: 0.5rem; }
.gallery--2 .gallery__grid { grid-template-columns: repeat(2, 1fr); }
.gallery--3 .gallery__grid { grid-template-columns: repeat(3, 1fr); }
.gallery--4 .gallery__grid { grid-template-columns: repeat(4, 1fr); }
.gallery__item { aspect-ratio: 1; overflow: hidden; border-radius: 0.5rem; }
.gallery__item img { width: 100%; height: 100%; object-fit: cover; }
.gallery__caption { text-align: center; font-size: 0.875rem; color: var(--color-text-muted); margin-top: 0.5rem; }
"""
        )

        # Add custom CSS (from customizations or theme default)
        custom_css = customizations.get("custom_css", theme.custom_css or "")
        if custom_css:
            lines.append("")
            lines.append("/* Custom CSS */")
            lines.append(custom_css)

        css = "\n".join(lines)
        return self._minify_css(css) if minify else css

    def get_template_env(self, theme_name: str = None) -> Environment:
        """Get Jinja2 environment for theme."""
        theme = self.get_theme(theme_name)
        active_theme = theme.name if theme else "default"

        # Use theme inheritance for template fallback
        from .theme_inheritance import ThemeInheritanceService

        inheritance_svc = ThemeInheritanceService(self.themes_dir)
        template_paths = inheritance_svc.get_template_paths(active_theme)

        # Package default theme takes priority (for pip upgrade compatibility)
        package_default = Path(__file__).parent.parent.parent / "themes" / "default" / "templates"
        if package_default.exists():
            # Remove site-local default if exists, package default takes priority
            site_default = self.themes_dir / "default" / "templates"
            template_paths = [p for p in template_paths if p != site_default]
            template_paths.insert(0, package_default)

        # Fallback if no paths found
        if not template_paths:
            template_paths = [package_default]

        env = Environment(
            loader=FileSystemLoader([str(p) for p in template_paths]),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add custom filters
        env.filters["render_blocks"] = self._render_blocks
        env.filters["excerpt"] = self._excerpt
        env.filters["asset_url"] = get_asset_url
        env.filters["upload_url"] = get_upload_url
        env.filters["static_url"] = get_static_url
        env.filters["date"] = self._date_filter

        # Add global functions
        env.globals["asset_url"] = get_asset_url
        env.globals["upload_url"] = get_upload_url
        env.globals["static_url"] = get_static_url
        env.globals["now"] = datetime.now

        return env

    def _date_filter(self, value: Any, format: str = "%Y-%m-%d") -> str:
        """Format date/datetime value."""
        if value is None:
            return ""
        if isinstance(value, str):
            # Try to parse ISO format string
            try:
                from datetime import datetime
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return value[:10] if len(value) >= 10 else value
        if hasattr(value, "strftime"):
            return value.strftime(format)
        return str(value)

    def _excerpt(self, content: Any, length: int = 200) -> str:
        """Extract plain text excerpt from content."""
        if not content:
            return ""

        text = ""

        # Handle dict (Editor.js blocks)
        if isinstance(content, dict) and "blocks" in content:
            texts = []
            for block in content.get("blocks", []):
                if block.get("type") in ("paragraph", "header"):
                    block_text = block.get("data", {}).get("text", "")
                    # Strip HTML tags
                    import re

                    block_text = re.sub(r"<[^>]+>", "", block_text)
                    texts.append(block_text)
            text = " ".join(texts)
        elif isinstance(content, str):
            # Try parsing as JSON
            try:
                data = json.loads(content)
                return self._excerpt(data, length)
            except (json.JSONDecodeError, TypeError):
                import re

                text = re.sub(r"<[^>]+>", "", content)
        else:
            text = str(content)

        # Truncate
        if len(text) <= length:
            return text
        return text[: length - 3].rsplit(" ", 1)[0] + "..."

    def _sanitize_url(self, url: str) -> str:
        """Sanitize URL to prevent XSS via javascript: or data: URLs."""
        if not url:
            return ""
        url = url.strip()
        # Allow only safe protocols
        if url.startswith(("http://", "https://", "/", "./", "../")):
            return escape(url)
        # Block javascript:, data:, vbscript:, etc.
        return ""

    def _sanitize_html(self, html: str, allow_tags: set = None) -> str:
        """Sanitize HTML allowing only specific tags with safe style attributes."""
        if allow_tags is None:
            allow_tags = {"b", "i", "strong", "em", "a", "br", "u", "mark", "code", "s", "span"}

        import re
        # Safe CSS properties for inline styles
        safe_style_pattern = re.compile(
            r"^(color|background|background-color)\s*:\s*"
            r"(#[0-9a-fA-F]{3,6}|rgb\(\d{1,3},\s*\d{1,3},\s*\d{1,3}\)|[a-zA-Z]+)\s*;?\s*$"
        )

        def sanitize_style(style_value: str) -> str:
            """Validate and sanitize style attribute value."""
            if not style_value:
                return ""
            # Split by semicolon and validate each property
            safe_styles = []
            for prop in style_value.split(";"):
                prop = prop.strip()
                if prop and safe_style_pattern.match(prop):
                    safe_styles.append(prop)
            return "; ".join(safe_styles) if safe_styles else ""

        def replace_tag(match):
            full_tag = match.group(1)
            tag_name = full_tag.lower().split()[0]
            clean_tag = tag_name.lstrip("/")

            if clean_tag not in allow_tags:
                return escape(match.group(0))

            # For closing tags, return as-is
            if tag_name.startswith("/"):
                return match.group(0)

            # Extract and sanitize style attribute
            style_match = re.search(r'style\s*=\s*["\']([^"\']*)["\']', full_tag, re.I)
            if style_match and clean_tag in ("span", "mark"):
                safe_style = sanitize_style(style_match.group(1))
                if safe_style:
                    return f'<{clean_tag} style="{safe_style}">'
                return f"<{clean_tag}>"

            # For tags that shouldn't have style, strip attributes
            if clean_tag in ("span", "mark", "s"):
                return f"<{clean_tag}>"

            return match.group(0)

        return re.sub(r"<(/?\w+[^>]*)>", replace_tag, html)

    def _validate_color(self, color: str) -> str:
        """Validate hex color, return empty string if invalid."""
        import re
        if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
            return color
        return ""

    def _render_blocks(self, content: Any) -> str:
        """Render Editor.js blocks to HTML."""
        if not content:
            return ""

        data = content

        # Handle string content (possibly JSON)
        if isinstance(content, str):
            try:
                data = json.loads(content)
                # Handle double-encoded JSON (legacy data)
                if isinstance(data, str):
                    data = json.loads(data.replace("\\!", "!"))
            except json.JSONDecodeError:
                return content

        if not isinstance(data, dict) or "blocks" not in data:
            return str(content)

        html_parts = []
        for block in data.get("blocks", []):
            block_type = block.get("type")
            block_data = block.get("data", {})

            if block_type == "paragraph":
                text = self._sanitize_html(block_data.get("text", ""))
                tunes = block.get("tunes", {})
                alignment = tunes.get("alignmentTune", {}).get("alignment", "left")
                text_color = self._validate_color(
                    tunes.get("colorTune", {}).get("textColor", "")
                )
                bg_color = self._validate_color(
                    tunes.get("colorTune", {}).get("backgroundColor", "")
                )

                styles = []
                if alignment in ("center", "right"):
                    styles.append(f"text-align: {alignment}")
                if text_color:
                    styles.append(f"color: {text_color}")
                if bg_color:
                    styles.append(f"background: {bg_color}")
                    styles.append("padding: 1rem")
                    styles.append("border-radius: 0.5rem")

                style_attr = f' style="{"; ".join(styles)}"' if styles else ""
                html_parts.append(f"<p{style_attr}>{text}</p>")

            elif block_type == "header":
                level = int(block_data.get("level", 2))
                level = max(1, min(6, level))
                text = escape(block_data.get("text", ""))
                tunes = block.get("tunes", {})
                alignment = tunes.get("alignmentTune", {}).get("alignment", "left")
                text_color = self._validate_color(
                    tunes.get("colorTune", {}).get("textColor", "")
                )
                bg_color = self._validate_color(
                    tunes.get("colorTune", {}).get("backgroundColor", "")
                )

                styles = []
                if alignment in ("center", "right"):
                    styles.append(f"text-align: {alignment}")
                if text_color:
                    styles.append(f"color: {text_color}")
                if bg_color:
                    styles.append(f"background: {bg_color}")
                    styles.append("padding: 1rem")
                    styles.append("border-radius: 0.5rem")

                style_attr = f' style="{"; ".join(styles)}"' if styles else ""
                html_parts.append(f"<h{level}{style_attr}>{text}</h{level}>")

            elif block_type == "list":
                style = block_data.get("style", "unordered")
                tag = "ol" if style == "ordered" else "ul"
                items = block_data.get("items", [])
                items_html = "".join(f"<li>{item}</li>" for item in items)
                html_parts.append(f"<{tag}>{items_html}</{tag}>")

            elif block_type == "image":
                file_data = block_data.get("file", {})
                url = self._sanitize_url(file_data.get("url", ""))
                caption = escape(block_data.get("caption", ""))
                if url:
                    html_parts.append(
                        f'<figure><img src="{url}" alt="{caption}" loading="lazy"><figcaption>{caption}</figcaption></figure>'
                    )

            elif block_type == "quote":
                text = block_data.get("text", "")
                caption = block_data.get("caption", "")
                html_parts.append(f"<blockquote><p>{text}</p><cite>{caption}</cite></blockquote>")

            elif block_type == "code":
                code = escape(block_data.get("code", ""))
                html_parts.append(f"<pre><code>{code}</code></pre>")

            elif block_type == "delimiter":
                html_parts.append("<hr>")

            elif block_type == "table":
                content = block_data.get("content", [])
                rows = []
                for row in content:
                    cells = "".join(f"<td>{self._sanitize_html(cell)}</td>" for cell in row)
                    rows.append(f"<tr>{cells}</tr>")
                html_parts.append(f'<table>{"".join(rows)}</table>')

            elif block_type == "raw":
                # Sanitize raw HTML to prevent XSS
                from .sanitizer import sanitizer_service

                raw_html = block_data.get("html", "")
                html_parts.append(sanitizer_service.sanitize(raw_html))

            elif block_type == "embed":
                service = escape(block_data.get("service", ""))
                embed = self._sanitize_url(block_data.get("embed", ""))
                caption = escape(block_data.get("caption", ""))
                caption_html = (
                    f'<figcaption class="embed__caption">{caption}</figcaption>' if caption else ""
                )
                if not embed:
                    continue

                # サービスごとに最適なiframe設定
                if service == "youtube":
                    iframe = f'<iframe src="{embed}" width="100%" height="400" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
                elif service == "vimeo":
                    iframe = f'<iframe src="{embed}" width="100%" height="400" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>'
                elif service == "googleMaps":
                    iframe = f'<iframe src="{embed}" width="100%" height="400" style="border:0" allowfullscreen loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>'
                elif service == "spotify":
                    iframe = f'<iframe src="{embed}" width="100%" height="352" frameborder="0" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>'
                elif service == "soundcloud":
                    iframe = f'<iframe src="{embed}" width="100%" height="166" scrolling="no" frameborder="no" allow="autoplay"></iframe>'
                elif service == "twitter":
                    iframe = (
                        f'<iframe src="{embed}" width="100%" height="500" frameborder="0"></iframe>'
                    )
                elif service == "instagram":
                    iframe = f'<iframe src="{embed}" width="100%" height="600" frameborder="0" scrolling="no" allowtransparency="true"></iframe>'
                elif service == "twitch":
                    iframe = f'<iframe src="{embed}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>'
                else:
                    iframe = f'<iframe src="{embed}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>'

                html_parts.append(
                    f'<figure class="embed embed--{service}">{iframe}{caption_html}</figure>'
                )

            elif block_type == "checklist":
                items = block_data.get("items", [])
                items_html = []
                for item in items:
                    checked = "checked" if item.get("checked") else ""
                    text = self._sanitize_html(item.get("text", ""))
                    items_html.append(
                        f'<li class="checklist-item"><input type="checkbox" {checked} disabled><span>{text}</span></li>'
                    )
                html_parts.append(f'<ul class="checklist">{"".join(items_html)}</ul>')

            elif block_type == "alert":
                alert_type = escape(block_data.get("type", "info"))
                message = self._sanitize_html(block_data.get("message", ""))
                html_parts.append(f'<div class="alert alert--{alert_type}">{message}</div>')

            elif block_type == "button":
                text = escape(block_data.get("text", "ボタン"))
                url = self._sanitize_url(block_data.get("url", "#")) or "#"
                style = escape(block_data.get("style", "primary"))
                html_parts.append(
                    f'<div class="button-block"><a href="{url}" class="btn btn--{style}">{text}</a></div>'
                )

            elif block_type == "linkCard":
                url = self._sanitize_url(block_data.get("url", ""))
                title = escape(block_data.get("title", ""))
                description = escape(block_data.get("description", ""))
                image = self._sanitize_url(block_data.get("image", ""))
                img_html = f'<img src="{image}" alt="" class="linkcard__image">' if image else ""
                if url:
                    html_parts.append(
                        f"""<a href="{url}" class="linkcard" target="_blank" rel="noopener">
                        {img_html}
                        <div class="linkcard__content">
                            <div class="linkcard__title">{title}</div>
                            <div class="linkcard__description">{description}</div>
                        </div>
                    </a>"""
                    )

            elif block_type == "columns":
                cols = block_data.get("content", [])
                cols_html = "".join(
                    f'<div class="column">{self._sanitize_html(col)}</div>' for col in cols
                )
                html_parts.append(f'<div class="columns columns--{len(cols)}">{cols_html}</div>')

            elif block_type == "map":
                src = self._sanitize_url(block_data.get("src", ""))
                caption = escape(block_data.get("caption", ""))
                caption_html = (
                    f'<figcaption class="map__caption">{caption}</figcaption>' if caption else ""
                )
                if src:
                    html_parts.append(
                        f"""<figure class="map">
                        <iframe src="{src}" width="100%" height="400" style="border:0" allowfullscreen loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>
                        {caption_html}
                    </figure>"""
                    )

            elif block_type == "video":
                url = block_data.get("url", "")
                caption = escape(block_data.get("caption", ""))
                caption_html = (
                    f'<figcaption class="video__caption">{caption}</figcaption>' if caption else ""
                )

                # YouTube - extract video ID safely
                yt_match = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
                if yt_match:
                    video_id = escape(yt_match.group(1))
                    html_parts.append(
                        f"""<figure class="video video--youtube">
                        <iframe src="https://www.youtube.com/embed/{video_id}" width="100%" height="400" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
                        {caption_html}
                    </figure>"""
                    )
                    continue

                # Vimeo - extract video ID safely
                vimeo_match = re.search(r"vimeo\.com/(\d+)", url)
                if vimeo_match:
                    video_id = escape(vimeo_match.group(1))
                    html_parts.append(
                        f"""<figure class="video video--vimeo">
                        <iframe src="https://player.vimeo.com/video/{video_id}" width="100%" height="400" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
                        {caption_html}
                    </figure>"""
                    )
                    continue

                # Direct video (mp4, webm, ogg)
                safe_url = self._sanitize_url(url)
                if safe_url and re.search(r"\.(mp4|webm|ogg)(\?.*)?$", url, re.IGNORECASE):
                    html_parts.append(
                        f"""<figure class="video video--native">
                        <video src="{safe_url}" controls width="100%"></video>
                        {caption_html}
                    </figure>"""
                    )
                    continue

                # Generic iframe - only for safe URLs
                safe_url = self._sanitize_url(url)
                if safe_url:
                    html_parts.append(
                        f"""<figure class="video">
                        <iframe src="{safe_url}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>
                        {caption_html}
                    </figure>"""
                    )

            elif block_type == "spacer":
                height = int(block_data.get("height", 50))
                height = max(10, min(500, height))
                html_parts.append(
                    f'<div class="spacer" style="height: {height}px;" aria-hidden="true"></div>'
                )

            elif block_type == "group":
                content = self._sanitize_html(block_data.get("content", ""))
                bg_color = escape(block_data.get("backgroundColor", "#f8fafc"))
                padding = int(block_data.get("padding", 16))
                padding = max(0, min(100, padding))
                # Validate hex color
                import re
                if not re.match(r'^#[0-9a-fA-F]{6}$', bg_color):
                    bg_color = "#f8fafc"
                html_parts.append(
                    f'<div class="group" style="background: {bg_color}; padding: {padding}px;">{content}</div>'
                )

            elif block_type == "cover":
                image_url = self._sanitize_url(block_data.get("imageUrl", ""))
                title = self._sanitize_html(block_data.get("title", ""))
                subtitle = self._sanitize_html(block_data.get("subtitle", ""))
                overlay_color = escape(block_data.get("overlayColor", "#000000"))
                overlay_opacity = float(block_data.get("overlayOpacity", 0.5))
                height = int(block_data.get("height", 400))
                height = max(100, min(1000, height))
                overlay_opacity = max(0, min(1, overlay_opacity))
                # Validate hex color
                import re
                if not re.match(r'^#[0-9a-fA-F]{6}$', overlay_color):
                    overlay_color = "#000000"
                r = int(overlay_color[1:3], 16)
                g = int(overlay_color[3:5], 16)
                b = int(overlay_color[5:7], 16)
                overlay_rgba = f"rgba({r}, {g}, {b}, {overlay_opacity})"
                bg_style = f'background-image: url({image_url});' if image_url else 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);'
                subtitle_html = f'<p class="cover__subtitle">{subtitle}</p>' if subtitle else ""
                html_parts.append(
                    f'<section class="cover" style="min-height: {height}px; {bg_style}">'
                    f'<div class="cover__overlay" style="background: {overlay_rgba};"></div>'
                    f'<div class="cover__content">'
                    f'<h2 class="cover__title">{title}</h2>'
                    f'{subtitle_html}'
                    f'</div>'
                    f'</section>'
                )

            elif block_type == "gallery":
                images = block_data.get("images", [])
                columns = int(block_data.get("columns", 3))
                columns = max(2, min(4, columns))
                caption = escape(block_data.get("caption", ""))
                caption_html = f'<figcaption class="gallery__caption">{caption}</figcaption>' if caption else ""
                images_html = []
                for img in images:
                    url = self._sanitize_url(img.get("url", ""))
                    if url:
                        images_html.append(f'<div class="gallery__item"><img src="{url}" alt="" loading="lazy"></div>')
                if images_html:
                    html_parts.append(
                        f'<figure class="gallery gallery--{columns}">'
                        f'<div class="gallery__grid">{"".join(images_html)}</div>'
                        f'{caption_html}</figure>'
                    )

        return "\n".join(html_parts)

    def render_blocks_html(self, content: Any) -> str:
        """Render Editor.js blocks to HTML (public API for preview)."""
        return self._render_blocks(content)

    def render(
        self,
        template_name: str,
        context: dict[str, Any],
        theme_name: str = None,
    ) -> str:
        """Render a template with context."""
        from datetime import datetime

        env = self.get_template_env(theme_name)
        template = env.get_template(template_name)

        # Add theme CSS to context
        context["theme_css"] = self.get_css_variables(theme_name)
        context["customizations"] = self.get_customizations(theme_name)
        context["current_year"] = datetime.now().year
        context.setdefault("site_name", "Focomy")

        return template.render(**context)

    # === Customization Methods ===

    def get_customizations(self, theme_name: str = None) -> dict:
        """Get saved customizations for a theme.

        Args:
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            Dict of customization values
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return {}

        customizations_file = self.themes_dir / theme.name / "customizations.json"
        if customizations_file.exists():
            try:
                return json.loads(customizations_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def set_customizations(self, values: dict, theme_name: str = None) -> bool:
        """Save customizations for a theme.

        Args:
            values: Dict of customization values
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            True if saved successfully
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return False

        customizations_file = self.themes_dir / theme.name / "customizations.json"
        try:
            customizations_file.write_text(
                json.dumps(values, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            return True
        except Exception:
            return False

    def get_customizable_settings(self, theme_name: str = None) -> list[dict]:
        """Get list of customizable settings for a theme.

        Args:
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            List of setting definitions with current values
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return []

        customizations = self.get_customizations(theme_name)
        settings = []

        # Site Identity (logo, favicon)
        settings.append({
            "id": "site_logo",
            "type": "image",
            "label": "サイトロゴ",
            "category": "site_identity",
            "default": "",
            "value": customizations.get("site_logo", ""),
            "description": "ヘッダーに表示されるロゴ画像（推奨: 高さ60px以下）",
        })
        settings.append({
            "id": "site_icon",
            "type": "image",
            "label": "サイトアイコン",
            "category": "site_identity",
            "default": "",
            "value": customizations.get("site_icon", ""),
            "description": "ファビコン・アプリアイコン（推奨: 512x512px）",
        })

        # Header Images
        settings.append({
            "id": "header_image",
            "type": "image",
            "label": "ヘッダー画像",
            "category": "header",
            "default": "",
            "value": customizations.get("header_image", ""),
            "description": "ヘッダー背景画像（推奨: 1920x400px）",
        })
        settings.append({
            "id": "background_image",
            "type": "image",
            "label": "背景画像",
            "category": "header",
            "default": "",
            "value": customizations.get("background_image", ""),
            "description": "サイト全体の背景画像",
        })

        # Colors
        for name, default_value in theme.colors.items():
            settings.append({
                "id": f"color_{name}",
                "type": "color",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "colors",
                "default": default_value,
                "value": customizations.get(f"color_{name}", default_value),
            })

        # Fonts
        for name, default_value in theme.fonts.items():
            settings.append({
                "id": f"font_{name}",
                "type": "font",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "fonts",
                "default": default_value,
                "value": customizations.get(f"font_{name}", default_value),
            })

        # Spacing
        for name, default_value in theme.spacing.items():
            settings.append({
                "id": f"space_{name}",
                "type": "spacing",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "spacing",
                "default": default_value,
                "value": customizations.get(f"space_{name}", default_value),
            })

        # Custom CSS
        settings.append({
            "id": "custom_css",
            "type": "code",
            "label": "カスタムCSS",
            "category": "custom_css",
            "default": theme.custom_css or "",
            "value": customizations.get("custom_css", theme.custom_css or ""),
            "description": "独自のCSSを追加できます",
        })

        return settings

    def generate_preview_css(self, preview_values: dict, theme_name: str = None) -> str:
        """Generate CSS with preview values (not saved).

        Args:
            preview_values: Dict of values to override
            theme_name: Theme name

        Returns:
            CSS string with overrides applied
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return ""

        # Start with saved customizations
        values = self.get_customizations(theme_name)
        # Override with preview values
        values.update(preview_values)

        lines = [":root {"]

        # Colors - check for customization override
        for name, default_value in theme.colors.items():
            value = values.get(f"color_{name}", default_value)
            lines.append(f"  --color-{name}: {value};")

        # Fonts
        for name, default_value in theme.fonts.items():
            value = values.get(f"font_{name}", default_value)
            lines.append(f"  --font-{name}: {value};")

        # Spacing
        for name, default_value in theme.spacing.items():
            value = values.get(f"space_{name}", default_value)
            lines.append(f"  --space-{name}: {value};")

        # Header/Background images
        header_image = values.get("header_image", "")
        background_image = values.get("background_image", "")
        if header_image:
            lines.append(f"  --header-image: url({header_image});")
        if background_image:
            lines.append(f"  --background-image: url({background_image});")

        lines.append("}")

        # Custom CSS
        custom_css = values.get("custom_css", "")
        if custom_css:
            lines.append("")
            lines.append("/* Custom CSS */")
            lines.append(custom_css)

        return "\n".join(lines)


# Singleton
theme_service = ThemeService()
