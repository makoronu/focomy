"""WordPress Import Constants - Shared constants for import operations."""

# WordPress status to Focomy status mapping
WP_STATUS_MAP: dict[str, str] = {
    "publish": "published",
    "draft": "draft",
    "pending": "pending",
    "private": "private",
    "future": "scheduled",
    "trash": "archived",
}
