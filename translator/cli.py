"""Command-line interface: `pdftrans paper.pdf --lang ko`."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from . import __version__
from .engines import create_engine
from .pipeline import load_glossary, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pdftrans", description="Layout-preserving PDF paper translator")
    p.add_argument("input", help="input PDF")
    p.add_argument("-o", "--output", help="output directory (default: next to the input)")
    p.add_argument("-l", "--lang", default="ko", help="target language code (default: ko)")
    p.add_argument("--source-lang", default="en", help="source language code (default: en)")
    p.add_argument("--engine", default="gemini", choices=["gemini", "dummy"])
    p.add_argument("--model", default=None, help="model name (default: $PDFTRANS_MODEL or gemini-2.5-flash)")
    p.add_argument("--pages", help='page range, e.g. "1-3,7"')
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--glossary", help="TSV glossary file")
    p.add_argument("--no-cache", action="store_true")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--mono-only", action="store_true")
    g.add_argument("--dual-only", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    # the google client is chatty at INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)

    try:
        engine = create_engine(
            args.engine,
            args.source_lang,
            args.lang,
            load_glossary(args.glossary),
            args.model or os.environ.get("PDFTRANS_MODEL"),
        )
        result = run(
            args.input,
            engine,
            output_dir=args.output,
            pages=args.pages,
            batch_size=max(1, args.batch_size),
            use_cache=not args.no_cache,
            make_mono=not args.dual_only,
            make_dual=not args.mono_only,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"blocks: {result.total_blocks} total, {result.translated_blocks} translated "
          f"({result.cached_blocks} from cache)")
    if result.mono:
        print(f"mono : {result.mono}")
    if result.dual:
        print(f"dual : {result.dual}")
    return 0
