"""Runtime configuration, read from environment variables (never logs secrets)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
SAMPLES_DIR = Path(os.environ.get("LEDGERLIGHT_SAMPLES_DIR", PROJECT_DIR / "samples"))
DATA_DIR = Path(os.environ.get("LEDGERLIGHT_DATA_DIR", BACKEND_DIR / "data"))
DB_PATH = Path(os.environ.get("LEDGERLIGHT_DB", DATA_DIR / "ledgerlight.db"))
UPLOAD_DIR = DATA_DIR / "uploads"

# Model used for extraction and explanation polish when ANTHROPIC_API_KEY is set.
LLM_MODEL = os.environ.get("LEDGERLIGHT_MODEL", "claude-sonnet-5-5")
PROMPT_VERSION = "extract-1.0"
TEXT_PARSER_VERSION = "text-parser-1.0"

# Display pacing (minimum visible dwell per stage, ms). Named presets or a number.
PACE_PRESETS = {"instant": 0, "fast": 150, "normal": 550, "slow": 1200}
DEFAULT_PACE = os.environ.get("LEDGERLIGHT_PACE", "normal")

# "Today" for date rules and dashboard ranges (spec A14). Empty string = real today.
AS_OF = os.environ.get("LEDGERLIGHT_AS_OF", "2026-11-16")

# Our own company (the buyer). Its GSTIN is printed on every invoice and must not be
# mistaken for the vendor's.
BUYER = {
    "name": "Halcyon Foods Pvt Ltd",
    "gstin": "27AAGCH5521L1Z7",
    "address": "Unit 4, Kalina Business Park, Santacruz East, Mumbai 400098",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 10


def llm_available() -> bool:
    """True when an Anthropic API key is configured. The key itself is never read here."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def pace_ms(pace: str | int | None) -> int:
    if pace is None or pace == "":
        pace = DEFAULT_PACE
    if isinstance(pace, (int, float)):
        return max(0, int(pace))
    p = str(pace).strip().lower()
    if p.isdigit():
        return int(p)
    return PACE_PRESETS.get(p, PACE_PRESETS["normal"])
