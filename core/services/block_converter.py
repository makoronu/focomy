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

    # ショートコードパターン
    # [shortcode attr="value"] or [shortcode attr="value"]content[/shortcode]
    # Note: ショートコード名はハイフン許可（contact-form等）
    SHORTCODE_PATTERN = re.compile(
        r'\[([\w-]+)((?:\s+[\w-]+=["\'][^"\']*["\']|\s+[\w-]+=\S+)*)\s*/?]'
        r'(?:(.*?)\[/\1])?',
        re.DOTALL | re.IGNORECASE,
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
                if isinstance(block, list):
                    blocks.extend(block)
                else:
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
        elif name == "heading":
            return self._convert_header(content, attrs)
        elif name == "list":
            return self._convert_list(content, attrs)
        elif name == "image":
            return self._convert_image(content, attrs)
        elif name == "quote":
            return self._convert_quote(content, attrs)
        elif name == "code" or name == "preformatted":
            return self._convert_code(content, attrs)
        elif name == "separator":
            return self._convert_delimiter()
        elif name == "table":
            return self._convert_table(content, attrs)
        elif name == "embed" or name.startswith("core-embed/"):
            return self._convert_embed(content, attrs, name)
        elif name == "html":
            return self._convert_raw(content)
        elif name == "freeform":
            # クラシックブロック - 中身をパースして複数ブロックに分解
            return self._convert_freeform(content, depth)
        elif name in ("columns", "column", "group", "cover"):
            # ネストブロック - 中のブロックを再帰的にパース
            return self._convert_nested(content, depth)

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

    def _convert_header(self, content: str, attrs: dict) -> dict | None:
        """Convert heading block."""
        soup = BeautifulSoup(content, "html.parser")

        # h1-h6を探す
        heading = None
        for level in range(1, 7):
            heading = soup.find(f"h{level}")
            if heading:
                break

        if heading:
            text = heading.get_text(strip=True)
            detected_level = int(heading.name[1])
        else:
            text = content.strip()
            detected_level = attrs.get("level", 2)

        if not text:
            return None

        level = attrs.get("level", detected_level)
        return {"type": "header", "data": {"text": text, "level": level}}

    def _convert_list(self, content: str, attrs: dict) -> dict | None:
        """Convert list block."""
        soup = BeautifulSoup(content, "html.parser")

        # ul or ol
        ul = soup.find("ul")
        ol = soup.find("ol")
        list_el = ol if ol else ul

        if not list_el:
            return None

        style = "ordered" if ol else "unordered"
        items = []
        for li in list_el.find_all("li", recursive=False):
            items.append(str(li.decode_contents()))

        if not items:
            return None

        return {"type": "list", "data": {"style": style, "items": items}}

    def _convert_image(self, content: str, attrs: dict) -> dict | None:
        """Convert image block."""
        soup = BeautifulSoup(content, "html.parser")
        img = soup.find("img")

        if not img:
            return None

        url = img.get("src", "")
        alt = img.get("alt", "")

        # figcaptionからキャプション取得
        caption = ""
        figcaption = soup.find("figcaption")
        if figcaption:
            caption = figcaption.get_text(strip=True)

        if not url:
            return None

        return {
            "type": "image",
            "data": {
                "file": {"url": url},
                "caption": caption or alt,
            },
        }

    def _convert_quote(self, content: str, attrs: dict) -> dict | None:
        """Convert quote block."""
        soup = BeautifulSoup(content, "html.parser")
        blockquote = soup.find("blockquote")

        if blockquote:
            # 引用テキスト
            p = blockquote.find("p")
            text = str(p.decode_contents()) if p else blockquote.get_text(strip=True)

            # 引用元（cite）
            cite = blockquote.find("cite")
            caption = cite.get_text(strip=True) if cite else ""
        else:
            text = content.strip()
            caption = ""

        if not text:
            return None

        return {"type": "quote", "data": {"text": text, "caption": caption}}

    def _convert_code(self, content: str, attrs: dict) -> dict | None:
        """Convert code block."""
        soup = BeautifulSoup(content, "html.parser")

        # pre > code or just pre or just code
        code = soup.find("code")
        pre = soup.find("pre")

        if code:
            code_text = code.get_text()
        elif pre:
            code_text = pre.get_text()
        else:
            code_text = content.strip()

        if not code_text:
            return None

        return {"type": "code", "data": {"code": code_text}}

    def _convert_delimiter(self) -> dict:
        """Convert separator/delimiter block."""
        return {"type": "delimiter", "data": {}}

    def _convert_table(self, content: str, attrs: dict) -> dict | None:
        """Convert table block."""
        soup = BeautifulSoup(content, "html.parser")
        table = soup.find("table")

        if not table:
            return None

        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                cells.append(str(cell.decode_contents()))
            if cells:
                rows.append(cells)

        if not rows:
            return None

        return {"type": "table", "data": {"content": rows}}

    def _convert_embed(self, content: str, attrs: dict, name: str) -> dict | None:
        """Convert embed block (YouTube, Vimeo, etc.)."""
        url = attrs.get("url", "")

        # サービス判定
        if "core-embed/" in name:
            service = name.split("/")[-1]
        else:
            service = attrs.get("providerNameSlug", "")

        # URLからサービスを推測
        if not service:
            if "youtube" in url or "youtu.be" in url:
                service = "youtube"
            elif "vimeo" in url:
                service = "vimeo"
            elif "twitter" in url or "x.com" in url:
                service = "twitter"
            elif "spotify" in url:
                service = "spotify"

        # 埋め込みURL生成
        embed_url = url
        if service == "youtube":
            # YouTube URL → embed URL変換
            if "watch?v=" in url:
                video_id = url.split("watch?v=")[-1].split("&")[0]
                embed_url = f"https://www.youtube.com/embed/{video_id}"
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[-1].split("?")[0]
                embed_url = f"https://www.youtube.com/embed/{video_id}"

        if not url:
            return None

        return {
            "type": "embed",
            "data": {
                "service": service,
                "source": url,
                "embed": embed_url,
                "caption": attrs.get("caption", ""),
            },
        }

    def _convert_raw(self, content: str) -> dict | None:
        """Convert HTML block (raw HTML)."""
        if not content.strip():
            return None
        return {"type": "raw", "data": {"html": content.strip()}}

    def _convert_freeform(self, content: str, depth: int) -> dict | list | None:
        """Convert freeform (classic editor) block.

        Classic blocks contain arbitrary HTML that needs to be parsed.
        Returns raw block for now - will be enhanced in S4.
        """
        if not content.strip():
            return None

        # クラシックブロックの中身をパース
        # 再帰的にGutenbergブロックがあればパース
        if "<!-- wp:" in content:
            inner_blocks = []
            for match in self.GUTENBERG_PATTERN.finditer(content):
                block_name = match.group(1)
                attrs_str = match.group(2)
                inner_content = match.group(3)

                try:
                    attrs = json.loads(attrs_str) if attrs_str else {}
                except json.JSONDecodeError:
                    attrs = {}

                block = self._convert_block(block_name, attrs, inner_content, depth + 1)
                if block:
                    if isinstance(block, list):
                        inner_blocks.extend(block)
                    else:
                        inner_blocks.append(block)

            if inner_blocks:
                return inner_blocks

        # Gutenbergブロックがなければ通常HTMLとしてパース（ショートコード対応）
        return self._parse_html(content.strip())

    def _convert_nested(self, content: str, depth: int) -> list | dict | None:
        """Convert nested blocks (columns, group, cover).

        Nested blocks are flattened - inner blocks are extracted.
        """
        if depth > self.MAX_DEPTH:
            return {"type": "raw", "data": {"html": content.strip()}}

        blocks = []

        # 内部のブロックを再帰的にパース
        for match in self.GUTENBERG_PATTERN.finditer(content):
            block_name = match.group(1)
            attrs_str = match.group(2)
            inner_content = match.group(3)

            try:
                attrs = json.loads(attrs_str) if attrs_str else {}
            except json.JSONDecodeError:
                attrs = {}

            block = self._convert_block(block_name, attrs, inner_content, depth + 1)
            if block:
                if isinstance(block, list):
                    blocks.extend(block)
                else:
                    blocks.append(block)

        if blocks:
            return blocks

        # 内部ブロックがなければrawで保持
        if content.strip():
            return {"type": "raw", "data": {"html": content.strip()}}

        return None

    def _process_shortcodes(self, html: str) -> list[dict]:
        """Process WordPress shortcodes in HTML.

        Args:
            html: HTML content that may contain shortcodes

        Returns:
            List of Editor.js blocks from shortcodes
        """
        blocks = []
        last_end = 0

        for match in self.SHORTCODE_PATTERN.finditer(html):
            # ショートコード前のテキスト
            before = html[last_end : match.start()].strip()
            if before:
                # 前のテキストをHTMLとしてパース（再帰防止フラグ付き）
                before_blocks = self._parse_html(before, _from_shortcode=True)
                blocks.extend(before_blocks)

            # ショートコード変換
            shortcode = match.group(1).lower()
            attrs_str = match.group(2) or ""
            content = match.group(3) or ""

            attrs = self._parse_shortcode_attrs(attrs_str)
            block = self._convert_shortcode(shortcode, attrs, content)
            if block:
                if isinstance(block, list):
                    blocks.extend(block)
                else:
                    blocks.append(block)

            last_end = match.end()

        # ショートコード後のテキスト
        after = html[last_end:].strip()
        if after:
            after_blocks = self._parse_html(after, _from_shortcode=True)
            blocks.extend(after_blocks)

        return blocks

    def _parse_shortcode_attrs(self, attrs_str: str) -> dict:
        """Parse shortcode attributes string.

        Args:
            attrs_str: ' attr1="value1" attr2="value2"'

        Returns:
            {"attr1": "value1", "attr2": "value2"}
        """
        attrs = {}
        # attr="value" or attr='value' or attr=value
        pattern = re.compile(r'([\w-]+)=["\']([^"\']*)["\']|([\w-]+)=(\S+)')

        for match in pattern.finditer(attrs_str):
            if match.group(1):
                attrs[match.group(1)] = match.group(2)
            elif match.group(3):
                attrs[match.group(3)] = match.group(4)

        return attrs

    def _convert_shortcode(self, name: str, attrs: dict, content: str) -> dict | list | None:
        """Convert a single shortcode to Editor.js block.

        Args:
            name: Shortcode name (e.g., "gallery", "video")
            attrs: Parsed attributes
            content: Content between [shortcode] and [/shortcode]

        Returns:
            Editor.js block(s) or None
        """
        if name == "gallery":
            return self._convert_gallery_shortcode(attrs)
        elif name == "video":
            return self._convert_video_shortcode(attrs)
        elif name == "audio":
            return self._convert_audio_shortcode(attrs)
        elif name == "embed":
            return self._convert_embed_shortcode(content)
        elif name == "caption":
            return self._convert_caption_shortcode(content, attrs)
        elif name == "playlist":
            return self._convert_playlist_shortcode(attrs)

        # 未対応ショートコード → raw
        shortcode_text = f"[{name}"
        if attrs:
            for k, v in attrs.items():
                shortcode_text += f' {k}="{v}"'
        shortcode_text += "]"
        if content:
            shortcode_text += f"{content}[/{name}]"

        return {"type": "raw", "data": {"html": shortcode_text}}

    def _convert_gallery_shortcode(self, attrs: dict) -> dict | None:
        """Convert [gallery] shortcode.

        [gallery ids="1,2,3" columns="3"]
        """
        ids_str = attrs.get("ids", "")
        if not ids_str:
            return None

        # IDをリストに変換
        ids = [img_id.strip() for img_id in ids_str.split(",") if img_id.strip()]
        if not ids:
            return None

        # columns属性（不正値はデフォルト3）
        try:
            columns = int(attrs.get("columns", 3))
        except (ValueError, TypeError):
            columns = 3

        # Editor.js galleryブロック形式
        # Note: 実際のURLはインポート時にメディアIDから解決する必要がある
        return {
            "type": "gallery",
            "data": {
                "images": [{"id": img_id, "url": f"#media-{img_id}"} for img_id in ids],
                "columns": columns,
            },
        }

    def _convert_video_shortcode(self, attrs: dict) -> dict | None:
        """Convert [video] shortcode.

        [video src="url" poster="url"]
        """
        src = attrs.get("src", "")
        if not src:
            return None

        return {
            "type": "embed",
            "data": {
                "service": "video",
                "source": src,
                "embed": src,
                "caption": "",
            },
        }

    def _convert_audio_shortcode(self, attrs: dict) -> dict | None:
        """Convert [audio] shortcode.

        [audio src="url"]
        """
        src = attrs.get("src", "")
        if not src:
            return None

        return {
            "type": "embed",
            "data": {
                "service": "audio",
                "source": src,
                "embed": src,
                "caption": "",
            },
        }

    def _convert_embed_shortcode(self, content: str) -> dict | None:
        """Convert [embed] shortcode.

        [embed]https://youtube.com/watch?v=xxx[/embed]
        """
        url = content.strip()
        if not url:
            return None

        # サービス判定
        service = ""
        embed_url = url
        if "youtube" in url or "youtu.be" in url:
            service = "youtube"
            if "watch?v=" in url:
                video_id = url.split("watch?v=")[-1].split("&")[0]
                embed_url = f"https://www.youtube.com/embed/{video_id}"
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[-1].split("?")[0]
                embed_url = f"https://www.youtube.com/embed/{video_id}"
        elif "vimeo" in url:
            service = "vimeo"
        elif "twitter" in url or "x.com" in url:
            service = "twitter"
        elif "spotify" in url:
            service = "spotify"

        return {
            "type": "embed",
            "data": {
                "service": service,
                "source": url,
                "embed": embed_url,
                "caption": "",
            },
        }

    def _convert_caption_shortcode(self, content: str, attrs: dict) -> dict | None:
        """Convert [caption] shortcode.

        [caption]<img src="...">Caption text[/caption]
        """
        if not content.strip():
            return None

        soup = BeautifulSoup(content, "html.parser")
        img = soup.find("img")

        if img:
            url = img.get("src", "")
            alt = img.get("alt", "")
            # img以外のテキストがキャプション
            img.extract()
            caption = soup.get_text(strip=True) or alt

            if url:
                return {
                    "type": "image",
                    "data": {"file": {"url": url}, "caption": caption},
                }

        # imgがなければraw
        return {"type": "raw", "data": {"html": content.strip()}}

    def _convert_playlist_shortcode(self, attrs: dict) -> dict | None:
        """Convert [playlist] shortcode.

        [playlist ids="1,2,3" type="audio"]
        """
        ids_str = attrs.get("ids", "")
        if not ids_str:
            return None

        playlist_type = attrs.get("type", "audio")

        # プレイリストはrawで保持（Editor.jsに対応ブロックなし）
        return {
            "type": "raw",
            "data": {
                "html": f'<div class="wp-playlist" data-type="{playlist_type}" data-ids="{ids_str}"></div>'
            },
        }

    def _parse_html(self, html: str, _from_shortcode: bool = False) -> list[dict]:
        """Parse classic HTML (no Gutenberg).

        Args:
            html: Plain HTML without Gutenberg comments
            _from_shortcode: Internal flag to prevent infinite recursion

        Returns:
            List of Editor.js blocks
        """
        # ショートコード検出（再帰呼び出し時はスキップ）
        if not _from_shortcode and "[" in html and "]" in html:
            if self.SHORTCODE_PATTERN.search(html):
                return self._process_shortcodes(html)

        soup = BeautifulSoup(html, "html.parser")
        blocks = []

        # トップレベル要素を順に処理
        for element in soup.children:
            if isinstance(element, str):
                # テキストノード
                text = element.strip()
                if text:
                    blocks.append({"type": "paragraph", "data": {"text": text}})
                continue

            if element.name is None:
                continue

            block = self._html_element_to_block(element)
            if block:
                if isinstance(block, list):
                    blocks.extend(block)
                else:
                    blocks.append(block)

        # ブロックが生成されなかった場合はrawで保持
        if not blocks and html.strip():
            blocks = [{"type": "raw", "data": {"html": html.strip()}}]

        return blocks

    def _html_element_to_block(self, element) -> dict | list | None:
        """Convert a single HTML element to Editor.js block."""
        tag = element.name

        if tag == "p":
            text = str(element.decode_contents())
            if text.strip():
                return {"type": "paragraph", "data": {"text": text}}

        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = element.get_text(strip=True)
            if text:
                return {"type": "header", "data": {"text": text, "level": level}}

        elif tag == "ul":
            items = []
            for li in element.find_all("li", recursive=False):
                items.append(str(li.decode_contents()))
            if items:
                return {"type": "list", "data": {"style": "unordered", "items": items}}

        elif tag == "ol":
            items = []
            for li in element.find_all("li", recursive=False):
                items.append(str(li.decode_contents()))
            if items:
                return {"type": "list", "data": {"style": "ordered", "items": items}}

        elif tag == "img":
            url = element.get("src", "")
            alt = element.get("alt", "")
            if url:
                return {
                    "type": "image",
                    "data": {"file": {"url": url}, "caption": alt},
                }

        elif tag == "figure":
            img = element.find("img")
            if img:
                url = img.get("src", "")
                alt = img.get("alt", "")
                figcaption = element.find("figcaption")
                caption = figcaption.get_text(strip=True) if figcaption else alt
                if url:
                    return {
                        "type": "image",
                        "data": {"file": {"url": url}, "caption": caption},
                    }

        elif tag == "blockquote":
            p = element.find("p")
            text = str(p.decode_contents()) if p else element.get_text(strip=True)
            cite = element.find("cite")
            caption = cite.get_text(strip=True) if cite else ""
            if text:
                return {"type": "quote", "data": {"text": text, "caption": caption}}

        elif tag == "pre":
            code = element.find("code")
            code_text = code.get_text() if code else element.get_text()
            if code_text:
                return {"type": "code", "data": {"code": code_text}}

        elif tag == "hr":
            return {"type": "delimiter", "data": {}}

        elif tag == "table":
            rows = []
            for tr in element.find_all("tr"):
                cells = []
                for cell in tr.find_all(["td", "th"]):
                    cells.append(str(cell.decode_contents()))
                if cells:
                    rows.append(cells)
            if rows:
                return {"type": "table", "data": {"content": rows}}

        elif tag == "iframe":
            src = element.get("src", "")
            if src:
                service = ""
                if "youtube" in src:
                    service = "youtube"
                elif "vimeo" in src:
                    service = "vimeo"
                return {
                    "type": "embed",
                    "data": {"service": service, "source": src, "embed": src, "caption": ""},
                }

        elif tag == "div":
            # divの中身を再帰的にパース
            inner_blocks = []
            for child in element.children:
                if isinstance(child, str):
                    text = child.strip()
                    if text:
                        inner_blocks.append({"type": "paragraph", "data": {"text": text}})
                elif child.name:
                    block = self._html_element_to_block(child)
                    if block:
                        if isinstance(block, list):
                            inner_blocks.extend(block)
                        else:
                            inner_blocks.append(block)
            if inner_blocks:
                return inner_blocks
            # 中身がなければrawで保持
            content = str(element.decode_contents()).strip()
            if content:
                return {"type": "raw", "data": {"html": str(element)}}

        # 未対応タグはrawで保持
        content = str(element).strip()
        if content:
            return {"type": "raw", "data": {"html": content}}

        return None


# シングルトン
block_converter = BlockConverter()
