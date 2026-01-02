"""Block Converter - HTML/Gutenberg to Editor.js blocks."""

import json
import re

from bs4 import BeautifulSoup


class BlockConverter:
    """Convert WordPress HTML/Gutenberg to Editor.js format."""

    MAX_DEPTH = 10
    MAX_SIZE = 5_000_000  # 5MB

    # Gutenbergブロックパターン
    GUTENBERG_PATTERN = re.compile(
        r"<!-- wp:(\S+?)(?:\s+(\{.*?\}))?\s*-->(.*?)<!-- /wp:\1\s*-->",
        re.DOTALL,
    )

    def convert(self, html: str) -> dict:
        """Convert HTML to Editor.js block format.

        Args:
            html: WordPress HTML content (Gutenberg or classic)

        Returns:
            Editor.js format dict with "blocks" list
        """
        if not html or not html.strip():
            return {"blocks": []}

        # サイズチェック
        if len(html) > self.MAX_SIZE:
            return {
                "blocks": [
                    {
                        "type": "raw",
                        "data": {"html": html[:1000] + "... (content truncated)"},
                    }
                ]
            }

        # Gutenbergブロック検出
        if "<!-- wp:" in html:
            blocks = self._parse_gutenberg(html)
        else:
            blocks = self._parse_html(html)

        return {"blocks": blocks}

    def _parse_gutenberg(self, html: str) -> list[dict]:
        """Parse Gutenberg block comments."""
        blocks = []

        for match in self.GUTENBERG_PATTERN.finditer(html):
            block_name = match.group(1)
            attrs_str = match.group(2)
            content = match.group(3)

            # 属性パース
            try:
                attrs = json.loads(attrs_str) if attrs_str else {}
            except json.JSONDecodeError:
                attrs = {}

            # ブロック変換
            block = self._convert_block(block_name, attrs, content)
            if block:
                blocks.append(block)

        # マッチしなかった場合は全体をrawで保持
        if not blocks and html.strip():
            blocks = [{"type": "raw", "data": {"html": html.strip()}}]

        return blocks

    def _convert_block(
        self, name: str, attrs: dict, content: str, depth: int = 0
    ) -> dict | None:
        """Convert a single Gutenberg block.

        Args:
            name: Block name (e.g., "paragraph", "core/heading")
            attrs: Block attributes from JSON
            content: Inner HTML content
            depth: Nesting depth for recursion limit

        Returns:
            Editor.js block dict or None if empty
        """
        if depth > self.MAX_DEPTH:
            return {"type": "raw", "data": {"html": content.strip()}}

        # core/ プレフィックス除去
        name = name.replace("core/", "")

        if name == "paragraph":
            return self._convert_paragraph(content, attrs)

        # 未対応ブロック → raw
        return {"type": "raw", "data": {"html": content.strip()}} if content.strip() else None

    def _convert_paragraph(self, content: str, attrs: dict) -> dict | None:
        """Convert paragraph block.

        Args:
            content: HTML content inside the block
            attrs: Block attributes (e.g., align)

        Returns:
            Editor.js paragraph block or None if empty
        """
        soup = BeautifulSoup(content, "html.parser")
        p = soup.find("p")

        if not p:
            text = content.strip()
        else:
            # decode_contents() preserves inner HTML (inline tags)
            text = str(p.decode_contents())

        if not text:
            return None  # 空paragraphはスキップ

        block = {"type": "paragraph", "data": {"text": text}}

        # 配置属性
        align = attrs.get("align")
        if align in ("center", "right"):
            block["tunes"] = {"alignmentTune": {"alignment": align}}

        return block

    def _parse_html(self, html: str) -> list[dict]:
        """Parse classic HTML (no Gutenberg).

        Args:
            html: Plain HTML without Gutenberg comments

        Returns:
            List of Editor.js blocks
        """
        # S4で実装予定
        # 現時点ではrawブロックで保持
        return [{"type": "raw", "data": {"html": html.strip()}}]


# シングルトン
block_converter = BlockConverter()
