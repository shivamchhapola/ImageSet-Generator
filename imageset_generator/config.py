"""
Shared constants and configuration for imageset_generator.
"""

from pathlib import Path

# ── HTTP ──────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "ImageSetGenerator/1.0 (open-source; github.com/imageset-generator)"
}
TIMEOUT = 30

# ── Image defaults ────────────────────────────────────────────────────────────
DEFAULT_IMAGE_SIZE = (512, 512)
DEFAULT_FORMAT = "JPEG"        # "JPEG" or "PNG"
DEFAULT_LIMIT = 20

# ── Filesystem ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
OUTPUT_DIR = ROOT / "sets"

# ── Provider constants ────────────────────────────────────────────────────────
TVMAZE_BASE = "https://api.tvmaze.com"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# ── Commons image blocklist (title substrings to skip) ───────────────────────
COMMONS_BAD_KEYWORDS = (
    "logo", "poster", "screenshot", "signature",
    "flag", "coat of arms", "icon", "collage",
)
