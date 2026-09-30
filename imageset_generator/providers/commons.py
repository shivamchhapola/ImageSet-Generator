"""
Wikimedia Commons image finder.

Given a person's name, returns candidate image URLs with
license/attribution metadata.
"""

from __future__ import annotations

import html
import re

import requests

from imageset_generator.config import (
    COMMONS_API,
    COMMONS_BAD_KEYWORDS,
    HEADERS,
    TIMEOUT,
)


def _get(params: dict) -> dict:
    r = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(str(value))).strip()


def _meta_value(meta: dict, key: str, default: str = "Unknown") -> str:
    value = (meta.get(key) or {}).get("value")
    return _strip_html(value) if value else default


def find_candidates(person_name: str) -> list[dict]:
    """Search Wikimedia Commons for portrait images of *person_name*.

    Returns a list of dicts, each with:
        url, title, author, license, license_url
    """
    searches = [
        f'"{person_name}" portrait',
        f'"{person_name}"',
        person_name,
    ]

    results: list[dict] = []
    seen: set[str] = set()

    for term in searches:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": term,
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 900,
            "format": "json",
        }
        try:
            data = _get(params)
        except Exception:
            continue

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            mime = info.get("mime", "")

            if not url or not mime.startswith("image/"):
                continue
            if title.casefold() in seen:
                continue
            if any(kw in title.casefold() for kw in COMMONS_BAD_KEYWORDS):
                continue

            seen.add(title.casefold())
            meta = info.get("extmetadata") or {}
            results.append({
                "url":         url,
                "title":       title,
                "source_page": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                "author":      _meta_value(meta, "Artist"),
                "license":     _meta_value(meta, "LicenseShortName"),
                "license_url": _meta_value(meta, "LicenseUrl", ""),
            })

        if results:
            break

    return results
