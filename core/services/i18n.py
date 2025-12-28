"""Internationalization (i18n) Service.

Provides multi-language support for:
- Admin UI translations
- Content translations
- Dynamic language switching
"""

import json
from pathlib import Path
from typing import Any

# Default translations (Japanese as primary)
DEFAULT_TRANSLATIONS = {
    "ja": {
        # Common
        "save": "保存",
        "cancel": "キャンセル",
        "delete": "削除",
        "edit": "編集",
        "create": "作成",
        "search": "検索",
        "filter": "フィルター",
        "actions": "操作",
        "confirm": "確認",
        "yes": "はい",
        "no": "いいえ",
        "loading": "読み込み中...",
        "error": "エラー",
        "success": "成功",
        "warning": "警告",
        # Auth
        "login": "ログイン",
        "logout": "ログアウト",
        "email": "メールアドレス",
        "password": "パスワード",
        "forgot_password": "パスワードを忘れた方",
        "reset_password": "パスワードリセット",
        "register": "登録",
        # Admin
        "dashboard": "ダッシュボード",
        "settings": "設定",
        "users": "ユーザー",
        "media": "メディア",
        "comments": "コメント",
        "trash": "ゴミ箱",
        "audit_log": "監査ログ",
        # Content
        "title": "タイトル",
        "slug": "スラッグ",
        "status": "ステータス",
        "draft": "下書き",
        "published": "公開",
        "scheduled": "予約投稿",
        "created_at": "作成日",
        "updated_at": "更新日",
        "author": "著者",
        "category": "カテゴリ",
        "tags": "タグ",
        # Messages
        "saved_successfully": "保存しました",
        "deleted_successfully": "削除しました",
        "error_occurred": "エラーが発生しました",
        "confirm_delete": "本当に削除しますか？",
        "no_results": "結果がありません",
        "required_field": "必須項目です",
        "invalid_email": "有効なメールアドレスを入力してください",
        "password_too_short": "パスワードは{min}文字以上必要です",
    },
    "en": {
        # Common
        "save": "Save",
        "cancel": "Cancel",
        "delete": "Delete",
        "edit": "Edit",
        "create": "Create",
        "search": "Search",
        "filter": "Filter",
        "actions": "Actions",
        "confirm": "Confirm",
        "yes": "Yes",
        "no": "No",
        "loading": "Loading...",
        "error": "Error",
        "success": "Success",
        "warning": "Warning",
        # Auth
        "login": "Login",
        "logout": "Logout",
        "email": "Email",
        "password": "Password",
        "forgot_password": "Forgot password?",
        "reset_password": "Reset Password",
        "register": "Register",
        # Admin
        "dashboard": "Dashboard",
        "settings": "Settings",
        "users": "Users",
        "media": "Media",
        "comments": "Comments",
        "trash": "Trash",
        "audit_log": "Audit Log",
        # Content
        "title": "Title",
        "slug": "Slug",
        "status": "Status",
        "draft": "Draft",
        "published": "Published",
        "scheduled": "Scheduled",
        "created_at": "Created",
        "updated_at": "Updated",
        "author": "Author",
        "category": "Category",
        "tags": "Tags",
        # Messages
        "saved_successfully": "Saved successfully",
        "deleted_successfully": "Deleted successfully",
        "error_occurred": "An error occurred",
        "confirm_delete": "Are you sure you want to delete?",
        "no_results": "No results found",
        "required_field": "This field is required",
        "invalid_email": "Please enter a valid email",
        "password_too_short": "Password must be at least {min} characters",
    },
}

# Supported languages
SUPPORTED_LANGUAGES = ["ja", "en"]
DEFAULT_LANGUAGE = "ja"


class I18nService:
    """
    Internationalization service.

    Usage:
        i18n = I18nService()

        # Get translation
        text = i18n.t("save")  # "保存" (default Japanese)
        text = i18n.t("save", lang="en")  # "Save"

        # With interpolation
        text = i18n.t("password_too_short", min=12)  # "パスワードは12文字以上必要です"

        # Set current language
        i18n.set_language("en")
    """

    def __init__(self, default_lang: str = DEFAULT_LANGUAGE):
        self._translations: dict[str, dict[str, str]] = DEFAULT_TRANSLATIONS.copy()
        self._current_lang = default_lang
        self._fallback_lang = DEFAULT_LANGUAGE

    @property
    def current_language(self) -> str:
        return self._current_lang

    @property
    def supported_languages(self) -> list[str]:
        return list(self._translations.keys())

    def set_language(self, lang: str) -> None:
        """Set current language."""
        if lang in self._translations:
            self._current_lang = lang

    def t(
        self,
        key: str,
        lang: str | None = None,
        **kwargs,
    ) -> str:
        """
        Get translated string.

        Args:
            key: Translation key
            lang: Language code (uses current if not specified)
            **kwargs: Interpolation values

        Returns:
            Translated string
        """
        lang = lang or self._current_lang

        # Try requested language
        translations = self._translations.get(lang, {})
        text = translations.get(key)

        # Fallback to default language
        if text is None and lang != self._fallback_lang:
            translations = self._translations.get(self._fallback_lang, {})
            text = translations.get(key)

        # If still not found, return key
        if text is None:
            return key

        # Interpolation
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass

        return text

    def add_translations(self, lang: str, translations: dict[str, str]) -> None:
        """Add or update translations for a language."""
        if lang not in self._translations:
            self._translations[lang] = {}
        self._translations[lang].update(translations)

    def load_translations_file(self, path: Path) -> None:
        """
        Load translations from a JSON file.

        File format:
        {
            "ja": {"key": "translation"},
            "en": {"key": "translation"}
        }
        """
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for lang, translations in data.items():
            self.add_translations(lang, translations)

    def get_all_translations(self, lang: str | None = None) -> dict[str, str]:
        """Get all translations for a language."""
        lang = lang or self._current_lang
        return self._translations.get(lang, {}).copy()

    def has_translation(self, key: str, lang: str | None = None) -> bool:
        """Check if a translation exists."""
        lang = lang or self._current_lang
        return key in self._translations.get(lang, {})


# Content translation support
class ContentTranslation:
    """
    Helper for translating content entities.

    Stores translations as separate entities linked by a translation_group.
    """

    @staticmethod
    def get_translation_key(entity_id: str, lang: str) -> str:
        """Generate translation relation key."""
        return f"translation:{entity_id}:{lang}"

    @staticmethod
    async def get_translations(
        db,
        entity_id: str,
    ) -> dict[str, Any]:
        """Get all translations for an entity."""
        from sqlalchemy import select

        from ..models import Relation

        query = select(Relation).where(
            Relation.from_entity_id == entity_id,
            Relation.relation_type == "translation",
        )
        result = await db.execute(query)
        relations = result.scalars().all()

        translations = {}
        for rel in relations:
            # The metadata stores the language code
            lang = rel.metadata.get("lang") if rel.metadata else None
            if lang:
                translations[lang] = rel.to_entity_id

        return translations


# Global instance
i18n_service = I18nService()


# Convenience function
def t(key: str, lang: str | None = None, **kwargs) -> str:
    """Shortcut for translation."""
    return i18n_service.t(key, lang, **kwargs)


# Jinja2 integration
def get_i18n_jinja_globals() -> dict:
    """Get i18n functions for Jinja2 templates."""
    return {
        "t": t,
        "i18n": i18n_service,
        "current_language": lambda: i18n_service.current_language,
        "supported_languages": lambda: i18n_service.supported_languages,
    }
