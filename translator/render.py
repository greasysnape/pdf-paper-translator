"""Write translated blocks back into PDF pages."""

from __future__ import annotations

import html
import logging
from pathlib import Path

import pymupdf

from .pdf_io import TextBlock

log = logging.getLogger(__name__)

CJK_LANGS = {"ko", "ja", "zh", "zh-tw"}


def _css(lang: str) -> str:
    # CJK text needs a slightly tighter line height to fit the original boxes
    lh = 1.15 if lang.lower() in CJK_LANGS else 1.2
    return f"* {{ line-height: {lh}; margin: 0; padding: 0; }}"


def _html(block: TextBlock) -> str:
    text = html.escape(block.translation or block.text)
    size = max(block.font_size, 4.0)
    weight = "bold" if block.bold else "normal"
    return f'<p style="font-size:{size:.1f}px; font-weight:{weight};">{text}</p>'


def _apply(page: pymupdf.Page, blocks: list[TextBlock], lang: str) -> None:
    css = _css(lang)
    for b in blocks:
        rect = pymupdf.Rect(b.bbox)
        page.add_redact_annot(rect, fill=(1, 1, 1))
    # remove only the text under the boxes, keep images and vector graphics
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)

    for b in blocks:
        rect = pymupdf.Rect(b.bbox)
        # a little extra room at the bottom; insert_htmlbox scales down if needed
        rect.y1 += b.font_size * 0.4
        spare, scale = page.insert_htmlbox(rect, _html(b), css=css, scale_low=0)
        if spare < 0:
            log.debug("block %s did not fit even after scaling", b.key)


def write_mono(src: Path, out: Path, blocks: list[TextBlock], lang: str) -> Path:
    doc = pymupdf.open(src)
    by_page: dict[int, list[TextBlock]] = {}
    for b in blocks:
        if b.translation:
            by_page.setdefault(b.page, []).append(b)
    for pno, items in by_page.items():
        _apply(doc[pno], items, lang)
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return out


def write_dual(src: Path, mono: Path, out: Path, pages: list[int]) -> Path:
    """Original on the left, translation on the right."""
    orig = pymupdf.open(src)
    trans = pymupdf.open(mono)
    dual = pymupdf.open()
    for pno in pages:
        r = orig[pno].rect
        page = dual.new_page(width=r.width * 2, height=r.height)
        page.show_pdf_page(pymupdf.Rect(0, 0, r.width, r.height), orig, pno)
        page.show_pdf_page(pymupdf.Rect(r.width, 0, r.width * 2, r.height), trans, pno)
    dual.save(out, garbage=3, deflate=True)
    for d in (orig, trans, dual):
        d.close()
    return out
