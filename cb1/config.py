"""Central configuration: paths, model ids, budget, tunables.

Everything env-overridable uses the CB1_ prefix. ANTHROPIC_API_KEY is read
by the anthropic SDK directly.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
EXTRACTED_DIR = DATA_DIR / "extracted"
DB_DIR = DATA_DIR / "db"
COSTS_PATH = DATA_DIR / "costs.jsonl"
UNRESOLVED_PATH = DATA_DIR / "unresolved.json"

EVAL_DIR = REPO_ROOT / "eval"
GOLDEN_DIR = EVAL_DIR / "golden"
EVAL_CACHE_DIR = EVAL_DIR / "cache"

# "bedrock" (AWS creds) or "anthropic" (ANTHROPIC_API_KEY). Default: use the
# Anthropic API when its key is present, else Bedrock.
BACKEND = os.environ.get(
    "CB1_BACKEND", "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "bedrock"
)
AWS_REGION = os.environ.get("CB1_AWS_REGION", "us-east-1")

MODEL = os.environ.get("CB1_MODEL", "claude-haiku-4-5")
BEDROCK_MODEL_IDS = {
    "claude-haiku-4-5": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}

# Haiku 4.5 list pricing, USD per million tokens.
PRICE_PER_MTOK = {
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
}
BATCH_DISCOUNT = 0.5  # Batch API is 50% off input and output

BUDGET_CAP_USD = float(os.environ.get("CB1_BUDGET_CAP_USD", "75"))

INDEX_URL = "https://www.nyc.gov/site/brooklyncb1/meetings/minutes.page"
BASE_URL = "https://www.nyc.gov"
# nyc.gov 403s non-browser user agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DOWNLOAD_DELAY_S = 1.0

RASTER_DPI = 150

SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "1.0"


def ocr_text_path(sha256: str, page_no: int) -> Path:
    """Per-page OCR transcript cache. The -pNNN convention is load-bearing:
    a mismatch is a silent cache miss, not an error."""
    return INTERIM_DIR / "ocr" / f"{sha256}-p{page_no:03d}.txt"


def ensure_dirs() -> None:
    for d in (RAW_DIR, INTERIM_DIR, EXTRACTED_DIR, DB_DIR, GOLDEN_DIR, EVAL_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
