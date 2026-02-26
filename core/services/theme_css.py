"""Theme CSS generation mixin."""

import re


BASE_CSS = """
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


class ThemeCSSMixin:
    """
    CSS generation mixin.

    Mixed into ThemeService to provide CSS variable generation
    and preview CSS functionality.
    """

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
        lines.append(BASE_CSS)

        # Add custom CSS (from customizations or theme default)
        custom_css = customizations.get("custom_css", theme.custom_css or "")
        if custom_css:
            lines.append("")
            lines.append("/* Custom CSS */")
            lines.append(custom_css)

        css = "\n".join(lines)
        return self._minify_css(css) if minify else css

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
