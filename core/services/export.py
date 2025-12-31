"""Export Service - Content export for CMS migration.

Exports content in various formats for migration to other systems.
"""

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue, Relation
from ..utils import utcnow

ExportFormat = Literal["json", "csv", "wordpress", "markdown"]


@dataclass
class ExportOptions:
    """Export configuration options."""

    include_drafts: bool = False
    include_deleted: bool = False
    include_media: bool = True
    include_relations: bool = True
    include_metadata: bool = True
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass
class ExportResult:
    """Export operation result."""

    format: str
    entity_count: int
    media_count: int
    file_size: int
    filename: str
    created_at: datetime


class ExportService:
    """
    Service for exporting content to various formats.

    Usage:
        export = ExportService(db)

        # Export to JSON
        data = await export.export_json("post")

        # Export to WordPress WXR
        wxr = await export.export_wordpress()

        # Export full site
        zip_data = await export.export_full_site()
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_json(
        self,
        type_name: str = None,
        options: ExportOptions = None,
    ) -> dict:
        """
        Export content to JSON format.

        Args:
            type_name: Optional content type filter
            options: Export options

        Returns:
            JSON-serializable dict
        """
        options = options or ExportOptions()

        entities = await self._get_entities(type_name, options)

        result = {
            "version": "1.0",
            "exported_at": utcnow().isoformat(),
            "generator": "Focomy CMS",
            "content_types": {},
        }

        for entity in entities:
            type_name = entity.type
            if type_name not in result["content_types"]:
                result["content_types"][type_name] = []

            entity_data = await self._serialize_entity(entity, options)
            result["content_types"][type_name].append(entity_data)

        if options.include_media:
            result["media"] = await self._export_media_list()

        if options.include_relations:
            result["relations"] = await self._export_relations()

        return result

    async def export_csv(
        self,
        type_name: str,
        options: ExportOptions = None,
    ) -> str:
        """
        Export content type to CSV format.

        Args:
            type_name: Content type to export
            options: Export options

        Returns:
            CSV string
        """
        options = options or ExportOptions()

        entities = await self._get_entities(type_name, options)

        if not entities:
            return ""

        # Collect all field names
        all_fields = set()
        entity_values = {}

        for entity in entities:
            values = await self._get_entity_values(entity.id)
            entity_values[entity.id] = values
            all_fields.update(values.keys())

        # Sort fields for consistent output
        fields = ["id", "created_at", "updated_at"] + sorted(all_fields - {"id"})

        # Write CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()

        for entity in entities:
            row = {
                "id": entity.id,
                "created_at": entity.created_at.isoformat() if entity.created_at else "",
                "updated_at": entity.updated_at.isoformat() if entity.updated_at else "",
                **entity_values.get(entity.id, {}),
            }
            writer.writerow(row)

        return output.getvalue()

    async def export_wordpress(
        self,
        options: ExportOptions = None,
    ) -> str:
        """
        Export to WordPress WXR format.

        Args:
            options: Export options

        Returns:
            WXR XML string
        """
        options = options or ExportOptions()

        # Get posts
        posts = await self._get_entities("post", options)
        pages = await self._get_entities("page", options)

        # Build WXR
        wxr = self._build_wxr_header()

        # Add posts
        for post in posts:
            values = await self._get_entity_values(post.id)
            wxr += self._build_wxr_item(post, values, "post")

        # Add pages
        for page in pages:
            values = await self._get_entity_values(page.id)
            wxr += self._build_wxr_item(page, values, "page")

        wxr += self._build_wxr_footer()

        return wxr

    def _build_wxr_header(self) -> str:
        """Build WXR XML header."""
        return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
    xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.2/">
<channel>
    <title>Focomy Export</title>
    <link></link>
    <description>Exported from Focomy CMS</description>
    <pubDate>{utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
    <wp:wxr_version>1.2</wp:wxr_version>
"""

    def _build_wxr_item(self, entity: Entity, values: dict, post_type: str) -> str:
        """Build WXR item element."""
        title = values.get("title", "")
        content = self._extract_content_text(values.get("content", {}))
        slug = values.get("slug", "")
        status = "publish" if values.get("status") == "published" else "draft"
        date = entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else ""

        return f"""
    <item>
        <title><![CDATA[{title}]]></title>
        <link></link>
        <pubDate>{date}</pubDate>
        <dc:creator><![CDATA[admin]]></dc:creator>
        <content:encoded><![CDATA[{content}]]></content:encoded>
        <wp:post_id>{hash(entity.id) % 100000}</wp:post_id>
        <wp:post_date>{date}</wp:post_date>
        <wp:post_name>{slug}</wp:post_name>
        <wp:status>{status}</wp:status>
        <wp:post_type>{post_type}</wp:post_type>
    </item>
"""

    def _build_wxr_footer(self) -> str:
        """Build WXR XML footer."""
        return """
</channel>
</rss>
"""

    def _extract_content_text(self, content: Any) -> str:
        """Extract plain text from Editor.js content."""
        if not content:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            blocks = content.get("blocks", [])
            texts = []
            for block in blocks:
                block_type = block.get("type", "")
                data = block.get("data", {})

                if block_type == "paragraph":
                    texts.append(f"<p>{data.get('text', '')}</p>")
                elif block_type == "header":
                    level = data.get("level", 2)
                    texts.append(f"<h{level}>{data.get('text', '')}</h{level}>")
                elif block_type == "list":
                    items = data.get("items", [])
                    style = data.get("style", "unordered")
                    tag = "ol" if style == "ordered" else "ul"
                    li_items = "".join(f"<li>{item}</li>" for item in items)
                    texts.append(f"<{tag}>{li_items}</{tag}>")
                elif block_type == "quote":
                    texts.append(f"<blockquote>{data.get('text', '')}</blockquote>")
                elif block_type == "code":
                    texts.append(f"<pre><code>{data.get('code', '')}</code></pre>")

            return "\n".join(texts)

        return ""

    async def export_markdown(
        self,
        type_name: str = "post",
        options: ExportOptions = None,
    ) -> dict[str, str]:
        """
        Export content to Markdown files.

        Args:
            type_name: Content type to export
            options: Export options

        Returns:
            Dict of filename -> markdown content
        """
        options = options or ExportOptions()

        entities = await self._get_entities(type_name, options)

        files = {}

        for entity in entities:
            values = await self._get_entity_values(entity.id)
            slug = values.get("slug", entity.id)
            title = values.get("title", "Untitled")
            content = self._convert_to_markdown(values.get("content", {}))

            # Build frontmatter
            frontmatter = [
                "---",
                f'title: "{title}"',
                f"slug: {slug}",
                f"date: {entity.created_at.isoformat() if entity.created_at else ''}",
                f"status: {values.get('status', 'draft')}",
            ]

            if values.get("tags"):
                frontmatter.append(f"tags: {values['tags']}")

            frontmatter.append("---")
            frontmatter.append("")

            markdown = "\n".join(frontmatter) + content

            files[f"{slug}.md"] = markdown

        return files

    def _convert_to_markdown(self, content: Any) -> str:
        """Convert Editor.js content to Markdown."""
        if not content:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            blocks = content.get("blocks", [])
            texts = []

            for block in blocks:
                block_type = block.get("type", "")
                data = block.get("data", {})

                if block_type == "paragraph":
                    texts.append(data.get("text", ""))
                    texts.append("")
                elif block_type == "header":
                    level = data.get("level", 2)
                    texts.append("#" * level + " " + data.get("text", ""))
                    texts.append("")
                elif block_type == "list":
                    items = data.get("items", [])
                    style = data.get("style", "unordered")
                    for i, item in enumerate(items):
                        if style == "ordered":
                            texts.append(f"{i+1}. {item}")
                        else:
                            texts.append(f"- {item}")
                    texts.append("")
                elif block_type == "quote":
                    texts.append(f"> {data.get('text', '')}")
                    texts.append("")
                elif block_type == "code":
                    lang = data.get("language", "")
                    texts.append(f"```{lang}")
                    texts.append(data.get("code", ""))
                    texts.append("```")
                    texts.append("")
                elif block_type == "image":
                    url = data.get("file", {}).get("url", "")
                    caption = data.get("caption", "")
                    texts.append(f"![{caption}]({url})")
                    texts.append("")

            return "\n".join(texts)

        return ""

    async def export_full_site(
        self,
        options: ExportOptions = None,
    ) -> bytes:
        """
        Export entire site as a ZIP archive.

        Args:
            options: Export options

        Returns:
            ZIP file as bytes
        """
        options = options or ExportOptions()
        options.include_media = True
        options.include_relations = True

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Export JSON data
            json_data = await self.export_json(options=options)
            zf.writestr("data.json", json.dumps(json_data, indent=2, ensure_ascii=False))

            # Export content types definitions
            content_types = await self._export_content_type_definitions()
            zf.writestr("content_types.json", json.dumps(content_types, indent=2))

            # Export relations config
            relations_config = await self._export_relations_config()
            zf.writestr("relations.json", json.dumps(relations_config, indent=2))

            # Export media files
            if options.include_media:
                media_files = await self._get_media_files()
                for file_info in media_files:
                    try:
                        file_path = Path("uploads") / file_info["path"]
                        if file_path.exists():
                            zf.write(file_path, f"media/{file_info['path']}")
                    except Exception:
                        pass

        zip_buffer.seek(0)
        return zip_buffer.read()

    async def _get_entities(
        self,
        type_name: str = None,
        options: ExportOptions = None,
    ) -> list[Entity]:
        """Get entities for export."""
        options = options or ExportOptions()

        conditions = []

        if type_name:
            conditions.append(Entity.type == type_name)

        if not options.include_deleted:
            conditions.append(Entity.deleted_at.is_(None))

        if not options.include_drafts:
            # Would need to check status field
            pass

        if options.date_from:
            conditions.append(Entity.created_at >= options.date_from)

        if options.date_to:
            conditions.append(Entity.created_at <= options.date_to)

        query = select(Entity)
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _get_entity_values(self, entity_id: str) -> dict:
        """Get all values for an entity."""
        query = select(EntityValue).where(EntityValue.entity_id == entity_id)
        result = await self.db.execute(query)
        values = result.scalars().all()

        return {v.field_name: v.value_json if v.value_json else v.value_text for v in values}

    async def _serialize_entity(
        self,
        entity: Entity,
        options: ExportOptions,
    ) -> dict:
        """Serialize entity for export."""
        values = await self._get_entity_values(entity.id)

        data = {
            "id": entity.id,
            "type": entity.type,
            "values": values,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

        if options.include_metadata:
            data["created_by"] = entity.created_by
            data["updated_by"] = entity.updated_by

        if options.include_relations:
            data["relations"] = await self._get_entity_relations(entity.id)

        return data

    async def _get_entity_relations(self, entity_id: str) -> list[dict]:
        """Get relations for an entity."""
        query = select(Relation).where(Relation.from_entity_id == entity_id)
        result = await self.db.execute(query)
        relations = result.scalars().all()

        return [
            {
                "type": r.relation_type,
                "to_entity_id": r.to_entity_id,
                "position": r.position,
            }
            for r in relations
        ]

    async def _export_media_list(self) -> list[dict]:
        """Export media entity list."""
        media_entities = await self._get_entities("media")
        return [
            await self._serialize_entity(e, ExportOptions(include_relations=False))
            for e in media_entities
        ]

    async def _export_relations(self) -> list[dict]:
        """Export all relations."""
        query = select(Relation)
        result = await self.db.execute(query)
        relations = result.scalars().all()

        return [
            {
                "from_entity_id": r.from_entity_id,
                "to_entity_id": r.to_entity_id,
                "relation_type": r.relation_type,
                "position": r.position,
            }
            for r in relations
        ]

    async def _export_content_type_definitions(self) -> dict:
        """Export content type YAML definitions."""
        # Would read from content_types directory
        return {}

    async def _export_relations_config(self) -> dict:
        """Export relations configuration."""
        # Would read from relations.yaml
        return {}

    async def _get_media_files(self) -> list[dict]:
        """Get media file information."""
        media_entities = await self._get_entities("media")
        files = []

        for entity in media_entities:
            values = await self._get_entity_values(entity.id)
            if values.get("path"):
                files.append(
                    {
                        "id": entity.id,
                        "path": values.get("path"),
                        "filename": values.get("filename"),
                    }
                )

        return files


def get_export_service(db: AsyncSession) -> ExportService:
    return ExportService(db)
