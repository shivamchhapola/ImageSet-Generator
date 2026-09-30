"""
Core image-set building logic.

Handles image downloading, cropping, caching, and ZIP creation.
This module is UI-agnostic — it exposes callbacks for progress reporting
so both CLI and GUI can use it.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path
from typing import Callable

import requests
from PIL import Image, ImageOps

from imageset_generator.config import (
    CACHE_DIR,
    DEFAULT_FORMAT,
    DEFAULT_IMAGE_SIZE,
    HEADERS,
    OUTPUT_DIR,
)
from imageset_generator.providers import commons


# ── Utilities ─────────────────────────────────────────────────────────────────

def clean_filename(s: str) -> str:
    """Sanitize *s* into a safe filesystem name."""
    import html as _html
    s = _html.unescape(s or "").strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s)
    return s.rstrip(". ")


# ── Image fetching ─────────────────────────────────────────────────────────────

def _download_and_crop(
    url: str,
    size: tuple[int, int] = DEFAULT_IMAGE_SIZE,
) -> Image.Image:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    return ImageOps.fit(
        img,
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.45),
    )


def get_image_for_person(
    person: str,
    fallback_url: str | None,
    size: tuple[int, int] = DEFAULT_IMAGE_SIZE,
) -> tuple[Image.Image | None, dict | None]:
    """Try Commons first, then fallback URL.

    Returns (image, source_info) or (None, None) on total failure.
    """
    for candidate in commons.find_candidates(person):
        try:
            img = _download_and_crop(candidate["url"], size)
            return img, {
                "provider":    "Wikimedia Commons",
                "source":      candidate["title"],
                "url":         candidate["source_page"],
                "author":      candidate["author"],
                "license":     candidate["license"],
                "license_url": candidate["license_url"],
            }
        except Exception:
            continue

    if fallback_url:
        try:
            img = _download_and_crop(fallback_url, size)
            return img, {
                "provider":    "TVmaze",
                "source":      "TVmaze person image",
                "url":         fallback_url,
                "author":      "See TVmaze source",
                "license":     "Not assumed to be freely licensed",
                "license_url": "",
            }
        except Exception:
            pass

    return None, None


# ── ZIP building ───────────────────────────────────────────────────────────────

def build_set(
    set_name: str,
    entries: list[dict],
    *,
    image_size: tuple[int, int] = DEFAULT_IMAGE_SIZE,
    image_format: str = DEFAULT_FORMAT,
    output_dir: Path | None = None,
    cache_dir: Path | None = None,
    on_progress: Callable[[int, int, str, str], None] | None = None,
) -> Path:
    """Download images and create a ZIP pack.

    Args:
        set_name:     Human-readable name for this set (used for filenames).
        entries:      List of Entry dicts (label, person, fallback_img, …).
        image_size:   Output pixel dimensions.
        image_format: "JPEG" or "PNG".
        output_dir:   Where to write the ZIP (defaults to OUTPUT_DIR).
        cache_dir:    Where to cache downloaded images (defaults to CACHE_DIR).
        on_progress:  Called as on_progress(current, total, label, status).
                      status is one of: "cached", "ok", "no_image", "error".

    Returns:
        Path to the written ZIP file.
    """
    slug = clean_filename(set_name)
    ext = "jpg" if image_format.upper() == "JPEG" else "png"

    cache_root = (cache_dir or CACHE_DIR) / slug
    cache_root.mkdir(parents=True, exist_ok=True)

    out_root = output_dir or OUTPUT_DIR
    out_root.mkdir(parents=True, exist_ok=True)

    sources: list[str] = []
    successful = 0
    total = len(entries)

    for n, entry in enumerate(entries, 1):
        label = clean_filename(entry["label"])
        person = entry.get("person", label)
        fallback = entry.get("fallback_img")
        target = cache_root / f"{label}.{ext}"

        if target.exists():
            successful += 1
            if on_progress:
                on_progress(n, total, label, "cached")
            continue

        if on_progress:
            on_progress(n, total, label, "downloading")

        try:
            img, source_info = get_image_for_person(person, fallback, image_size)
        except Exception as exc:
            if on_progress:
                on_progress(n, total, label, f"error: {exc}")
            continue

        if img is None:
            if on_progress:
                on_progress(n, total, label, "no_image")
            continue

        save_kwargs: dict = {"optimize": True}
        if image_format.upper() == "JPEG":
            save_kwargs["quality"] = 90

        img.save(target, image_format.upper(), **save_kwargs)
        successful += 1

        assert source_info is not None
        sources.append(
            f"Label: {label}\n"
            f"Person: {person}\n"
            f"Provider: {source_info['provider']}\n"
            f"Source: {source_info['source']}\n"
            f"URL: {source_info['url']}\n"
            f"Author: {source_info['author']}\n"
            f"License: {source_info['license']}\n"
            f"License URL: {source_info['license_url'] or 'See source page'}\n"
        )

        if on_progress:
            on_progress(n, total, label, "ok")

        time.sleep(0.25)

    if successful == 0:
        raise RuntimeError("No images could be downloaded for any entry.")

    zip_path = out_root / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for img_file in sorted(cache_root.glob(f"*.{ext}")):
            z.write(img_file, img_file.name)

        source_text = (
            f"Image Set: {set_name}\n"
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Images: {successful}/{total}\n\n"
            + "\n\n".join(sources)
            + "\n\n"
            "LICENSE NOTICE:\n"
            "Wikimedia Commons files carry their own licenses — check each entry above.\n"
            "TVmaze fallback images are not assumed to be freely licensed.\n"
            "Review SOURCES.txt before redistributing this pack publicly.\n"
        )
        z.writestr("SOURCES.txt", source_text)

    return zip_path
