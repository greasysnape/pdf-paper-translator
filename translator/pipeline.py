"""End-to-end translation pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from tqdm import tqdm

from .cache import TranslationCache
from .engines import Engine
from .math_guard import should_translate
from .pdf_io import TextBlock, extract_blocks, parse_page_range
from .render import write_dual, write_mono

log = logging.getLogger(__name__)


@dataclass
class Result:
    mono: Path | None
    dual: Path | None
    total_blocks: int
    translated_blocks: int
    cached_blocks: int


def load_glossary(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    gl: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "\t" not in line:
                continue
            src, tgt = line.split("\t", 1)
            gl[src.strip()] = tgt.strip()
    return gl


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def translate_blocks(
    blocks: list[TextBlock],
    engine: Engine,
    cache: TranslationCache,
    batch_size: int = 20,
) -> int:
    """Fill `translation` on each block. Returns the number of cache hits."""
    hits = 0
    pending: list[tuple[TextBlock, str]] = []
    for b in blocks:
        key = cache.make_key(engine.name, engine.model, engine.src_lang, engine.tgt_lang, b.text)
        cached = cache.get(key)
        if cached is not None:
            b.translation = cached
            hits += 1
        else:
            pending.append((b, key))

    batches = list(_chunks(pending, batch_size))
    for batch in tqdm(batches, desc="translating", unit="batch", disable=not batches):
        outputs = engine.translate_batch([b.text for b, _ in batch])
        for (b, key), out in zip(batch, outputs):
            b.translation = out
            cache.put(key, engine.name, engine.model, engine.src_lang, engine.tgt_lang, b.text, out)
    return hits


def run(
    input_pdf: str | Path,
    engine: Engine,
    output_dir: str | Path | None = None,
    pages: str | None = None,
    batch_size: int = 20,
    use_cache: bool = True,
    make_mono: bool = True,
    make_dual: bool = True,
) -> Result:
    src = Path(input_pdf)
    if not src.exists():
        raise FileNotFoundError(src)
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(src)
    if doc.is_encrypted:
        raise RuntimeError("encrypted PDFs are not supported")
    page_list = parse_page_range(pages, doc.page_count)
    blocks = extract_blocks(doc, page_list)
    doc.close()

    todo = [b for b in blocks if should_translate(b.text)]
    log.info("%d text blocks, %d to translate on %d pages", len(blocks), len(todo), len(page_list))

    cache = TranslationCache(enabled=use_cache)
    try:
        hits = translate_blocks(todo, engine, cache, batch_size)
    finally:
        cache.close()

    stem = src.stem
    mono_path = out_dir / f"{stem}.mono.pdf"
    dual_path = out_dir / f"{stem}.dual.pdf"

    write_mono(src, mono_path, todo, engine.tgt_lang)
    dual = write_dual(src, mono_path, dual_path, page_list) if make_dual else None
    mono = mono_path
    if not make_mono:
        mono_path.unlink(missing_ok=True)
        mono = None

    return Result(mono=mono, dual=dual, total_blocks=len(blocks), translated_blocks=len(todo), cached_blocks=hits)
