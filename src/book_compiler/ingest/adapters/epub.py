"""EPUB adapter — stdlib zip + minimal HTML strip."""

from __future__ import annotations

import re
import zipfile
from html import unescape
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from ..canonical import BookDraft

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+\n")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p\s*>", "\n\n", html)
    html = re.sub(r"(?is)</h[1-6]\s*>", "\n\n", html)
    text = unescape(_TAG_RE.sub("", html))
    text = _WS_RE.sub("\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _spine_html_paths(zf: zipfile.ZipFile) -> list[str]:
    """Resolve reading order from container + opf."""
    container = zf.read("META-INF/container.xml")
    root = ET.fromstring(container)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    opf_path = root.find(".//c:rootfile", ns)
    if opf_path is None:
        raise ValueError("EPUB 缺少 container.xml rootfile")
    opf = opf_path.attrib.get("full-path", "")
    if not opf:
        raise ValueError("EPUB container 无 full-path")

    opf_root = ET.fromstring(zf.read(opf))
    opf_dir = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
    opf_ns = {"o": "http://www.idpf.org/2007/opf"}
    manifest = {
        item.attrib["id"]: item.attrib.get("href", "")
        for item in opf_root.findall(".//o:item", opf_ns)
        if item.attrib.get("id") and item.attrib.get("href")
    }
    spine = opf_root.find(".//o:spine", opf_ns)
    if spine is None:
        raise ValueError("EPUB 缺少 spine")

    paths: list[str] = []
    for ref in spine.findall("o:itemref", opf_ns):
        idref = ref.attrib.get("idref")
        href = manifest.get(idref or "")
        if not href:
            continue
        full = opf_dir + href
        # normalize path
        parts: list[str] = []
        for seg in full.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg and seg != ".":
                parts.append(seg)
        paths.append("/".join(parts))
    return paths


def spine_item_count(data: bytes) -> int:
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return len(_spine_html_paths(zf))


def _normalize_href(href: str) -> str:
    href = href.split("#", 1)[0].strip()
    parts: list[str] = []
    for seg in href.replace("\\", "/").split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg and seg != ".":
            parts.append(seg)
    return "/".join(parts)


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_ncx_path(zf: zipfile.ZipFile, opf_path: str) -> str | None:
    opf_root = ET.fromstring(zf.read(opf_path))
    opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    opf_ns = {"o": "http://www.idpf.org/2007/opf"}
    for item in opf_root.findall(".//o:item", opf_ns):
        props = item.attrib.get("properties", "")
        media = item.attrib.get("media-type", "")
        href = item.attrib.get("href", "")
        if "nav" in props or media == "application/x-dtbncx+xml" or href.endswith(".ncx"):
            return _normalize_href(opf_dir + href)
    for name in zf.namelist():
        if name.lower().endswith(".ncx"):
            return _normalize_href(name)
    return None


def _top_level_nav_points(ncx_root: ET.Element) -> list[tuple[str, str]]:
    """Return (title, href) for navPoints directly under navMap."""
    nav_map = next((el for el in ncx_root.iter() if _local_tag(el.tag) == "navMap"), None)
    if nav_map is None:
        return []
    out: list[tuple[str, str]] = []
    for child in nav_map:
        if _local_tag(child.tag) != "navPoint":
            continue
        label = next((c for c in child if _local_tag(c.tag) == "navLabel"), None)
        text_el = None
        if label is not None:
            text_el = next((c for c in label if _local_tag(c.tag) == "text"), None)
        content = next((c for c in child if _local_tag(c.tag) == "content"), None)
        title = (text_el.text or "").strip() if text_el is not None else ""
        href = content.attrib.get("src", "") if content is not None else ""
        if title and href:
            out.append((title, _normalize_href(href)))
    return out


def spine_index_for_href(data: bytes, href: str) -> int | None:
    target = _normalize_href(href)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        spine = _spine_html_paths(zf)
        index = {_normalize_href(p): i for i, p in enumerate(spine)}
        if target in index:
            return index[target]
        # suffix match for path variants
        for path, i in index.items():
            if path.endswith(target) or target.endswith(path):
                return i
    return None


def _extract_body_html(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", "", html)
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", html)
    return (m.group(1) if m else html).strip()


def _resolve_asset_path(base_dir: str, ref: str) -> str:
    ref = ref.split("#", 1)[0].strip()
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    combined = f"{base_dir}/{ref}" if base_dir else ref
    return _normalize_href(combined)


def _rewrite_epub_assets(html: str, base_dir: str, slug: str) -> str:
    from urllib.parse import quote

    def src_repl(m: re.Match) -> str:
        q = m.group(1)
        ref = m.group(2)
        resolved = _resolve_asset_path(base_dir, ref)
        if resolved.startswith(("http://", "https://", "data:")):
            return m.group(0)
        url = f"/api/books/{quote(slug, safe='')}/epub-asset?path={quote(resolved, safe='')}"
        return f"src={q}{url}{q}"

    html = re.sub(r"""src=(["'])(.*?)\1""", src_repl, html)
    return html


def _chapter_spine_ranges(zf: zipfile.ZipFile) -> list[dict]:
    container = zf.read("META-INF/container.xml")
    croot = ET.fromstring(container)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    opf_el = croot.find(".//c:rootfile", ns)
    if opf_el is None:
        raise ValueError("EPUB 缺少 container.xml rootfile")
    opf = opf_el.attrib.get("full-path", "")
    ncx_path = _find_ncx_path(zf, opf)
    if not ncx_path:
        raise ValueError("EPUB 缺少 toc.ncx 目录")
    ncx_root = ET.fromstring(zf.read(ncx_path))
    nav = _top_level_nav_points(ncx_root)
    if not nav:
        raise ValueError("EPUB 目录为空")

    spine = _spine_html_paths(zf)
    spine_index = {_normalize_href(p): i for i, p in enumerate(spine)}

    def locate(href: str) -> int:
        key = _normalize_href(href)
        if key in spine_index:
            return spine_index[key]
        for path, i in spine_index.items():
            if path.endswith(key) or key.endswith(path):
                return i
        return 0

    starts = [locate(href) for _, href in nav]
    ranges: list[dict] = []
    for idx, ((title, href), start) in enumerate(zip(nav, starts)):
        end = len(spine)
        for j in range(idx + 1, len(starts)):
            if starts[j] > start:
                end = starts[j]
                break
        ranges.append(
            {
                "title": title,
                "href": _normalize_href(href),
                "start": start,
                "end": end,
                "spine": spine,
            }
        )
    return ranges


def extract_chapter_html(data: bytes, chapter_href: str, *, slug: str = "") -> str:
    """Return merged HTML body for one NCX chapter."""
    target = _normalize_href(chapter_href)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        ranges = _chapter_spine_ranges(zf)
        match = next(
            (
                r
                for r in ranges
                if r["href"] == target or r["href"].endswith(target) or target.endswith(r["href"])
            ),
            None,
        )
        if not match:
            raise ValueError(f"EPUB 章节未找到: {chapter_href}")

        spine = match["spine"]
        parts: list[str] = []
        for i in range(match["start"], match["end"]):
            path = spine[i]
            try:
                raw = zf.read(path).decode("utf-8", errors="replace")
            except KeyError:
                continue
            body = _extract_body_html(raw)
            if not body:
                continue
            base_dir = path.rsplit("/", 1)[0] if "/" in path else ""
            if slug:
                body = _rewrite_epub_assets(body, base_dir, slug)
            parts.append(f'<section class="epub-section">{body}</section>')

    if not parts:
        raise ValueError("EPUB 章节 HTML 为空")
    return f'<div class="epub-chapter">{"".join(parts)}</div>'


def read_epub_asset(data: bytes, asset_path: str) -> tuple[bytes, str]:
    target = _normalize_href(asset_path)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        if target in zf.namelist():
            raw = zf.read(target)
        else:
            hit = next(
                (n for n in zf.namelist() if n.endswith(target) or target.endswith(n)),
                None,
            )
            if not hit:
                raise FileNotFoundError(asset_path)
            raw = zf.read(hit)
    ext = Path(target).suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
    return raw, mime


def extract_nav_chapters(data: bytes) -> list[dict]:
    """Split EPUB by top-level NCX entries → [{title, href, text, spine_index}]."""
    with zipfile.ZipFile(BytesIO(data)) as zf:
        container = zf.read("META-INF/container.xml")
        croot = ET.fromstring(container)
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        opf_path = croot.find(".//c:rootfile", ns)
        if opf_path is None:
            raise ValueError("EPUB 缺少 container.xml rootfile")
        opf = opf_path.attrib.get("full-path", "")
        ncx_path = _find_ncx_path(zf, opf)
        if not ncx_path:
            raise ValueError("EPUB 缺少 toc.ncx 目录")
        ncx_root = ET.fromstring(zf.read(ncx_path))
        nav = _top_level_nav_points(ncx_root)
        if not nav:
            raise ValueError("EPUB 目录为空")

        spine = _spine_html_paths(zf)
        spine_index = {_normalize_href(p): i for i, p in enumerate(spine)}

        def locate(href: str) -> int:
            key = _normalize_href(href)
            if key in spine_index:
                return spine_index[key]
            for path, i in spine_index.items():
                if path.endswith(key) or key.endswith(path):
                    return i
            return 0

        starts = [locate(href) for _, href in nav]
        chapters: list[dict] = []
        for idx, ((title, href), start) in enumerate(zip(nav, starts)):
            end = len(spine)
            for j in range(idx + 1, len(starts)):
                if starts[j] > start:
                    end = starts[j]
                    break
            chunks: list[str] = []
            for i in range(start, end):
                try:
                    raw = zf.read(spine[i]).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                t = _html_to_text(raw)
                if t:
                    chunks.append(t)
            text = "\n\n".join(chunks).strip()
            if not text:
                continue
            chapters.append(
                {
                    "title": title,
                    "href": _normalize_href(href),
                    "text": text + "\n",
                    "spine_index": start,
                }
            )
        return chapters


def nav_spine_entries(data: bytes) -> list[dict]:
    """Top-level NCX entries with spine positions (no body text)."""
    chapters = extract_nav_chapters(data)
    return [
        {"title": c["title"], "href": c["href"], "spine_index": c["spine_index"]}
        for c in chapters
    ]


def match_nav_spine(entries: list[dict], chapter_title: str) -> dict | None:
    title = chapter_title.strip()
    if not title:
        return None
    for entry in entries:
        nav_title = entry["title"]
        if title == nav_title or nav_title.endswith(title) or title in nav_title:
            return entry
    return None


def adapt(data: bytes, filename: str) -> BookDraft:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            paths = _spine_html_paths(zf)
            chunks: list[str] = []
            for path in paths:
                try:
                    raw = zf.read(path).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                t = _html_to_text(raw)
                if t:
                    chunks.append(t)
    except zipfile.BadZipFile as e:
        raise ValueError("无法解析 EPUB") from e

    if not chunks:
        raise ValueError("EPUB 中未提取到正文")

    text = "\n\n".join(chunks).strip() + "\n"
    return BookDraft(
        text=text,
        source_format="epub",
        original_filename=filename,
        warnings=["EPUB 已按 spine 顺序转为纯文本"],
    )
