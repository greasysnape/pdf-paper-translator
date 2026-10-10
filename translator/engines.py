"""Translation engines."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

LANG_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
}


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code.lower(), code)


class Engine(ABC):
    name: str = "base"
    model: str = ""

    def __init__(self, src_lang: str, tgt_lang: str, glossary: dict[str, str] | None = None) -> None:
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.glossary = glossary or {}

    @abstractmethod
    def translate_batch(self, texts: list[str]) -> list[str]:
        """Translate a batch; must return a list of the same length."""


class DummyEngine(Engine):
    """Offline engine for testing the layout pipeline."""

    name = "dummy"
    model = "dummy"

    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"[{self.tgt_lang}] {t}" for t in texts]


SYSTEM_PROMPT = """You are a professional translator of academic papers.
Translate each input segment from {src} to {tgt}.

Rules:
- Keep LaTeX, inline math, variable names, citations like [12] or (Smith et al., 2020), URLs and code unchanged.
- Keep technical terms accurate; when a term is commonly left in English in {tgt} papers, you may keep it.
- Do not add explanations, notes or quotes.
- Return ONLY a JSON array of strings, one translation per input segment, in the same order.
{glossary}"""


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(
        self,
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_retries: int = 4,
    ) -> None:
        super().__init__(src_lang, tgt_lang, glossary)
        from google import genai
        from google.genai import types

        self._types = types
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (see .env.example)")
        self.client = genai.Client(api_key=key)
        self.model = model or os.environ.get("PDFTRANS_MODEL", "gemini-2.5-flash")
        self.max_retries = max_retries

    def _system_prompt(self) -> str:
        gl = ""
        if self.glossary:
            pairs = "\n".join(f"- {s} -> {t}" for s, t in self.glossary.items())
            gl = f"\nGlossary (always use these translations):\n{pairs}\n"
        return SYSTEM_PROMPT.format(src=lang_name(self.src_lang), tgt=lang_name(self.tgt_lang), glossary=gl)

    @staticmethod
    def _parse(raw: str, n: int) -> list[str] | None:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list) or len(data) != n:
            return None
        return [str(x) for x in data]

    def _call(self, texts: list[str]) -> list[str] | None:
        types = self._types
        payload = json.dumps(texts, ensure_ascii=False)
        resp = self.client.models.generate_content(
            model=self.model,
            contents=payload,
            config=types.GenerateContentConfig(
                system_instruction=self._system_prompt(),
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        return self._parse(resp.text or "", len(texts))

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                out = self._call(texts)
                if out is not None:
                    return out
                log.warning("malformed response for batch of %d (attempt %d)", len(texts), attempt)
            except Exception as e:  # network / quota errors
                log.warning("gemini error (attempt %d/%d): %s", attempt, self.max_retries, e)
            time.sleep(delay)
            delay *= 2

        # last resort: one segment at a time so a single bad block can't sink the batch
        if len(texts) > 1:
            log.info("falling back to single-segment requests")
            result = []
            for t in texts:
                result.extend(self.translate_batch([t]))
            return result
        log.error("could not translate segment, keeping original")
        return texts


def create_engine(name: str, src: str, tgt: str, glossary: dict[str, str] | None, model: str | None) -> Engine:
    name = name.lower()
    if name == "dummy":
        return DummyEngine(src, tgt, glossary)
    if name == "gemini":
        return GeminiEngine(src, tgt, glossary, model=model)
    raise ValueError(f"unknown engine: {name}")
