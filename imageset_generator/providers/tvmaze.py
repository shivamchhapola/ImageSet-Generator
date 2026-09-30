"""
TVmaze provider — searches TV shows and retrieves their cast.
No API key required.
"""

from __future__ import annotations

from imageset_generator.config import HEADERS, TIMEOUT, TVMAZE_BASE
import requests


def _get(url: str, params: dict | None = None) -> dict | list:
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def search(query: str) -> list[dict]:
    """Return a list of show candidates matching *query*.

    Each item has keys: id, name, year, genres, image_url.
    """
    results = _get(f"{TVMAZE_BASE}/search/shows", {"q": query})
    out = []
    for item in results[:10]:
        show = item["show"]
        image = (show.get("image") or {})
        out.append({
            "id":        show["id"],
            "name":      show["name"],
            "year":      (show.get("premiered") or "")[:4],
            "genres":    show.get("genres") or [],
            "image_url": image.get("medium") or image.get("original"),
            "summary":   show.get("summary") or "",
        })
    return out


def fetch_entries(show_id: int, limit: int | None = None) -> list[dict]:
    """Return cast entries for *show_id* up to *limit* items."""
    cast = _get(f"{TVMAZE_BASE}/shows/{show_id}/cast")

    seen: set[str] = set()
    out: list[dict] = []

    for entry in cast:
        character_data = entry.get("character") or {}
        character = character_data.get("name")
        person_data = entry.get("person") or {}
        person = person_data.get("name")

        if not character or not person:
            continue

        key = character.casefold()
        if key in seen:
            continue
        seen.add(key)

        character_image = character_data.get("image") or {}
        person_image = person_data.get("image") or {}
        
        fallback_img = (
            character_image.get("original") or character_image.get("medium") or
            person_image.get("original") or person_image.get("medium")
        )

        out.append({
            "label":        character,
            "person":       person,
            "person_id":    person_data.get("id"),
            "fallback_img": fallback_img,
        })

        if limit and len(out) >= limit:
            break

    return out
