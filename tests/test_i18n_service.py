"""Tests for I18nService.

Tests translation, interpolation, and language switching.
"""

import pytest

from core.services.i18n import I18nService, t


class TestI18nService:
    """I18nService test cases."""

    @pytest.fixture
    def i18n(self) -> I18nService:
        return I18nService()

    def test_default_language(self, i18n: I18nService):
        """Test default language is Japanese."""
        assert i18n.current_language == "ja"

    def test_translate_japanese(self, i18n: I18nService):
        """Test Japanese translation."""
        assert i18n.t("save") == "保存"
        assert i18n.t("cancel") == "キャンセル"
        assert i18n.t("delete") == "削除"

    def test_translate_english(self, i18n: I18nService):
        """Test English translation."""
        assert i18n.t("save", lang="en") == "Save"
        assert i18n.t("cancel", lang="en") == "Cancel"
        assert i18n.t("delete", lang="en") == "Delete"

    def test_set_language(self, i18n: I18nService):
        """Test setting current language."""
        i18n.set_language("en")
        assert i18n.current_language == "en"
        assert i18n.t("save") == "Save"

        i18n.set_language("ja")
        assert i18n.current_language == "ja"
        assert i18n.t("save") == "保存"

    def test_invalid_language_ignored(self, i18n: I18nService):
        """Test that invalid language is ignored."""
        i18n.set_language("invalid")
        assert i18n.current_language == "ja"

    def test_missing_key_returns_key(self, i18n: I18nService):
        """Test that missing key returns the key itself."""
        result = i18n.t("nonexistent_key")
        assert result == "nonexistent_key"

    def test_interpolation(self, i18n: I18nService):
        """Test string interpolation."""
        result = i18n.t("password_too_short", min=12)
        assert "12" in result

    def test_interpolation_english(self, i18n: I18nService):
        """Test English interpolation."""
        result = i18n.t("password_too_short", lang="en", min=8)
        assert "8" in result
        assert "at least" in result.lower()

    def test_fallback_to_default(self, i18n: I18nService):
        """Test fallback to default language."""
        # Add a key only in Japanese
        i18n.add_translations("ja", {"custom_key": "カスタム値"})

        # Should fallback to Japanese when not in English
        result = i18n.t("custom_key", lang="en")
        assert result == "カスタム値"

    def test_add_translations(self, i18n: I18nService):
        """Test adding translations."""
        i18n.add_translations("ja", {"new_key": "新しい値"})
        assert i18n.t("new_key") == "新しい値"

    def test_add_new_language(self, i18n: I18nService):
        """Test adding a new language."""
        i18n.add_translations("fr", {
            "save": "Sauvegarder",
            "cancel": "Annuler",
        })

        assert i18n.t("save", lang="fr") == "Sauvegarder"
        assert i18n.t("cancel", lang="fr") == "Annuler"

    def test_supported_languages(self, i18n: I18nService):
        """Test supported languages list."""
        languages = i18n.supported_languages
        assert "ja" in languages
        assert "en" in languages

    def test_has_translation(self, i18n: I18nService):
        """Test checking if translation exists."""
        assert i18n.has_translation("save") is True
        assert i18n.has_translation("nonexistent") is False

    def test_get_all_translations(self, i18n: I18nService):
        """Test getting all translations for a language."""
        translations = i18n.get_all_translations("ja")

        assert "save" in translations
        assert "cancel" in translations
        assert translations["save"] == "保存"


class TestConvenienceFunction:
    """Test the convenience t() function."""

    def test_shortcut_function(self):
        """Test the t() shortcut function."""
        assert t("save") == "保存"
        assert t("save", lang="en") == "Save"

    def test_shortcut_with_interpolation(self):
        """Test shortcut with interpolation."""
        result = t("password_too_short", min=10)
        assert "10" in result


class TestTranslationCategories:
    """Test translations by category."""

    @pytest.fixture
    def i18n(self) -> I18nService:
        return I18nService()

    def test_common_translations(self, i18n: I18nService):
        """Test common UI translations."""
        common_keys = [
            "save", "cancel", "delete", "edit", "create",
            "search", "filter", "actions", "confirm",
            "yes", "no", "loading", "error", "success", "warning"
        ]

        for key in common_keys:
            assert i18n.has_translation(key, "ja")
            assert i18n.has_translation(key, "en")

    def test_auth_translations(self, i18n: I18nService):
        """Test authentication translations."""
        auth_keys = [
            "login", "logout", "email", "password",
            "forgot_password", "reset_password", "register"
        ]

        for key in auth_keys:
            assert i18n.has_translation(key, "ja")
            assert i18n.has_translation(key, "en")

    def test_admin_translations(self, i18n: I18nService):
        """Test admin UI translations."""
        admin_keys = [
            "dashboard", "settings", "users", "media",
            "comments", "trash", "audit_log"
        ]

        for key in admin_keys:
            assert i18n.has_translation(key, "ja")
            assert i18n.has_translation(key, "en")

    def test_content_translations(self, i18n: I18nService):
        """Test content management translations."""
        content_keys = [
            "title", "slug", "status", "draft", "published",
            "scheduled", "created_at", "updated_at",
            "author", "category", "tags"
        ]

        for key in content_keys:
            assert i18n.has_translation(key, "ja")
            assert i18n.has_translation(key, "en")

    def test_message_translations(self, i18n: I18nService):
        """Test message translations."""
        message_keys = [
            "saved_successfully", "deleted_successfully",
            "error_occurred", "confirm_delete",
            "no_results", "required_field", "invalid_email"
        ]

        for key in message_keys:
            assert i18n.has_translation(key, "ja")
            assert i18n.has_translation(key, "en")
