"""Mask traffic-incident names out of the shipped mail dataset.

data/mail_items.jsonl carries a 1,200-character window per letter. The board's
own outgoing fatality-inquiry letters quote the victim under a literal
'Victim:' label, so those names ride along in the window text even though the
parquet exports mask them. This applies the same policy to the JSONL.

Deterministic and idempotent - no model calls, so re-running is free. Reads
the names from the local DuckDB, which keeps them.

    uv run python scripts/redact_mail_names.py
"""

import json
from pathlib import Path

import duckdb

from cb1 import config
from cb1.db import _name_masker

FILES = ("mail_items.jsonl", "mail_adjudications.jsonl")
TEXT_FIELDS = ("window", "opening", "text", "body", "sender")


def main() -> None:
    con = duckdb.connect(str(config.DB_DIR / "cb1.duckdb"), read_only=True)
    mask = _name_masker(con)

    for fname in FILES:
        path = Path(config.DATA_DIR) / fname
        if not path.exists():
            continue
        out, changed = [], 0
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            hit = False
            for f in TEXT_FIELDS:
                if isinstance(rec.get(f), str):
                    masked = mask(rec[f])
                    if masked != rec[f]:
                        rec[f], hit = masked, True
            changed += hit
            out.append(json.dumps(rec, ensure_ascii=False))
        if changed:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"redact_mail_names: {fname} - {changed} records masked")

    con.close()


if __name__ == "__main__":
    main()
