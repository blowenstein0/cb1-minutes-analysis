"""Per-page text extraction, cached in data/interim/text.

Cache key is sha256 of the file, so re-runs are free and a re-uploaded
(changed) PDF re-extracts automatically.
"""

import json
from functools import lru_cache

import fitz  # pymupdf

from cb1 import config


@lru_cache(maxsize=None)
def page_texts(pdf_path, sha256: str) -> list[str]:
    """Text of every page (text layer only — no OCR). Cached on disk and
    in memory (the text layer never changes for a given sha)."""
    cache = config.INTERIM_DIR / "text" / f"{sha256}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    with fitz.open(pdf_path) as doc:
        texts = [page.get_text() for page in doc]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(texts))
    return texts


def is_textless(text: str) -> bool:
    """No usable text layer — a scanned page needing OCR."""
    return len(text.strip()) < 20
