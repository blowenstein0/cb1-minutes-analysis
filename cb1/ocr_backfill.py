"""Backfill OCR for ALL textless pages (the 'dark' attachments).

The main pipeline deliberately skipped attachment scans to keep extraction
cheap. This backfill makes them full-text searchable — resident letters,
written testimony, scanned reports — so archival analyses (letters over
time, mention counts) see the whole record. Cached per page; safe to kill
and rerun. Oldest meetings first (they're the darkest).

Run: uv run python -m cb1.ocr_backfill {haiku|tesseract}

Tesseract tier is free; validated against 59 Haiku transcripts of the same
pages: median word recall 98%, 85%+ on 50/59. Adequate for searchability
(mentions, letters); pages where tesseract fails land in an escalation
list for an optional paid vision pass.
"""

import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

from cb1 import config
from cb1.anthropic_client import Client
from cb1.identify import load_meetings
from cb1.pdf_text import is_textless, page_texts
from cb1.rasterize import page_jpeg, page_jpeg_path
from cb1.vision_ocr import ocr_page

PROVENANCE = config.INTERIM_DIR / "ocr" / "_provenance.jsonl"
ESCALATE = config.INTERIM_DIR / "ocr" / "_escalate.jsonl"


def dark_pages() -> list[tuple[str, str, str, int]]:
    """(meeting_id, local, sha256, page_no) for every textless page with no
    transcript yet, oldest meetings first."""
    todo = []
    for mid, m in sorted(load_meetings().items(), key=lambda kv: kv[1]["date"]):
        for f in m["files"]:
            path = config.RAW_DIR / f["local"]
            for i, t in enumerate(page_texts(path, f["sha256"])):
                if is_textless(t) and not config.ocr_text_path(f["sha256"], i).exists():
                    todo.append((mid, f["local"], f["sha256"], i))
    return todo


def main() -> None:
    client = Client()
    todo = dark_pages()
    print(f"ocr-backfill: {len(todo)} dark pages to transcribe", flush=True)
    for n, (mid, local, sha, page_no) in enumerate(todo, 1):
        ocr_page(config.RAW_DIR / local, sha, page_no, client)
        if n % 50 == 0:
            print(f"  [{n}/{len(todo)}] through {mid} "
                  f"(${client.ledger.total_usd():.2f} total spend)", flush=True)
    print(f"ocr-backfill: done, total spend ${client.ledger.total_usd():.2f}", flush=True)


def _tesseract_one(args):
    local, sha, page_no = args
    img_path = page_jpeg_path(sha, page_no)
    if not img_path.exists():
        page_jpeg(config.RAW_DIR / local, sha, page_no)
    out = subprocess.run(
        ["tesseract", str(img_path), "stdout", "--psm", "3"],
        capture_output=True, text=True, timeout=120,
    )
    text = out.stdout.strip()
    config.ocr_text_path(sha, page_no).write_text(text)
    img_path.unlink(missing_ok=True)  # keep disk flat; jpg is regenerable
    return sha, page_no, len(text.split())


def main_tesseract(workers: int = 6) -> None:
    todo = [(local, sha, i) for _, local, sha, i in dark_pages()]
    print(f"tesseract-backfill: {len(todo)} pages, {workers} workers", flush=True)
    done = 0
    with PROVENANCE.open("a") as prov, ESCALATE.open("a") as esc, \
            ProcessPoolExecutor(max_workers=workers) as ex:
        for sha, page_no, nwords in ex.map(_tesseract_one, todo, chunksize=8):
            key = f"{sha}-p{page_no:03d}"
            prov.write(json.dumps({"key": key, "engine": "tesseract"}) + "\n")
            if nwords < 10:
                esc.write(json.dumps({"key": key, "words": nwords}) + "\n")
            done += 1
            if done % 250 == 0:
                print(f"  [{done}/{len(todo)}]", flush=True)
    print(f"tesseract-backfill: done ({done} pages, $0)", flush=True)


if __name__ == "__main__":
    tiers = {"haiku": main, "tesseract": main_tesseract}
    tier = sys.argv[1] if len(sys.argv) > 1 else ""
    if tier not in tiers:
        raise SystemExit("usage: python -m cb1.ocr_backfill {haiku|tesseract}")
    tiers[tier]()
