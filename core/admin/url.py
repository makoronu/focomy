"""
Admin URL Helper - 管理画面URL一元管理

テンプレート内でのURL直書きを禁止し、
Python側でURL生成を行うことで一貫性を保つ。
"""


class AdminURL:
    """管理画面URL生成ヘルパー"""

    @staticmethod
    def entity_list(type_name: str, channel_slug: str | None = None) -> str:
        """エンティティ一覧URL"""
        if channel_slug:
            return f"/admin/channel/{channel_slug}/posts"
        return f"/admin/{type_name}"

    @staticmethod
    def entity_new(type_name: str, channel_slug: str | None = None) -> str:
        """エンティティ新規作成URL"""
        return f"{AdminURL.entity_list(type_name, channel_slug)}/new"

    @staticmethod
    def entity_edit(type_name: str, entity_id: int, channel_slug: str | None = None) -> str:
        """エンティティ編集URL"""
        base = AdminURL.entity_list(type_name, channel_slug)
        return f"{base}/{entity_id}/edit"

    @staticmethod
    def entity_form_action(
        type_name: str, entity_id: int | None = None, channel_slug: str | None = None
    ) -> str:
        """フォーム送信先URL（新規/更新共用）"""
        base = AdminURL.entity_list(type_name, channel_slug)
        if entity_id:
            return f"{base}/{entity_id}"
        return base

    @staticmethod
    def entity_delete(type_name: str, entity_id: int, channel_slug: str | None = None) -> str:
        """エンティティ削除URL"""
        base = AdminURL.entity_list(type_name, channel_slug)
        return f"{base}/{entity_id}"

    @staticmethod
    def entity_bulk(type_name: str, channel_slug: str | None = None) -> str:
        """一括操作URL - 常にtype_name形式（ルートが/{type_name}/bulkのため）"""
        # channel_slugがあっても、ルートは/{type_name}/bulk形式
        return f"/admin/{type_name}/bulk"

    @staticmethod
    def entity_pagination(
        type_name: str, page: int, channel_slug: str | None = None, query: str | None = None
    ) -> str:
        """ページネーションURL"""
        base = AdminURL.entity_list(type_name, channel_slug)
        url = f"{base}?page={page}"
        if query:
            url += f"&{query}"
        return url
