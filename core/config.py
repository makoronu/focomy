"""Configuration management."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class SiteConfig(BaseModel):
    name: str = "My Site"
    tagline: str = ""
    url: str = "http://localhost:8000"
    language: str = "ja"
    timezone: str = "Asia/Tokyo"


class AdminConfig(BaseModel):
    path: str = "/admin"
    per_page: int = 20


class ImageConfig(BaseModel):
    max_width: int = 1920
    max_height: int = 1920
    quality: int = 85
    format: str = "webp"


class CDNConfig(BaseModel):
    enabled: bool = False
    url: str = ""  # e.g., "https://cdn.example.com"
    upload_to_s3: bool = False
    s3_bucket: str = ""
    s3_region: str = "ap-northeast-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""


class MediaConfig(BaseModel):
    upload_dir: str = "uploads"
    max_size: int = 10485760
    allowed_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
    ]
    image: ImageConfig = ImageConfig()
    cdn: CDNConfig = CDNConfig()


class SecurityHeadersConfig(BaseModel):
    # HSTS settings
    hsts_enabled: bool = True
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False

    # Frame options
    frame_options: str = "SAMEORIGIN"  # DENY, SAMEORIGIN, or empty to disable

    # Content Security Policy
    csp_enabled: bool = True
    csp_report_only: bool = False

    # Permissions Policy
    permissions_policy_enabled: bool = True


class SecurityConfig(BaseModel):
    secret_key: str = "change-this-in-production"
    session_expire: int = 86400
    login_attempts: int = 5
    lockout_duration: int = 900
    password_min_length: int = 12
    headers: SecurityHeadersConfig = SecurityHeadersConfig()


class CORSConfig(BaseModel):
    """CORS configuration."""

    enabled: bool = True
    allow_origins: list[str] = ["*"]  # Use ["https://example.com"] in production
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]
    allow_credentials: bool = True
    max_age: int = 600  # Preflight cache in seconds


class RateLimitConfig(BaseModel):
    """API rate limiting configuration."""

    enabled: bool = True
    default_limit: str = "100/minute"  # Default rate limit
    login_limit: str = "5/minute"  # Stricter for login
    api_limit: str = "60/minute"  # For API endpoints
    admin_limit: str = "200/minute"  # More generous for admin
    storage_backend: str = "memory"  # "memory" or "redis"
    redis_url: str = ""


class OAuthConfig(BaseModel):
    google_client_id: str = ""
    google_client_secret: str = ""


class SEOConfig(BaseModel):
    title_separator: str = " | "
    default_description: str = ""
    default_og_image: str = ""


class FeaturesConfig(BaseModel):
    """Feature flags for phased stabilization."""

    # Phase 1: Core (always enabled)
    core: bool = True

    # Phase 2: Media
    media: bool = True

    # Phase 3: ACF Alternative
    acf_alternative: bool = False

    # Phase 4: Auxiliary features
    menu: bool = False
    widget: bool = False
    revision: bool = True
    preview: bool = False
    workflow: bool = False
    edit_lock: bool = False
    bulk: bool = False
    search: bool = True
    redirect: bool = False
    routing: bool = False
    audit: bool = True
    sentry: bool = False
    link_validator: bool = False

    # Phase 5: Extended features
    comment: bool = False
    form: bool = True
    api_auth: bool = False
    oauth: bool = False
    mail: bool = False
    invite: bool = False
    schedule: bool = False
    export: bool = False
    cleanup: bool = False
    i18n: bool = False

    # Phase 6: Plugin/Theme
    plugin: bool = False
    marketplace: bool = False
    theme_inheritance: bool = False
    update: bool = False
    deployment: bool = False

    # Phase 7: WordPress Import
    wordpress_import: bool = False


class MenuItemConfig(BaseModel):
    label: str
    url: str = "#"
    target: str = "_self"
    icon: str = ""
    children: list["MenuItemConfig"] = []


class MenusConfig(BaseModel):
    header: list[MenuItemConfig] = []
    footer: list[MenuItemConfig] = []
    sidebar: list[MenuItemConfig] = []


class ThemeConfig(BaseModel):
    active: str = "default"


def _get_base_dir() -> Path:
    """Get base directory - prefer cwd if config.yaml exists there."""
    cwd = Path.cwd()
    if (cwd / "config.yaml").exists():
        return cwd
    return Path(__file__).parent.parent


class Settings(BaseSettings):
    # Paths - config.yaml がある場所を基準にする
    base_dir: Path = _get_base_dir()
    database_url: str = "postgresql+asyncpg://focomy:focomy@localhost:5432/focomy"
    debug: bool = False

    # Config sections
    site: SiteConfig = SiteConfig()
    admin: AdminConfig = AdminConfig()
    media: MediaConfig = MediaConfig()
    security: SecurityConfig = SecurityConfig()
    cors: CORSConfig = CORSConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    seo: SEOConfig = SEOConfig()
    oauth: OAuthConfig = OAuthConfig()
    menus: MenusConfig = MenusConfig()
    theme: ThemeConfig = ThemeConfig()
    features: FeaturesConfig = FeaturesConfig()

    class Config:
        env_file = ".env"
        env_prefix = "FOCOMY_"


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load YAML config file."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        import sys
        print(f"\nError: Invalid YAML in {path}", file=sys.stderr)
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            print(f"  Line {mark.line + 1}, Column {mark.column + 1}", file=sys.stderr)
        if hasattr(e, 'problem'):
            print(f"  {e.problem}", file=sys.stderr)
        print("\nPlease fix config.yaml and try again.\n", file=sys.stderr)
        raise SystemExit(1)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    base_dir = _get_base_dir()
    config_path = base_dir / "config.yaml"

    yaml_config = load_yaml_config(config_path)

    settings = Settings()

    # Override with YAML config
    if "site" in yaml_config:
        settings.site = SiteConfig(**yaml_config["site"])
    if "admin" in yaml_config:
        settings.admin = AdminConfig(**yaml_config["admin"])
    if "media" in yaml_config:
        media_config = yaml_config["media"]
        if "image" in media_config:
            media_config["image"] = ImageConfig(**media_config["image"])
        if "cdn" in media_config:
            media_config["cdn"] = CDNConfig(**media_config["cdn"])
        settings.media = MediaConfig(**media_config)
    if "security" in yaml_config:
        settings.security = SecurityConfig(**yaml_config["security"])
    if "seo" in yaml_config:
        settings.seo = SEOConfig(**yaml_config["seo"])
    if "oauth" in yaml_config:
        settings.oauth = OAuthConfig(**yaml_config["oauth"])
    if "menus" in yaml_config:
        menus_config = yaml_config["menus"]
        parsed_menus = {}
        for location in ("header", "footer", "sidebar"):
            if location in menus_config:
                parsed_menus[location] = [_parse_menu_item(item) for item in menus_config[location]]
        settings.menus = MenusConfig(**parsed_menus)
    if "features" in yaml_config:
        settings.features = FeaturesConfig(**yaml_config["features"])
    if "theme" in yaml_config:
        settings.theme = ThemeConfig(**yaml_config["theme"])

    return settings


def _parse_menu_item(item: dict[str, Any]) -> MenuItemConfig:
    """Parse a menu item from YAML config."""
    children = []
    if "children" in item:
        children = [_parse_menu_item(c) for c in item["children"]]
    return MenuItemConfig(
        label=item.get("label", ""),
        url=item.get("url", "#"),
        target=item.get("target", "_self"),
        icon=item.get("icon", ""),
        children=children,
    )


settings = get_settings()
