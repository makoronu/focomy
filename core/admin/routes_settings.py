"""Admin settings routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from .helpers import templates, require_admin, get_context

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    category: str = "site",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Settings management page."""
    from ..services.settings import SettingsService

    settings_svc = SettingsService(db)

    # Get settings for the selected category
    settings_data = await settings_svc.get_by_category(category)

    # Define setting fields for each category
    setting_fields = {
        "site": [
            {"key": "name", "label": "サイト名", "type": "text"},
            {"key": "tagline", "label": "タグライン", "type": "text"},
            {"key": "url", "label": "サイトURL", "type": "url"},
            {"key": "language", "label": "言語", "type": "text"},
            {"key": "timezone", "label": "タイムゾーン", "type": "text"},
        ],
        "seo": [
            {
                "key": "title_separator",
                "label": "タイトル区切り",
                "type": "text",
                "placeholder": " | ",
            },
            {"key": "default_description", "label": "デフォルト説明文", "type": "textarea"},
            {"key": "default_og_image", "label": "デフォルトOG画像URL", "type": "url"},
            {"key": "og_site_name", "label": "OGサイト名", "type": "text"},
            {"key": "og_locale", "label": "OGロケール", "type": "text", "placeholder": "ja_JP"},
            {
                "key": "twitter_site",
                "label": "Twitter @ユーザー名",
                "type": "text",
                "placeholder": "@example",
            },
            {
                "key": "ga4_id",
                "label": "Google Analytics 4 ID",
                "type": "text",
                "placeholder": "G-XXXXXXXXXX",
            },
            {
                "key": "gtm_id",
                "label": "Google Tag Manager ID",
                "type": "text",
                "placeholder": "GTM-XXXXXXX",
            },
            {"key": "search_console_id", "label": "Search Console 認証メタ", "type": "text"},
            {"key": "bing_webmaster_id", "label": "Bing Webmaster 認証メタ", "type": "text"},
        ],
        "media": [
            {"key": "max_size", "label": "最大アップロードサイズ (bytes)", "type": "number"},
            {"key": "image_max_width", "label": "画像最大幅", "type": "number"},
            {"key": "image_max_height", "label": "画像最大高さ", "type": "number"},
            {"key": "image_quality", "label": "画像品質 (1-100)", "type": "number"},
            {"key": "image_format", "label": "画像フォーマット", "type": "text"},
        ],
        "security": [
            {"key": "session_expire", "label": "セッション有効期限 (秒)", "type": "number"},
            {"key": "login_attempts", "label": "最大ログイン試行回数", "type": "number"},
            {"key": "lockout_duration", "label": "ロックアウト時間 (秒)", "type": "number"},
            {"key": "password_min_length", "label": "パスワード最小長", "type": "number"},
        ],
        "headers": [
            {
                "key": "info",
                "label": "セキュリティヘッダー情報",
                "type": "info",
                "value": "以下のセキュリティヘッダーが自動的に適用されています",
            },
            {
                "key": "hsts",
                "label": "HSTS (HTTP Strict Transport Security)",
                "type": "readonly",
                "value": "有効 (本番環境のみ)",
            },
            {"key": "csp", "label": "Content-Security-Policy", "type": "readonly", "value": "有効"},
            {
                "key": "x_frame_options",
                "label": "X-Frame-Options",
                "type": "readonly",
                "value": "SAMEORIGIN",
            },
            {
                "key": "x_content_type",
                "label": "X-Content-Type-Options",
                "type": "readonly",
                "value": "nosniff",
            },
            {
                "key": "referrer_policy",
                "label": "Referrer-Policy",
                "type": "readonly",
                "value": "strict-origin-when-cross-origin",
            },
            {
                "key": "permissions_policy",
                "label": "Permissions-Policy",
                "type": "readonly",
                "value": "有効 (不要なAPIを無効化)",
            },
            {
                "key": "coop",
                "label": "Cross-Origin-Opener-Policy",
                "type": "readonly",
                "value": "same-origin",
            },
            {
                "key": "corp",
                "label": "Cross-Origin-Resource-Policy",
                "type": "readonly",
                "value": "same-origin",
            },
        ],
    }

    categories = [
        {"value": "site", "label": "サイト情報"},
        {"value": "seo", "label": "SEO"},
        {"value": "media", "label": "メディア"},
        {"value": "security", "label": "セキュリティ"},
        {"value": "headers", "label": "セキュリティヘッダー"},
    ]

    context = await get_context(request, db, current_user, "settings")
    context.update(
        {
            "settings": settings_data,
            "fields": setting_fields.get(category, []),
            "current_category": category,
            "categories": categories,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/settings.html", context)


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Save settings."""
    from ..services.settings import SettingsService

    settings_svc = SettingsService(db)
    entity_svc = EntityService(db)

    form_data = await request.form()
    category = form_data.get("category", "site")
    user_data = entity_svc.serialize(current_user)
    user_id = user_data.get("id")

    # Process each setting
    count = 0
    for key, value in form_data.items():
        if key in ("csrf_token", "category"):
            continue

        full_key = f"{category}.{key}"
        await settings_svc.set(full_key, value, category=category, user_id=user_id)
        count += 1

    return RedirectResponse(
        url=f"/admin/settings?category={category}&message={count}件の設定を保存しました",
        status_code=303,
    )
