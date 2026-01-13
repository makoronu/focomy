"""AdminURL ヘルパーのテスト"""

import pytest

from core.admin.url import AdminURL


class TestAdminURL:
    """AdminURLクラスのテスト"""

    # entity_list
    def test_entity_list_normal(self):
        assert AdminURL.entity_list("post") == "/admin/post"

    def test_entity_list_channel(self):
        assert AdminURL.entity_list("post", "news") == "/admin/channel/news/posts"

    # entity_new
    def test_entity_new_normal(self):
        assert AdminURL.entity_new("post") == "/admin/post/new"

    def test_entity_new_channel(self):
        assert AdminURL.entity_new("post", "news") == "/admin/channel/news/posts/new"

    # entity_edit
    def test_entity_edit_normal(self):
        assert AdminURL.entity_edit("post", 123) == "/admin/post/123/edit"

    def test_entity_edit_channel(self):
        assert AdminURL.entity_edit("post", 123, "news") == "/admin/channel/news/posts/123/edit"

    # entity_form_action
    def test_entity_form_action_new(self):
        assert AdminURL.entity_form_action("post") == "/admin/post"

    def test_entity_form_action_edit(self):
        assert AdminURL.entity_form_action("post", 123) == "/admin/post/123"

    def test_entity_form_action_channel_new(self):
        assert AdminURL.entity_form_action("post", None, "news") == "/admin/channel/news/posts"

    def test_entity_form_action_channel_edit(self):
        assert AdminURL.entity_form_action("post", 123, "news") == "/admin/channel/news/posts/123"

    # entity_delete
    def test_entity_delete_normal(self):
        assert AdminURL.entity_delete("post", 123) == "/admin/post/123"

    def test_entity_delete_channel(self):
        assert AdminURL.entity_delete("post", 123, "news") == "/admin/channel/news/posts/123"

    # entity_bulk
    def test_entity_bulk_normal(self):
        assert AdminURL.entity_bulk("post") == "/admin/post/bulk"

    def test_entity_bulk_channel(self):
        # bulk操作は常にtype_name形式（ルートが/{type_name}/bulkのため）
        assert AdminURL.entity_bulk("post", "news") == "/admin/post/bulk"

    # entity_pagination
    def test_entity_pagination_normal(self):
        assert AdminURL.entity_pagination("post", 2) == "/admin/post?page=2"

    def test_entity_pagination_with_query(self):
        assert AdminURL.entity_pagination("post", 2, query="status=draft") == "/admin/post?page=2&status=draft"

    def test_entity_pagination_channel(self):
        assert AdminURL.entity_pagination("post", 2, "news") == "/admin/channel/news/posts?page=2"
