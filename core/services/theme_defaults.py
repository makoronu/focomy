"""Default theme creation."""

from pathlib import Path

import yaml


def create_default_theme(themes_dir: Path, theme_config_class: type) -> object:
    """Create default theme if not exists.

    Args:
        themes_dir: Path to themes directory
        theme_config_class: ThemeConfig class to instantiate

    Returns:
        ThemeConfig instance for the default theme
    """
    default_dir = themes_dir / "default"
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

    return theme_config_class(config)
