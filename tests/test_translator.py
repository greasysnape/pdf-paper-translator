from pathlib import Path

import pymupdf
import pytest

from translator.cache import TranslationCache
from translator.engines import DummyEngine, GeminiEngine
from translator.math_guard import should_translate
from translator.pdf_io import extract_blocks, parse_page_range
from translator.pipeline import load_glossary, run


@pytest.mark.parametrize("spec,expected", [
    (None, [0, 1, 2, 3, 4]),
    ("1-3", [0, 1, 2]),
    ("2,4", [1, 3]),
    ("4-", [3, 4]),
    ("1-2,5,9", [0, 1, 4]),
])
def test_parse_page_range(spec, expected):
    assert parse_page_range(spec, 5) == expected


@pytest.mark.parametrize("text,ok", [
    ("We propose a novel method for document translation.", True),
    ("[12]", False),
    ("(3)", False),
    ("Figure 2", False),
    ("x = ∑_{i=1}^{n} α_i y_i + β", False),
    ("0.83 0.91 0.77", False),
    ("https://arxiv.org/abs/2410.01234", False),
    ("Introduction", False),
])
def test_should_translate(text, ok):
    assert should_translate(text) is ok


def test_glossary(tmp_path):
    f = tmp_path / "g.tsv"
    f.write_text("# comment\nattention\t어텐션\n\nbad line\nfine-tuning\t파인튜닝\n", encoding="utf-8")
    assert load_glossary(f) == {"attention": "어텐션", "fine-tuning": "파인튜닝"}


def test_cache_roundtrip(tmp_path):
    c = TranslationCache(tmp_path / "c.sqlite3")
    k = c.make_key("dummy", "dummy", "en", "ko", "hello world")
    assert c.get(k) is None
    c.put(k, "dummy", "dummy", "en", "ko", "hello world", "안녕 세상")
    assert c.get(k) == "안녕 세상"
    c.close()


def test_gemini_parse():
    assert GeminiEngine._parse('```json\n["a", "b"]\n```', 2) == ["a", "b"]
    assert GeminiEngine._parse('["a"]', 2) is None
    assert GeminiEngine._parse("not json", 1) is None


def _make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 520, 200),
        "Large language models have shown strong performance on many reasoning benchmarks.",
        fontsize=11,
    )
    page.insert_text((72, 260), "[1]", fontsize=9)
    doc.save(path)
    doc.close()


def test_extract_and_run_dummy(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANS_CACHE_DIR", str(tmp_path / "cache"))
    src = tmp_path / "paper.pdf"
    _make_pdf(src)

    doc = pymupdf.open(src)
    blocks = extract_blocks(doc, [0])
    doc.close()
    assert any("language models" in b.text for b in blocks)

    res = run(src, DummyEngine("en", "ko"), output_dir=tmp_path / "out")
    assert res.mono and res.mono.exists()
    assert res.dual and res.dual.exists()
    assert res.translated_blocks == 1

    out = pymupdf.open(res.mono)
    assert "[ko]" in out[0].get_text()
    out.close()

    # second run hits the cache
    res2 = run(src, DummyEngine("en", "ko"), output_dir=tmp_path / "out")
    assert res2.cached_blocks == 1
