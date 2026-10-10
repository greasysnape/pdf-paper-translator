"""Text block extraction from PDF pages."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pymupdf


@dataclass
class TextBlock:
    page: int               # 0-based page index
    index: int              # block index on the page
    bbox: tuple[float, float, float, float]
    text: str
    font_size: float
    bold: bool = False
    translation: str | None = None

    @property
    def key(self) -> str:
        return f"{self.page}:{self.index}"


def parse_page_range(spec: str | None, page_count: int) -> list[int]:
    """'1-3,7' -> [0, 1, 2, 6]. None means all pages."""
    if not spec:
        return list(range(page_count))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a) if a else 1
            end = int(b) if b else page_count
            pages.update(range(start - 1, min(end, page_count)))
        else:
            n = int(part)
            if 1 <= n <= page_count:
                pages.add(n - 1)
    return sorted(pages)


def _join_lines(block: dict) -> tuple[str, float, bool]:
    sizes: Counter[float] = Counter()
    bold_chars = 0
    total_chars = 0
    lines: list[str] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        text = "".join(s.get("text", "") for s in spans)
        for s in spans:
            n = len(s.get("text", ""))
            sizes[round(s.get("size", 0), 1)] += n
            total_chars += n
            if s.get("flags", 0) & 16:  # bold flag
                bold_chars += n
        lines.append(text)

    # de-hyphenate words split across lines
    merged = ""
    for t in lines:
        t = t.strip()
        if not t:
            continue
        if merged.endswith("-") and t[:1].islower():
            merged = merged[:-1] + t
        elif merged:
            merged += " " + t
        else:
            merged = t

    size = sizes.most_common(1)[0][0] if sizes else 10.0
    bold = total_chars > 0 and bold_chars / total_chars > 0.6
    return merged, size, bold


def extract_blocks(doc: pymupdf.Document, pages: list[int]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for pno in pages:
        page = doc[pno]
        data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for i, b in enumerate(data.get("blocks", [])):
            if b.get("type") != 0:  # 0 = text, 1 = image
                continue
            text, size, bold = _join_lines(b)
            if not text:
                continue
            blocks.append(
                TextBlock(page=pno, index=i, bbox=tuple(b["bbox"]), text=text, font_size=size, bold=bold)
            )
    return blocks
