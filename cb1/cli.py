"""CLI entrypoints, one subcommand per pipeline stage."""

import argparse
import sys

from cb1.costs import CostLedger

STAGES = [
    "download",
    "identify",
    "segment",
    "extract-text",
    "extract-structured",
    "eval",
    "load-db",
    "cost-report",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cb1", description="CB1 minutes pipeline")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--sync", action="store_true",
                        help="extract-structured: synchronous calls instead of Batch API")
    parser.add_argument("--only", nargs="*", default=None, metavar="MEETING_ID",
                        help="extract-structured: limit to specific meeting ids")
    parser.add_argument("--draft", metavar="MEETING_ID",
                        help="eval: write a draft golden extraction for hand-correction")
    args = parser.parse_args(argv)

    if args.stage == "cost-report":
        print(CostLedger().report())
        return 0

    if args.stage == "download":
        from cb1.download import download_all
        from cb1.scrape import extract_pdf_hrefs, fetch_index

        download_all(extract_pdf_hrefs(fetch_index()))
        return 0

    if args.stage == "identify":
        from cb1.anthropic_client import Client
        from cb1.identify import run_identify

        run_identify(client=Client())
        return 0

    if args.stage == "extract-text":
        from cb1.anthropic_client import Client
        from cb1.vision_ocr import run_extract_text

        run_extract_text(Client())
        return 0

    if args.stage == "segment":
        from cb1.segment import run_segment

        run_segment()
        return 0

    if args.stage == "extract-structured":
        from cb1.anthropic_client import Client
        from cb1.extract import run_extract_structured

        run_extract_structured(Client(), sync=args.sync, only=args.only)
        return 0

    if args.stage == "eval":
        from cb1.anthropic_client import Client
        from cb1.eval.run import draft_golden, run_eval

        client = Client()  # backend resolves to bedrock or anthropic via config
        if args.draft:
            draft_golden(args.draft, client)
            return 0
        return run_eval(client)

    if args.stage == "load-db":
        from cb1.db import load_db

        load_db()
        return 0


if __name__ == "__main__":
    sys.exit(main())
