"""Runtime configuration, read from environment variables (never logs secrets)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def load_dotenv(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from a git-ignored .env file. Values are returned, never printed."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# backend/.env fills in variables that the shell has not already set (tests switch this off).
if os.environ.get("LEDGERLIGHT_DOTENV", "1") != "0":
    for _k, _v in load_dotenv(BACKEND_DIR / ".env").items():
        os.environ.setdefault(_k, _v)
SAMPLES_DIR = Path(os.environ.get("LEDGERLIGHT_SAMPLES_DIR", PROJECT_DIR / "samples"))
DATA_DIR = Path(os.environ.get("LEDGERLIGHT_DATA_DIR", BACKEND_DIR / "data"))
DB_PATH = Path(os.environ.get("LEDGERLIGHT_DB", DATA_DIR / "ledgerlight.db"))
UPLOAD_DIR = DATA_DIR / "uploads"

# AI provider for extraction and explanation polish: Claude when ANTHROPIC_API_KEY is set, otherwise Groq
# when GROQ_API_KEY is set, otherwise none. LEDGERLIGHT_MODEL overrides the model for whichever is active.
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "groq": "qwen/qwen3.8-27b"}
NO_KEY_HINT = "set ANTHROPIC_API_KEY or GROQ_API_KEY"

# Which invoices the AI reads: "auto" = only image-only scans (text PDFs use the tested deterministic parser),
# "llm" = every invoice.
EXTRACTION_MODE = os.environ.get("LEDGERLIGHT_EXTRACTION", "auto").strip().lower()
PROMPT_VERSION = "extract-1.1"
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

# Public deployment: one private copy of the demo data per visitor (see db.py, "per-visitor sandboxes").
SANDBOXES = os.environ.get("LEDGERLIGHT_SANDBOXES", "0") == "1"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 10


def llm_provider() -> str | None:
    """'anthropic', 'groq' or None, from which key is configured. Only presence is checked, never the value."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "groq"
    return None


def llm_available() -> bool:
    return llm_provider() is not None


def llm_model() -> str | None:
    prov = llm_provider()
    if prov is None:
        return None
    return os.environ.get("LEDGERLIGHT_MODEL", "").strip() or DEFAULT_MODELS[prov]


def llm_reads_text_pdfs() -> bool:
    return EXTRACTION_MODE == "llm"


def pace_ms(pace: str | int | None) -> int:
    if pace is None or pace == "":
        pace = DEFAULT_PACE
    if isinstance(pace, (int, float)):
        return max(0, int(pace))
    p = str(pace).strip().lower()
    if p.isdigit():
        return int(p)
    return PACE_PRESETS.get(p, PACE_PRESETS["normal"])
